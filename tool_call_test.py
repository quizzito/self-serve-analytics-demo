import os
import json
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]

try:
    resp = client.chat.completions.create(
        model="mistralai/mistral-nemotron",
        messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        tools=tools,
    )
    print("SUCCESS")
    print(resp.choices[0].message)
except Exception as e:
    print("FAILED:", e)