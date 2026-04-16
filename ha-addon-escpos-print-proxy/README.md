# ESC/POS Print Proxy — Home Assistant Add-on

Receives print jobs over HTTP from a cloud-hosted Odoo POS and forwards them
to a local-LAN ESC/POS network printer (TCP:9100).

Runs inside Home Assistant as an add-on. Pair with the Cloudflare Tunnel HA
Add-on to expose it to your cloud Odoo without opening any inbound ports on
your router.

## Request / Response Contract

```
POST /print
Authorization: Bearer <api_key>
Content-Type:  application/json

{
  "image_base64": "<base64 JPEG receipt>",
  "printer_ip":   "192.168.1.50",
  "cut":          true,     // optional, default true
  "beep":         false     // optional, default false (accepted for forward-compat)
}
```

Responses:

| Code | Body                                            | Meaning                          |
|------|-------------------------------------------------|----------------------------------|
| 200  | `{"ok": true}`                                  | Printed.                         |
| 400  | `{"ok": false, "error": "..."}`                 | Bad JSON / missing field / bad image. |
| 401  | `{"ok": false, "error": "unauthorized"}`        | Missing or wrong Bearer token.   |
| 502  | `{"ok": false, "error": "printer unreachable"}` | Socket to `printer_ip:9100` failed. |
| 500  | `{"ok": false, "error": "..."}`                 | Unexpected server error.         |

```
GET /status           (unauthenticated — used for tunnel health checks)
```

Returns `{"ok": true, "version": "0.1.0", "uptime_s": 123.4}`.

## Configuration

Set in the add-on's **Configuration** tab:

| Option    | Type    | Default | Notes                                       |
|-----------|---------|---------|---------------------------------------------|
| api_key   | string  | (empty) | **Required.** Generate: `openssl rand -hex 32` |
| port      | int     | 8073    | Port the proxy listens on.                  |
| paper_mm  | 58 or 80| 80      | Default paper width if not in the request.  |

The add-on refuses to start if `api_key` is empty.

## Host network

`host_network: true` so one add-on instance can reach any printer IP on your
LAN. The `printer_ip` field in each request determines where that job goes —
you do **not** have to configure the printer IP in the add-on.

## Setup

Full setup walkthrough (HA installation, Cloudflare Tunnel route, Odoo
printer settings, troubleshooting) lives in `DOCS.md`.

## Contract coupling

This proxy's `/print` shape is the shared contract with the Odoo
`controllers/print_proxy.py` relay path. Changes to the contract must update
both sides in the same commit series.
