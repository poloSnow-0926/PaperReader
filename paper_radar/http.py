"""带重试和限速的 HTTP 工具。"""

import time

import httpx

USER_AGENT = "paper-radar/0.1 (personal research tool)"
_client = httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT}, follow_redirects=True)


def request(method: str, url: str, *, retries: int = 6, **kwargs) -> httpx.Response:
    """遇到 429/5xx 时指数退避重试。其他错误直接返回给调用方处理。"""
    delay = 3.0
    for attempt in range(retries):
        try:
            resp = _client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == retries - 1:
                raise
        else:
            if resp.status_code != 429 and resp.status_code < 500:
                return resp
            if attempt == retries - 1:
                return resp
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = max(delay, float(retry_after))
        time.sleep(delay)
        delay = min(delay * 2, 60)
    raise RuntimeError("unreachable")
