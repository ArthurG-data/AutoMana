import requests, time
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "ArthurMTGApp/1.0 (contact: guillaume.arthur1@gmail.com)"  # Scryfall asks for this
})

def get(url, **kw):
    # tiny client with naive retry/backoff for 429/5xx, and a mild limiter
    for attempt in range(6):
        r = SESSION.get(url, timeout=60, **kw)
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(2 ** attempt, 10)
            time.sleep(wait)  # backoff
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()