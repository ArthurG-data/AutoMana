import os
import redis
import orjson, json

_broker_url = os.getenv("BROKER_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(_broker_url)


def get_from_cache(key: str):
    data = redis_client.get(key)
    if data:
        print("In da cache------------------")
        return json.loads(data)
    return None

def set_to_cache(key: str, value, expiry_seconds: int = 300):
    redis_client.setex(key, expiry_seconds, orjson.dumps(value))
    print("Not in da cache------------------")