from huggingface_hub import InferenceClient
# ,ChatCompletionOutput, ChatCompletionOutputComplete, ChatCompletionOutputMessage, ChatCompletionOutputUsage

# messages = [{"role": "system", "content": """Implement the Verilog module based on the following description. Assume that signals are positive clock/clk triggered unless otherwise stated."""},
# 			{"role": "user", "content": """Build a circuit with no inputs and one output. That output should always
# drive 0 (or logic low).

# Place the completion of the Verilog module in an XML tag <hdls></hdls>.
# Inside the XML tag, all partial modules constructing the Verilog module, are placed inside a child XML tag <hdl></hdl>.
# In each partial tag, the tag <module_definition></module_definition> is used to place the module definition of that module and
# the tag <module_code></module_code> is used to place the module code of that module.
	
# module TopModule (
#   output out
# );"""}]
# client = InferenceClient(
# 	"nvmthanhhcmus/COMBA-CodeLLama-4bit-53k-Pyranet-GGUF",) #meta-llama/Meta-Llama-3-8B-Instruct
# print(client.chat_completion(messages, 
# 							 max_tokens=2048,
# 							 temperature=0.85*2,
# 							 top_p=0.95,))
# resp.
# resp = ChatCompletionOutput(choices=[ChatCompletionOutputComplete(finish_reason='stop', index=0, message=ChatCompletionOutputMessage(role='assistant', content='The capital of France is Paris.', reasoning=None, tool_call_id=None, tool_calls=None), logprobs=None, content_filter_results={'hate': {'filtered': False}, 'self_harm': {'filtered': False}, 'sexual': {'filtered': False}, 'violence': {'filtered': False}, 'jailbreak': {'filtered': False, 'detected': False}, 'profanity': {'filtered': False, 'detected': False}})], created=1761806469, id='chatcmpl-b44d80838cfc44c2a4ebd4f4ee91b5cb', model='meta-llama/llama-3-8b-instruct', system_fingerprint='', usage=ChatCompletionOutputUsage(completion_tokens=8, prompt_tokens=42, total_tokens=50, prompt_tokens_details=None, completion_tokens_details=None), object='chat.completion')

# resp = ChatCompletionOutput(choices=[ChatCompletionOutputComplete(finish_reason='stop', index=0, message=ChatCompletionOutputMessage(role='assistant', content='The capital of France is Paris.', reasoning=None, tool_call_id=None, tool_calls=None), logprobs=None,)], created=1761806469, id='chatcmpl-b44d80838cfc44c2a4ebd4f4ee91b5cb', model='meta-llama/llama-3-8b-instruct', system_fingerprint='', usage=ChatCompletionOutputUsage(completion_tokens=8, prompt_tokens=42, total_tokens=50))

# print(resp.