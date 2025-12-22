"""
Alfred V2 - Simple HTTP server for health checks.

This is used by Railway for health monitoring.
In the future, this could be expanded to a full API.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

from alfred import __version__


class HealthHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/health":
            self._send_json(200, {
                "status": "healthy",
                "version": __version__,
                "service": "alfred-v2",
            })
        else:
            self._send_json(404, {"error": "Not found"})

    def _send_json(self, status: int, data: dict[str, Any]) -> None:
        """Send a JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass


def run_server(port: int | None = None) -> None:
    """Run the health check server."""
    import os
    # Railway sets PORT environment variable
    if port is None:
        port = int(os.environ.get("PORT", 8000))
    
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Alfred health server running on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()

