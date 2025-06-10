import json
from fastapi import UploadFile

async def decode_json_input(file: UploadFile)-> dict:
    content = await file.read()
    try:
        #decode bytes
        decoded_content = content.decode("utf-8")
        data = json.loads(decoded_content)
        data= data.get('data')
        return data
    except Exception as e:
        return [f"Error: {str(e)}"]