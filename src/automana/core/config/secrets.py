from pathlib import Path
import os

def read_secret(name: str) -> str | None:
    """
    Read a Docker secret from /run/secrets/<name>.
    Falls back to env var <NAME> if not running in Docker.
    """
    secret_path = Path("/run/secrets") / name
    if secret_path.exists():
        return secret_path.read_text().strip()
    return os.getenv(name.upper())