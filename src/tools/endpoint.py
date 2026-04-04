# from huggingface_hub import HfApi, list_models

# # Use root method
# models = list_models()

# # Or configure a HfApi client
# hf_api = HfApi(
#     endpoint="https://ph5eo7wv62ydyan0.us-east-1.aws.endpoints.huggingface.cloud", # Can be a Private Hub endpoint.
#     token="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", # Token is not persisted on the machine.
# )
# models = hf_api.list_models()
# print(list(models))

from huggingface_hub import get_inference_endpoint
endpoint = get_inference_endpoint("miha-deepseek-coder-pyranet--crx", token="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")
endpoint.pause()