"""
LLM Interface for COMBA Pipeline — Dual-GPU routing.

Wraps VLLMInterface as LangChain-compatible BaseChatModel so
the pipeline can seamlessly switch between base model (GPU 0)
and LoRA debugger (GPU 1).

Architecture:
    GPU 0 (:8000) → base model   → Converter + Generator  (call_llm_base)
    GPU 1 (:8001) → base + LoRA  → Correcter              (call_llm_lora)

Usage:
    # From pipeline
    llm = COMBALlm.from_env()
    llm.switch_to_base()       # for converter/generator
    llm.switch_to_lora()       # for correcter

    # Direct calls
    result = llm.call_llm_base(messages)
    result = llm.call_llm_lora(messages)
"""

import os
import logging
from typing import Any, List, Optional, Dict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import Field
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class COMBALlm(BaseChatModel):
    """
    Unified LLM interface for the COMBA pipeline.

    Supports three modes:
      - "dual"    : 2 vLLM servers, route base→GPU0, lora→GPU1
      - "single"  : 1 vLLM server with LoRA, same client
      - "langchain": Use LangChain ChatOpenAI directly (dev mode)
    """

    mode: str = Field(default="base")       # current routing: "base" or "debugger"
    server_mode: str = Field(default="dual") # "dual", "single", or "langchain"
    base_url: str = Field(default="http://localhost:8000/v1")
    debugger_url: str = Field(default="http://localhost:8001/v1")
    api_key: str = Field(default="not-needed")
    model_base: str = Field(default="generator")
    model_debugger: str = Field(default="debugger")
    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=2048)
    timeout: float = Field(default=120.0)
    max_retries_llm: int = Field(default=3)

    # Internal clients (lazy-initialized)
    _client_base: Any = None
    _client_debugger: Any = None

    @property
    def _llm_type(self) -> str:
        return "comba-llm"

    def _ensure_clients(self):
        """Lazy-init OpenAI clients."""
        if self._client_base is not None:
            return

        from openai import OpenAI

        self._client_base = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )

        if self.server_mode == "dual":
            self._client_debugger = OpenAI(
                base_url=self.debugger_url,
                api_key=self.api_key,
                timeout=self.timeout,
            )
        else:
            self._client_debugger = self._client_base

        logger.info(
            f"[COMBALlm] server_mode={self.server_mode} | "
            f"base={self.base_url} | debugger={self.debugger_url}"
        )

    # ── Mode Switching ──────────────────────────────────────

    def switch_to_base(self):
        """Route subsequent _generate() calls to base model (GPU 0)."""
        self.mode = "base"
        logger.debug("[COMBALlm] Switched to BASE mode")

    def switch_to_lora(self):
        """Route subsequent _generate() calls to LoRA debugger (GPU 1)."""
        self.mode = "debugger"
        logger.debug("[COMBALlm] Switched to LORA/DEBUGGER mode")

    # ── Direct Call Methods ─────────────────────────────────

    def call_llm_base(
        self,
        messages: List[Dict[str, str]],
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """Call base model (GPU 0) directly. Returns text content."""
        return self._call(
            messages, client_mode="base",
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )

    def call_llm_lora(
        self,
        messages: List[Dict[str, str]],
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """Call LoRA debugger (GPU 1) directly. Returns text content."""
        return self._call(
            messages, client_mode="debugger",
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )

    def _call(
        self,
        messages: List[Dict[str, str]],
        client_mode: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Internal: route to correct client and call."""
        self._ensure_clients()

        if client_mode == "debugger":
            client = self._client_debugger
            model = self.model_debugger
        else:
            client = self._client_base
            model = self.model_base

        import time
        for attempt in range(1, self.max_retries_llm + 1):
            try:
                t0 = time.time()
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                elapsed = (time.time() - t0) * 1000

                text = resp.choices[0].message.content or ""
                tok_in = resp.usage.prompt_tokens if resp.usage else 0
                tok_out = resp.usage.completion_tokens if resp.usage else 0

                logger.info(
                    f"[{client_mode}] {tok_out} tok | "
                    f"{elapsed:.0f}ms | {model}"
                )
                return text

            except Exception as e:
                logger.warning(
                    f"[{client_mode}] Attempt {attempt}/{self.max_retries_llm}: {e}"
                )
                if attempt == self.max_retries_llm:
                    raise
                time.sleep(2 ** attempt)

    # ── BaseChatModel Interface ─────────────────────────────

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        LangChain-compatible generate.
        Routes to base or debugger based on self.mode.
        """
        # Convert LangChain messages to OpenAI format
        oai_messages = []
        for m in messages:
            if hasattr(m, "type"):
                role = {"human": "user", "ai": "assistant", "system": "system"}.get(
                    m.type, "user"
                )
            else:
                role = "user"
            oai_messages.append({"role": role, "content": m.content})

        text = self._call(
            oai_messages,
            client_mode=self.mode,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        )

        message = AIMessage(content=text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    # ── Factory Methods ─────────────────────────────────────

    @classmethod
    def from_env(cls) -> "COMBALlm":
        """Create COMBALlm from .env configuration."""
        load_dotenv()

        base_url = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
        debugger_url = os.getenv("LLM_DEBUGGER_URL", "")
        api_key = os.getenv("LLM_API_KEY", "not-needed")
        model_base = os.getenv("LLM_MODEL_BASE", os.getenv("LLM_MODEL", "qwen-base"))
        model_debugger = os.getenv("LLM_MODEL_DEBUGGER", "debugger")

        # Auto-detect server mode
        server_mode = "dual" if debugger_url else "single"

        if not debugger_url:
            debugger_url = base_url

        return cls(
            server_mode=server_mode,
            base_url=base_url,
            debugger_url=debugger_url,
            api_key=api_key,
            model_base=model_base,
            model_debugger=model_debugger,
        )

    @classmethod
    def from_langchain(cls, llm) -> "COMBALlm":
        """
        Wrap an existing LangChain ChatModel as COMBALlm.
        Both base and lora route to the same model (dev mode).
        """
        # Return a thin wrapper that delegates to the provided llm
        return _LangChainWrapper(wrapped_llm=llm)

    # ── Health ──────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """Check server health."""
        self._ensure_clients()
        result = {"server_mode": self.server_mode, "servers": {}}

        for name, client, url in [
            ("base", self._client_base, self.base_url),
            ("debugger", self._client_debugger, self.debugger_url),
        ]:
            try:
                models = client.models.list()
                model_ids = [m.id for m in models.data]
                result["servers"][name] = {"status": "ok", "url": url, "models": model_ids}
            except Exception as e:
                result["servers"][name] = {"status": "error", "url": url, "error": str(e)}

        return result

    def __repr__(self):
        return (
            f"COMBALlm(server_mode={self.server_mode!r}, mode={self.mode!r}, "
            f"base={self.base_url!r}, debugger={self.debugger_url!r})"
        )


class _LangChainWrapper(BaseChatModel):
    """Thin wrapper for using an existing LangChain model as COMBALlm."""

    wrapped_llm: Any = Field(default=None)
    mode: str = Field(default="base")

    @property
    def _llm_type(self) -> str:
        return "comba-langchain-wrapper"

    def switch_to_base(self):
        self.mode = "base"

    def switch_to_lora(self):
        self.mode = "debugger"

    def call_llm_base(self, messages, **kwargs) -> str:
        return self._call_wrapped(messages)

    def call_llm_lora(self, messages, **kwargs) -> str:
        return self._call_wrapped(messages)

    def _call_wrapped(self, messages) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage
        lc_messages = []
        for m in messages:
            if m["role"] == "system":
                lc_messages.append(SystemMessage(content=m["content"]))
            else:
                lc_messages.append(HumanMessage(content=m["content"]))
        resp = self.wrapped_llm.invoke(lc_messages)
        return resp.content

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        result = self.wrapped_llm._generate(messages, stop=stop, **kwargs)
        return result
