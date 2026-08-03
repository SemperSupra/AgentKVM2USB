from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2

from epiphan_sdk import EpiphanKVM_SDK


def api_response(method: str, target: str, body: bytes, sdk: EpiphanKVM_SDK) -> tuple[int, dict]:
    parsed = urlparse(target)
    query = parse_qs(parsed.query)
    path = parsed.path.rstrip("/") or "/"

    try:
        if method == "GET" and path == "/status":
            return 200, sdk.get_status()
        if method == "GET" and path == "/health":
            include_mi00 = _truthy(query.get("include_mi00", ["0"])[0])
            return 200, sdk.get_device_health(include_mi00=include_mi00)
        if method == "GET" and path == "/macros":
            return 200, {"macros": sdk.list_macros()}
        if method == "GET" and path == "/frame":
            include_image = _truthy(query.get("include_image", ["0"])[0])
            return 200, _frame_response(sdk, include_image=include_image)
        if method == "POST" and path == "/macro":
            payload = _json_body(body)
            return 200, sdk.run_macro(payload.get("script", ""), dry_run=bool(payload.get("dry_run", False)))
        if method == "POST" and path == "/named-macro":
            payload = _json_body(body)
            return 200, sdk.run_named_macro(payload.get("name", ""), dry_run=bool(payload.get("dry_run", False)))
        if method == "POST" and path == "/macro/validate":
            payload = _json_body(body)
            return 200, sdk.validate_macro(payload.get("script", ""))
    except json.JSONDecodeError as exc:
        return 400, {"error": f"invalid JSON: {exc}"}
    except Exception as exc:
        return 500, {"error": str(exc)}

    return 404, {"error": "not found"}


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _json_body(body: bytes) -> dict:
    if not body:
        return {}
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise json.JSONDecodeError("expected JSON object", body.decode("utf-8"), 0)
    return data


def _frame_response(sdk: EpiphanKVM_SDK, include_image: bool = False) -> dict:
    frame = sdk.get_processed_frame()
    if frame is None:
        return {"available": False, "shape": None}

    response = {
        "available": True,
        "shape": list(frame.shape),
    }
    if include_image:
        ok, encoded = cv2.imencode(".jpg", frame)
        if ok:
            response["jpeg_base64"] = base64.b64encode(encoded.tobytes()).decode("ascii")
        else:
            response["jpeg_base64"] = None
            response["error"] = "JPEG encoding failed"
    return response


class AgentApiServer:
    def __init__(self, sdk: EpiphanKVM_SDK, host: str = "127.0.0.1", port: int = 8765):
        self.sdk = sdk
        self.host = host
        self.port = int(port)
        self.httpd = ThreadingHTTPServer((self.host, self.port), self._handler_class())

    def _handler_class(self):
        sdk = self.sdk

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self._send(*api_response("GET", self.path, b"", sdk))

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or 0)
                self._send(*api_response("POST", self.path, self.rfile.read(length), sdk))

            def log_message(self, format, *args):
                return

            def _send(self, status: int, payload: dict):
                data = json.dumps(payload, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler

    def serve_forever(self):
        self.httpd.serve_forever()

    def shutdown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
