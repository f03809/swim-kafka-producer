import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

logger = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    health_path: str = "/health"
    metrics_path: str = "/metrics"

    def log_message(self, format: str, *args: object) -> None:
        logger.debug(format, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == self.health_path:
            body = b'{"status":"ok"}\n'
            self._send(200, body, "application/json")
        elif path == self.metrics_path:
            data = generate_latest(REGISTRY)
            self._send(200, data, CONTENT_TYPE_LATEST)
        else:
            self._send(404, b'{"status":"not found"}\n', "application/json")


class HealthServer:
    def __init__(self, port: int, health_path: str = "/health", metrics_path: str = "/metrics") -> None:
        self._port = port
        _HealthHandler.health_path = health_path
        _HealthHandler.metrics_path = metrics_path
        self._server = ThreadingHTTPServer(("", port), _HealthHandler)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Health server listening on port %s", self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)
