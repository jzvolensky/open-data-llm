from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

CHUNK = 65536


class DownloadTooLargeError(Exception):
    """Raised when a download exceeds the configured size limit."""


class HttpClient:
    """Thin httpx wrapper with a descriptive UA, retries and streaming downloads."""

    def __init__(
        self,
        base_url: str = "",
        user_agent: str = "open-data-llm/0.1",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout,
            follow_redirects=True,
            transport=httpx.HTTPTransport(retries=max_retries),
        )

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> Any:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                response = self._client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:  # noqa: PERF203
                last = exc
                time.sleep(0.5 * (attempt + 1))
        assert last is not None
        raise last

    def head(self, url: str) -> httpx.Response:
        return self._client.head(url)

    def download(self, url: str, dest: Path, max_bytes: int | None = None) -> int:
        """Stream ``url`` to ``dest``. Aborts and removes the file if too large."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            declared = response.headers.get("content-length")
            if max_bytes and declared and int(declared) > max_bytes:
                raise DownloadTooLargeError(
                    f"declared {declared} bytes > limit {max_bytes}"
                )
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK):
                    written += len(chunk)
                    if max_bytes and written > max_bytes:
                        handle.close()
                        dest.unlink(missing_ok=True)
                        raise DownloadTooLargeError(f"streamed past limit {max_bytes}")
                    handle.write(chunk)
        return written

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
