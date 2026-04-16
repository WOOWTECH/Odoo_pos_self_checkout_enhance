# Changelog

All notable changes to this add-on will be documented here.

## 0.2.0 — 2026-04-16

- New optional `printer_ip` add-on option. When set, acts as the
  default target printer IP for incoming `/print` requests that
  don't specify one in their JSON body.
- Rationale: lets the cloud Odoo side stay ignorant of the shop's
  LAN topology. The shop operator configures the IP once here,
  when installing the add-on, and the cloud admin only needs to
  fill in the Cloud Relay URL + API key on Odoo's printer form.
- Backward compatible: payload contract unchanged. Requests with
  explicit `printer_ip` still work and override the default.
- Log line `dispatch -> <ip>` now includes `source=payload` or
  `source=addon-default` so the effective IP is diagnosable.

## 0.1.0 — 2026-04-16

Initial release.

- `POST /print` endpoint with Bearer-token authentication.
- `GET /status` unauthenticated health endpoint.
- Bundled `escpos_min.py` driver (raster bitmap, GS v 0, full cut).
- Alpine 3.19 + Python 3.11 base; Flask 3.x, Pillow 10.x.
- `host_network: true` so a single add-on instance can serve every
  printer on the LAN (printer IP is per-request, not per-config).
- Paper widths 58 mm and 80 mm supported.
