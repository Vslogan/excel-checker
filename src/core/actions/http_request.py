"""HTTP request action implementation."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional, Union

import requests

from src.core.actions.base import ActionResult, BaseAction
from src.core.context import ExecutionContext, UIDelegate, extract_path_value


def parse_timeout_seconds(val: Any, default: float = 10.0) -> float:
    """Parse timeout value in ms, s, or plain number."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        # If > 100, assume ms
        return val / 1000.0 if val >= 100 else float(val)
    if isinstance(val, str):
        cleaned = val.replace(",", "").strip().lower()
        if cleaned.endswith("ms"):
            num = re.findall(r"[\d.]+", cleaned)
            return float(num[0]) / 1000.0 if num else default
        elif cleaned.endswith("s"):
            num = re.findall(r"[\d.]+", cleaned)
            return float(num[0]) if num else default
        else:
            num = re.findall(r"[\d.]+", cleaned)
            if num:
                f = float(num[0])
                return f / 1000.0 if f >= 100 else f
    return default


class HttpRequestAction(BaseAction):
    """Action to send synchronous HTTP requests and extract callback variables."""

    action_type = "http_request"
    display_name = "发网络请求"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.method = (
            self.config.get("method")
            or self.config.get("方法")
            or "GET"
        ).upper()
        self.url = (
            self.config.get("url")
            or self.config.get("URL")
            or ""
        )
        self.headers = (
            self.config.get("headers")
            or self.config.get("header")
            or self.config.get("请求头")
            or {}
        )
        self.body = (
            self.config.get("body")
            or self.config.get("请求体")
            or None
        )
        self.timeout = (
            self.config.get("timeout")
            or self.config.get("超时时间")
            or 10000
        )
        self.callback = (
            self.config.get("callback")
            or self.config.get("回调处理")
            or {}
        )

    def execute(self, context: ExecutionContext, ui_delegate: UIDelegate) -> ActionResult:
        # Interpolate URL
        rendered_url = context.render_template(self.url).strip()
        if not rendered_url.startswith("http://") and not rendered_url.startswith("https://"):
            rendered_url = "https://" + rendered_url

        # Parse & interpolate headers
        rendered_headers: Dict[str, str] = {}
        if isinstance(self.headers, str):
            try:
                parsed_h = json.loads(context.render_template(self.headers))
                if isinstance(parsed_h, dict):
                    rendered_headers = {str(k): str(v) for k, v in parsed_h.items()}
            except Exception:
                rendered_headers = {}
        elif isinstance(self.headers, dict):
            for k, v in self.headers.items():
                rendered_k = str(context.render_template(k))
                rendered_v = str(context.render_template(v))
                rendered_headers[rendered_k] = rendered_v

        # Parse & interpolate body
        data_payload = None
        json_payload = None
        if self.body is not None:
            if isinstance(self.body, (dict, list)):
                json_payload = context.render_template(self.body)
            elif isinstance(self.body, str):
                rendered_body = context.render_template(self.body)
                # Try parsing as JSON first
                try:
                    json_payload = json.loads(rendered_body)
                except Exception:
                    data_payload = rendered_body

        timeout_sec = parse_timeout_seconds(self.timeout)

        ui_delegate.log(f"[HttpRequest] Sending {self.method} to {rendered_url} (timeout={timeout_sec}s)...")

        # Determine SSL verify path
        verify_arg: Union[bool, str] = True
        if os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
            verify_arg = "/etc/ssl/certs/ca-certificates.crt"
        if "verify" in self.config:
            verify_arg = self.config["verify"]

        try:
            resp = requests.request(
                method=self.method,
                url=rendered_url,
                headers=rendered_headers,
                data=data_payload,
                json=json_payload,
                timeout=timeout_sec,
                verify=verify_arg,
            )
            ui_delegate.log(f"[HttpRequest] Response code: {resp.status_code}")

            # Parse response
            resp_data: Any = None
            try:
                resp_data = resp.json()
            except Exception:
                resp_data = resp.text

            # Execute callback extractions if present
            if self.callback and isinstance(self.callback, dict):
                for var_name, path_expr in self.callback.items():
                    rendered_path = context.render_template(path_expr)
                    extracted = extract_path_value(resp_data, rendered_path)
                    context.set_var(var_name, extracted)
                    ui_delegate.log(f"[HttpRequest Callback] Extracted '{rendered_path}' -> {var_name} = {extracted}")

            # Also set default response variables in context for convenience
            context.set_var("_last_response", resp_data)
            context.set_var("_last_status", resp.status_code)

            if not resp.ok:
                err = f"HTTP 请求返回错误状态码 {resp.status_code}: {resp.text[:200]}"
                ui_delegate.log(f"[HttpRequest Warn] {err}")
                return ActionResult.fail(err)

            return ActionResult.ok(resp_data)

        except requests.exceptions.Timeout:
            err = f"HTTP 请求超时 (超过 {timeout_sec} 秒)"
            ui_delegate.log(f"[HttpRequest Error] {err}")
            return ActionResult.fail(err)
        except Exception as e:
            err = f"HTTP 请求发生异常: {str(e)}"
            ui_delegate.log(f"[HttpRequest Error] {err}")
            return ActionResult.fail(err)
