# Changelog

All notable changes to this add-on will be documented here.

## 0.1.0 — 2026-04-16

Initial release.

- `POST /print` endpoint with Bearer-token authentication.
- `GET /status` unauthenticated health endpoint.
- Bundled `escpos_min.py` driver (raster bitmap, GS v 0, full cut).
- Alpine 3.19 + Python 3.11 base; Flask 3.x, Pillow 10.x.
- `host_network: true` so a single add-on instance can serve every
  printer on the LAN (printer IP is per-request, not per-config).
- Paper widths 58 mm and 80 mm supported.
