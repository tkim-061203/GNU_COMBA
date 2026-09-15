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
print(chat_completion.choices[0].message.content)

# for message in chat_completion:
# 	# print(message.choices[0].delta.content, end = "")
# 	print(message[0])