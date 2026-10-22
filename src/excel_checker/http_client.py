"""Synchronous HTTP transport with JSON decoding and millisecond timeouts."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from .errors import ActionError
from .interfaces import HttpResponse


class UrllibHttpClient:
    """Small dependency-free HTTP client used by the core by default."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Any,
        timeout_ms: float,
    ) -> HttpResponse:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ActionError("请求 URL 必须是完整的 http:// 或 https:// 地址")

        request_headers = dict(headers)
        data: bytes | None
        if body is None:
            data = None
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            try:
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ActionError(f"HTTP body 不能序列化为 JSON：{exc}") from exc
            if not any(key.lower() == "content-type" for key in request_headers):
                request_headers["Content-Type"] = "application/json; charset=utf-8"

        try:
            request = urllib.request.Request(
                url=url,
                data=data,
                headers=request_headers,
                method=method.upper(),
            )
            with urllib.request.urlopen(request, timeout=float(timeout_ms) / 1000.0) as response:
                raw_body = response.read()
                response_headers = {key: value for key, value in response.headers.items()}
                status_code = int(response.status)
                charset = response.headers.get_content_charset() or "utf-8"
        except urllib.error.HTTPError as exc:
            detail = self._decode_body(exc.read(), "utf-8")
            suffix = f"；响应：{detail[:500]}" if detail else ""
            raise ActionError(f"HTTP 请求返回状态码 {exc.code}{suffix}") from exc
        except TimeoutError as exc:
            raise ActionError(f"HTTP 请求超时（{timeout_ms:g} ms）：{url}") from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise ActionError(f"HTTP 请求超时（{timeout_ms:g} ms）：{url}") from exc
            raise ActionError(f"HTTP 请求失败：{reason}") from exc
        except OSError as exc:
            raise ActionError(f"HTTP 请求失败：{exc}") from exc

        decoded = self._decode_body(raw_body, charset)
        if not decoded:
            payload: Any = None
        else:
            try:
                payload = json.loads(decoded)
            except json.JSONDecodeError:
                payload = decoded
        return HttpResponse(status_code=status_code, headers=response_headers, body=payload)

    @staticmethod
    def _decode_body(body: bytes, charset: str) -> str:
        try:
            return body.decode(charset, errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")
