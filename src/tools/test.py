# pip install openai 

from openai import OpenAI 

client = OpenAI(
	base_url = "https://pft5zl5q5itiv1pe.us-east-1.aws.endpoints.huggingface.cloud/v1/",
	api_key = "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"
)

chat_completion = client.chat.completions.create(
	# model="/repository/DeepSeekCoder.F16.gguf",
	model="/repository/DeepSeekCoder.F16.gguf",
	messages=[{"role": "user", "content": "Hello world!"}]
)
# chat_completion = client.chat.completions.create(
# 	model = 
# 	inputs = "Hello world!"
# )
# ChatCompletion(id='chatcmpl-HprpbXx898gnBtNMSI40UTGCWjobpEoA', choices=[Choice(finish_reason='stop', index=0, logprobs=None, message=ChatCompletionMessage(content='Hello! How can I assist you today?\n', refusal=None, role='assistant', annotations=None, audio=None, function_call=None, tool_calls=None))], created=1761838107, model='/repository/DeepSeekCoder.F16.gguf', object='chat.completion', service_tier=None, system_fingerprint='b6830-f8f071fad', usage=CompletionUsage(completion_tokens=11, prompt_tokens=13, total_tokens=24, completion_tokens_details=None, prompt_tokens_details=None), timings={'cache_n': 0, 'prompt_n': 13, 'prompt_ms': 60.063, 'prompt_per_token_ms': 4.620230769230769, 'prompt_per_second': 216.43940529111097, 'predicted_n': 11, 'predicted_ms': 522.772, 'predicted_per_token_ms': 47.524727272727276, 'predicted_per_second': 21.04167782513218})
print(chat_completion.choices[0].message.content)

# for message in chat_completion:
# 	# print(message.choices[0].delta.content, end = "")
# 	print(message[0])