import redis
import orjson, json

redis_client = redis.Redis(host='localhost', port=6379, db=0)


def get_from_cache(key: str):
    data = redis_client.get(key)
    if data:
        print("In da cache------------------")
        return json.loads(data)
    return None

def set_to_cache(key: str, value, expiry_seconds: int = 300):
    redis_client.setex(key, expiry_seconds, orjson.dumps(value))
    print("Not in da cache------------------")