from langchain_community.llms import LlamaCpp
import sys
from huggingface_hub import InferenceClient
from openai import OpenAI
from openai.types.chat import ChatCompletion
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams
from typing import Optional
import logging
import openai

# Set the logging level for the 'openai' logger to ERROR or CRITICAL
logging.getLogger("openai").setLevel(logging.ERROR)

# Set the logging level for the 'httpx' logger to ERROR or CRITICAL
# This is often the source of HTTP request/response logs
logging.getLogger("httpx").setLevel(logging.ERROR)

providers = {
	"llamacpp": "LLamaCPPInferenceClient",
	"huggingface": "HuggingFaceInferenceClient",
	"openai": "OpenAiInferenceClient",
	"vllm": "VLLMInferenceClient",
}

default_provider = list(providers.keys())[0]
class InferenceClass():
	def __new__(cls, provider: str, *args, **kwargs):
		print(f"Using provider: {provider}")
		if provider in providers:
			return getattr(sys.modules[__name__],providers[provider])(*args, **kwargs)
		else:
			raise Exception(f"Provider {provider} not supported. Supported providers are: {list(providers.keys())}")

class GeneralInferenceClass():
	def __init__(self, model: str, max_tokens: int, temperature: float, top_p: float, revision: Optional[str]=None):
		self.model = model
		self.max_tokens = max_tokens
		self.temperature = temperature
		self.top_p = top_p
		self.revision = revision
	def invoke(self, prompt: list[str], **kwargs) -> tuple[str, dict]:
		pass
	def free_model(self):
		pass

n_gpu_layers = -1  # The number of layers to put on the GPU. The rest will be on the CPU. If you don't know how many layers there are, you can use -1 to move all to GPU.
n_batch = 512  # Should be between 1 and n_ctx, consider the amount of VRAM in your GPU.
n_ctx=16384,

class LLamaCPPInferenceClient(GeneralInferenceClass):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.llm = LlamaCpp(
			model_path=self.model,
			# model_path="/home/thanh/vllm/GNU_COMBA/src/codellama-7b.Q4_K_M.gguf",
			# model_path="/home/thanh/Downloads/ggml-model-q4_0.gguf",
			n_gpu_layers=n_gpu_layers,
			n_batch=n_batch,
			max_tokens=self.max_tokens,
			n_ctx=n_ctx,
			# callback_manager=callback_manager,
			# verbose=True,  # Verbose is required to pass to the callback manager
			temperature=self.temperature,
			verbose=False
		)
	def invoke(self, prompt: list[str]):

		response : str = self.llm.invoke('\n'.join(prompt))
		return (response, {})
	def free_model(self):
		self.llm.client.close()


class HuggingFaceInferenceClient(GeneralInferenceClass):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		print(f"Loading model from HuggingFace: {self.model}")
		self.llm = InferenceClient(
			model=self.model,
			base_url="https://nb-f8ef48ad-492e-4b6e-8d7c-4544a6bcdc53-8888-sea1.notebook.console.greennode.ai/v1"
		)
	def invoke(self, prompt: list[str]):
		# response : str = self.llm.invoke(prompt)
		messages = [{"role": "user", "content": message} for message in prompt]
		response = self.llm.chat_completion(messages=messages, max_tokens=self.max_tokens, temperature=self.temperature)

		return (response.choices[0].message, 
		  {"completion_tokens": response.usage.completion_tokens,
		 	"prompt_tokens": response.usage.prompt_tokens,
		   "total_tokens": response.usage.total_tokens})

class OpenAiInferenceClient(GeneralInferenceClass):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		token="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"
		base_url="http://localhost:8000/v1/"
		print(f"Loading model from HuggingFace: {self.model}, {base_url}")
		self.llm = OpenAI(
			base_url=base_url,
			api_key="",
			# api_key = "",
		)
		# self.tokenizer = AutoTokenizer.from_pretrained(self.model, token=token)
	def invoke(self, prompt: list[str],**kwargs):
		# response : str = self.llm.invoke(prompt)
		if 'chatArgs' in kwargs:
			messages = kwargs['chatArgs']
		elif 'promptArgs' in kwargs:
			messages = []
			for i in range(len(kwargs['promptArgs'])):
				instruction = kwargs['promptArgs'][i]['instruction']
				messages.append({"role": "user", "content": instruction})
				if 'response' in kwargs['promptArgs'][i]:
					response = kwargs['promptArgs'][i]['response']
					messages.append({"role": "assistant", "content": response})

		else:
			messages = [{"role": "user", "content": message} for message in prompt]
		try:
			response = self.llm.chat.completions.create(
				model=self.model,
				messages=messages,
				max_tokens=self.max_tokens, 
				temperature=self.temperature,
				top_p=self.top_p,
				
				# stop=self.tokenizer.eos_token,
			)
		except openai.OpenAIError as e:
			# openai exceptions (e.g. APIStatusError) are not picklable by dill/multiprocess
			# because their __init__ requires 'response' and 'body' kwargs.
			# Convert to a plain RuntimeError so the worker can relay it to the main process.
			raise RuntimeError(f"OpenAI API error: {type(e).__name__}: {e}") from None

		return (response.choices[0].message.content, 
		  {"completion_tokens": response.usage.completion_tokens,
		 	"prompt_tokens": response.usage.prompt_tokens,
		   "total_tokens": response.usage.total_tokens})
	
class VLLMInferenceClient(GeneralInferenceClass):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		print(f"Loading model from HuggingFace: {self.model}")
		token="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"
		self.llm = LLM(
			model= self.model,
			hf_token= token,
			revision=self.revision
			# api_key = "",
		)
		self.samplingParams = SamplingParams(temperature=self.temperature,
									   max_tokens=self.max_tokens,
									   top_p=self.top_p)
	def invoke(self, prompt: list[str],**kwargs):
		# response : str = self.llm.invoke(prompt)
		if 'chatArgs' in kwargs:
			messages = kwargs['chatArgs']
		elif 'promptArgs' in kwargs:
			messages = []
			for i in range(len(kwargs['promptArgs'])):
				instruction = kwargs['promptArgs'][i]['instruction']
				messages.append({"role": "user", "content": instruction})
				if 'response' in kwargs['promptArgs'][i]:
					response = kwargs['promptArgs'][i]['response']
					messages.append({"role": "assistant", "content": response})

		else:
			messages = [{"role": "user", "content": message} for message in prompt]
		# print(messages)
		# exit(123)
		response = self.llm.chat(
			messages=messages,
			sampling_params=self.samplingParams
			# stop=self.tokenizer.eos_token,
		)
		# response = self.llm.chat_completion(messages=[{"role": "user", "content": prompt}], max_tokens=self.max_tokens, temperature=self.temperature)
		print(response)
		exit()
		return (response.choices[0].message.content, 
		  {"completion_tokens": response.usage.completion_tokens,
		 	"prompt_tokens": response.usage.prompt_tokens,
		   "total_tokens": response.usage.total_tokens})