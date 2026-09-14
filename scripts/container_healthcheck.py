"""Small, secret-free health probe for the backend container."""

import json
import sys
from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    try:
        with urlopen("http://127.0.0.1:8000/api/v1/health", timeout=3) as response:
            if not 200 <= response.status < 300:
                return 1
            payload = json.load(response)
        count = payload.get("collection_count")
        if payload.get("status") != "ready" or not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            return 1
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
