"""Configuration for the retrieval-only API."""

SERVICE_NAME = "bis-toys-retrieval-api"

ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

ALLOWED_METHODS = ("GET", "POST")
ALLOWED_HEADERS = ("Content-Type",)
