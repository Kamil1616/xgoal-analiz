import json
import os
import time

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance", "cache")

def _ensure_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def _path(key):
    safe = key.replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, safe + ".json")

def get(key, ttl_minutes=60):
    _ensure_dir()
    try:
        p = _path(key)
        if not os.path.exists(p):
            return None
        with open(p, "r") as f:
            data = json.load(f)
        if time.time() - data["ts"] > ttl_minutes * 60:
            return None
        return data["value"]
    except:
        return None

def set(key, value):
    _ensure_dir()
    try:
        p = _path(key)
        with open(p, "w") as f:
            json.dump({"ts": time.time(), "value": value}, f)
    except:
        pass
