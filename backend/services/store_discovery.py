import os
from os import getenv
import openai

value = os.getenv("OPEN_AI") 


def discover_stores_openai(country: str):
    prompt = f"""
You are an expert Magic: The Gathering collector. List 10 reputable online stores that sell MTG singles and products in {country}.
Return a JSON list with keys: name, url, product_types (e.g., singles, boosters), shipping_info.
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response['choices'][0]['message']['content']