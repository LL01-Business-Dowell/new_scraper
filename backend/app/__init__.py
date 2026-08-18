import sys

try:
    import google.genai._api_client as genai_client

    async def _safe_aclose(self):
        client = getattr(self, "_async_httpx_client", None)
        if client is not None:
            await client.aclose()

    genai_client.BaseApiClient.aclose = _safe_aclose
except (ImportError, AttributeError):
    pass