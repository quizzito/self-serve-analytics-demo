import os
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
)

completion = client.chat.completions.create(
    model="mistralai/mistral-nemotron",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
    temperature=0.6,
    top_p=0.7,
    max_tokens=200,
    stream=False,
)

print(completion.choices[0].message.content)