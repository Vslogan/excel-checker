from __future__ import annotations

import io
import json
import unittest
from email.message import Message
from typing import Self
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from excel_checker.errors import ActionError
from excel_checker.http_client import UrllibHttpClient


class FakeResponse:
    def __init__(self, body: bytes, status: int = 201) -> None:
        self._body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = "application/json; charset=utf-8"

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class UrllibHttpClientTests(unittest.TestCase):
    def test_json_request_and_response_with_millisecond_timeout(self) -> None:
        response = FakeResponse(b'{"accepted": true}')
        client = UrllibHttpClient()
        with patch(
            "excel_checker.http_client.urllib.request.urlopen", return_value=response
        ) as open_url:
            result = client.request(
                method="POST",
                url="https://example.test/api",
                headers={"X-Test": "yes"},
                body={"id": 7},
                timeout_ms=2500,
            )

        request = open_url.call_args.args[0]
        self.assertIsInstance(request, Request)
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.data, json.dumps({"id": 7}, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(request.get_header("Content-type"), "application/json; charset=utf-8")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 2.5)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.body, {"accepted": True})

    def test_http_error_is_reported_and_body_is_included(self) -> None:
        error = HTTPError(
            "https://example.test/api",
            504,
            "Gateway Timeout",
            hdrs=None,
            fp=io.BytesIO(b"upstream timeout"),
        )
        with (
            patch("excel_checker.http_client.urllib.request.urlopen", side_effect=error),
            self.assertRaisesRegex(ActionError, "状态码 504.*upstream timeout"),
        ):
            UrllibHttpClient().request(
                method="GET",
                url="https://example.test/api",
                headers={},
                body=None,
                timeout_ms=100,
            )

    def test_incomplete_url_is_rejected_before_network_access(self) -> None:
        with self.assertRaisesRegex(ActionError, "完整的 http:// 或 https://"):
            UrllibHttpClient().request(
                method="GET",
                url="example.test/path",
                headers={},
                body=None,
                timeout_ms=100,
            )


if __name__ == "__main__":
    unittest.main()
