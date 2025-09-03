import json
from fastapi import UploadFile

async def decode_json_input(file: bytes) -> dict:
    try:
        #decode bytes
        decoded_content = file.decode("utf-8")
        data = json.loads(decoded_content)
        return data 
    except Exception as e:
        return [f"Error: {str(e)}"]