# -*- coding: utf-8 -*-
"""
HA Add-on: ESC/POS Print Proxy.

A small Flask service that accepts bearer-authenticated print jobs over HTTP
and dispatches them to a local-LAN ESC/POS network printer via TCP:9100.

Runs inside a Home Assistant add-on container. The cloud Odoo server posts
print jobs over HTTPS through Cloudflare Tunnel → this process → printer.

Contract (shared with the Odoo `controllers/print_proxy.py` relay path):

    POST /print
        Authorization: Bearer <api_key>
        Content-Type:  application/json
        Body: {
          "image_base64": "<base64 JPEG receipt>",
          "printer_ip":   "192.168.x.y",
          "cut":  bool (optional, default true),
          "beep": bool (optional, default false, not implemented yet)
        }
        → 200 {"ok": true}
        → 400 {"ok": false, "error": "<reason>"}     malformed / missing fields
        → 401 {"ok": false, "error": "unauthorized"}
        → 502 {"ok": false, "error": "printer unreachable: ..."}
        → 500 {"ok": false, "error": "<exception>"}

    GET /status                    (unauthenticated — used for tunnel health)
        → 200 {"ok": true, "version": "...", "uptime_s": <float>}

Environment (read by run.sh from /data/options.json):
    API_KEY    Shared secret; required.
    PORT       TCP port to bind; default 8073.
    PAPER_MM   Default paper width in mm if not in request (80 or 58); default 80.
"""
import hmac
import logging
import os
import time

from flask import Flask, jsonify, request

from escpos_min import print_image

__version__ = "0.1.0"

_logger = logging.getLogger("escpos_proxy")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

API_KEY = os.environ.get("API_KEY", "").strip()
PORT = int(os.environ.get("PORT", "8073"))
PAPER_MM = int(os.environ.get("PAPER_MM", "80"))
_STARTED_AT = time.time()


def _bearer_ok(auth_header):
    """Constant-time compare of the Bearer token against API_KEY."""
    if not API_KEY:
        # Fail closed: an unconfigured proxy MUST NOT accept jobs.
        return False
    if not auth_header or not auth_header.startswith("Bearer "):
        return False
    given = auth_header[len("Bearer "):].strip()
    return hmac.compare_digest(given, API_KEY)


def create_app():
    app = Flask(__name__)

    @app.get("/status")
    def status():
        return jsonify(
            ok=True,
            version=__version__,
            uptime_s=round(time.time() - _STARTED_AT, 1),
        )

    @app.post("/print")
    def do_print():
        if not _bearer_ok(request.headers.get("Authorization", "")):
            _logger.warning(
                "unauthorized /print from %s",
                request.remote_addr,
            )
            return jsonify(ok=False, error="unauthorized"), 401

        try:
            data = request.get_json(force=True, silent=False) or {}
        except Exception as exc:
            return jsonify(ok=False, error=f"malformed JSON: {exc}"), 400

        image_b64 = data.get("image_base64")
        printer_ip = data.get("printer_ip")
        if not image_b64:
            return jsonify(ok=False, error="missing image_base64"), 400
        if not printer_ip:
            return jsonify(ok=False, error="missing printer_ip"), 400

        paper = int(data.get("paper_width") or PAPER_MM)
        # `cut` and `beep` are accepted but the driver always cuts and doesn't
        # beep; acknowledged here for forward-compat contract stability.
        _ = bool(data.get("cut", True))
        _ = bool(data.get("beep", False))

        _logger.info("dispatch -> %s (paper=%dmm)", printer_ip, paper)
        result = print_image(printer_ip, 9100, image_b64, paper_width=paper, timeout=5)

        if result.get("success"):
            return jsonify(ok=True)
        err = result.get("error") or "unknown error"
        # If the printer TCP socket failed, surface as 502. If the decode/raster
        # failed, it's a client-data problem → 400. The driver differentiates
        # these by error message prefix.
        if err.startswith("printer unreachable"):
            return jsonify(ok=False, error=err), 502
        if err.startswith("decode failed") or err.endswith("is empty"):
            return jsonify(ok=False, error=err), 400
        return jsonify(ok=False, error=err), 500

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover — production entry is run.sh
    if not API_KEY:
        _logger.error("API_KEY is empty — refusing to start. Set it in the add-on options.")
        raise SystemExit(2)
    _logger.info("ESC/POS print proxy %s listening on 0.0.0.0:%d", __version__, PORT)
    app.run(host="0.0.0.0", port=PORT, threaded=True)
