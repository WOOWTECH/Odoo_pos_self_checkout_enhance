# Changelog

All notable changes to this add-on will be documented here.

## 0.5.0 — 2026-04-21

- Auto-generate API key on first start when `api_key` is left empty.
  The generated key is persisted to addon options via the HA Supervisor
  API and visible in the Configuration tab for copying to Odoo.
- `api_key` is now optional in the schema — no need to generate one
  manually before starting the addon.

## 0.4.1 — 2026-04-17

- Removed redundant global `paper_mm` option from main settings.
  Per-printer `paper_mm` in the `printers` list (added in 0.4.0)
  is now the only way to set paper width. Odoo always sends
  `paper_width` in the relay payload as a fallback (default 80mm).
- Changed per-printer `paper_mm` schema from free-form integer
  (`int?`) to `list(58|80)?` — renders as radio buttons in the
  HA UI, preventing invalid values like `1` or `999`.

## 0.4.0 — 2026-04-17

- Per-label `paper_mm` option in the `printers` list. Kitchen printer
  (80mm) and invoice printer (58mm) can now use different paper widths
  from the same add-on instance.
- Paper width resolution precedence:
  label's `paper_mm` > request's `paper_width` > global `paper_mm`.
- Backward compatible: existing configs without per-label `paper_mm`
  continue to use the request's `paper_width` or the global default.

## 0.3.0 — 2026-04-16

- New optional `printers` list option — `[{label, ip}]` — for shops
  with multiple ESC/POS printers (e.g. `電子統一發票` invoice +
  kitchen). Cloud Odoo sends an optional `printer_label` in the
  request body; this add-on maps it to the right LAN IP.
- Rationale: cloud Odoo admin picks a label (`invoice`, `kitchen`)
  instead of typing a LAN IP. Keeps the "no LAN info in the cloud"
  design principle when scaling beyond one printer.
- Backward compatible: payload contract unchanged. Requests without
  `printer_label` still resolve via `printer_ip` payload field, then
  fall back to the `printer_ip` option default.
- Unknown labels return a 400 with a specific error naming the
  label — prevents silently sending to the wrong printer.
- Resolution precedence: `printer_label` > `printer_ip` (payload) >
  `printer_ip` (add-on default).
- Log line `dispatch -> <ip>` now reports `source=label:<name>` when
  the label path was taken.

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
