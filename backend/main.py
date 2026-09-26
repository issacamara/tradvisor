"""FastAPI application entry point for the packaged API runtime."""

from fastapi import FastAPI

app = FastAPI(title="Tradvisor API", version="0.13.0")


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
