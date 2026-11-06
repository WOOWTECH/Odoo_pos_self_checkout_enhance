# POS Self Order Enhancement

Odoo 18 module that hardens and extends the built-in POS self-ordering
(`pos_self_order`) for real-world restaurant use.

> Traditional Chinese: see [`README.zh-TW.md`](README.zh-TW.md).

## Features

### Ordering UX
- **No customer cancel** — the "Cancel" button is hidden from customer-facing
  screens after submission; staff can still cancel from the POS backend.
- **Continue ordering** — the landing page shows a "Continue Ordering" button
  that lets a customer add items to their existing (unpaid) order instead of
  starting a new one.
- **Pay per Order (Community)** — enables the Enterprise-only "Pay per Order"
  mode on Community. Customers submit multiple orders and settle everything
  at once from "My Orders".
- **Takeaway counter payment (opt-in)** — a `pos.config` setting to let
  self-order takeaway customers pay at the counter instead of online.
  Dine-in customers always see both options.

### Payment gate
- All self-order flows (meal and each) apply a **payment gate** — orders are
  created as `draft` with `self_order_payment_status='pending_online'`, so
  KDS and printers are blocked until payment is confirmed.
- Meal mode: kitchen ticket auto-fires after payment.
- Each mode: staff manually fires courses after payment via Hold & Fire.

### Kitchen printing (network ESC/POS)
- Adds a **`network_escpos`** printer type — direct raw-TCP printing to
  network ESC/POS thermal printers, no IoT Box required.
- Optional **cloud relay** (Home Assistant add-on included under
  `ha-addon-escpos-print-proxy/`) so the shop's printer can be reached from
  a remote Odoo. Provide a Cloudflare tunnel URL and an API key — the
  add-on handles the LAN side.
- **Server-side Pillow rendering** — kitchen tickets are rendered as JPEG
  on the Odoo server for cloud-relay printers. This bypasses browser
  `html-to-image` limitations (CJK font embedding failure, background-tab
  throttling) that produce blank receipts.
- **No duplicate prints** — the server-side path (backend) and the frontend
  fallback (browser via `sendOrderInPreparation`) coordinate through a
  `skip_printer_ids` handoff so cloud printers never receive the same job
  twice. Local-TCP printers keep the frontend fallback.
- Kitchen ticket contents: order reference, print timestamp
  (`YYYY-MM-DD HH:MM:SS`), table (floor + number), takeaway / Uber delivery
  banner + address + courier, order lines with quantity, and per-line notes
  (`customer_note` from kiosk **and** `note` from POS staff), plus the
  order-level `general_note` in a footer.
- Per-printer settings: `escpos_printer_ip`, `escpos_paper_width`
  (80mm / 58mm), `escpos_print_copies` (1–10), `escpos_proxy_url`,
  `escpos_proxy_api_key`, `escpos_printer_label`.
- Backend "Print test page" button on the printer form for end-to-end
  verification of connectivity + copy count.

### Kitchen Display Screen (KDS)
- Browser-based KDS with a shareable public URL and a regenerable access
  token (Configuration → Point of Sale → "Kitchen Display Screen (KDS)").
- Live order updates via WebSocket. Supports Hold & Fire per category so
  courses can be sequenced at the pass.
- Remake / SEND-BACK workflow: when a line is remade the reprinted ticket
  carries a `SEND BACK · <reason>` banner instead of the "New" title.

### Payment integrations
- Compatible with `pos_online_payment` and Odoo's payment module.
- Payment form gets a polish patch: labels never wrap, provider icons are
  constrained to 48x48, and the Cancel button matches the Pay button shape
  — important on kiosk / mobile widths.
- Return-to-ordering shortcut on the payment confirmation page.

### Uber Direct delivery (opt-in per config)
- OAuth 2.0 to the Uber Direct API with automatic token refresh.
- Automatic courier dispatch when a paid order carries a delivery address.
- Kitchen ticket surfaces `*** 外送 ***`, the delivery address (2-line
  truncation), and the courier name once dispatched.
- Delivery status webhook: point the Uber Direct webhook at
  `https://<your-odoo>/uber-direct/webhook` and paste the webhook's
  **Signing Key** (Uber Developer Dashboard > Webhooks) into
  *Webhook Signing Key* on the POS configuration (visible to
  administrators only). Every call is verified (HMAC-SHA256 of the body
  in `x-uber-signature`); **without a signing key all webhook calls are
  rejected with 401** and delivery status / courier details are not
  updated.

## Requirements

- Odoo 18.0 (Community or Enterprise)
- `pos_self_order`, `pos_restaurant` (already in Odoo)
- Optional: `pos_online_payment` for online payment methods
- Optional: Home Assistant Supervisor + Cloudflare tunnel for the ESC/POS
  cloud relay (`ha-addon-escpos-print-proxy/`)

## Installation

1. Clone into your Odoo `addons` directory:
   ```bash
   git clone https://github.com/WOOWTECH/Odoo_pos_self_checkout_enhance.git \
       pos_self_order_enhancement
   ```
2. In Odoo: **Apps → Update Apps List** → search for
   "POS Self Order Enhancement" → **Install**.

## Configuration

Most features are wired automatically. The pieces you might want to touch:

| Where | What | Default |
|-------|------|---------|
| **Configuration → Point of Sale → your PoS** | "Kitchen Display Screen (KDS)" setting | off |
| **Configuration → Point of Sale → your PoS** | "Takeaway Counter Payment" setting | off (takeaway is online-only) |
| **Configuration → Printers → your printer** | `printer_type = "Use a network ESC/POS printer"` | — |
| **Configuration → Printers → your printer** | `Print Copies`, `Paper Width`, `Cloud Relay URL`, `API Key`, `Printer Label` | 1 copy, 80mm |

## Changelog

### 18.0.2.2.1 (security release)
- **Uber Direct webhook:** calls must be signed. Paste the webhook
  *Signing Key* into the POS configuration; without it every webhook call
  is rejected (401) and delivery status / courier details stop updating.
- **ESC/POS printing:** `/pos-escpos/print` and `/pos-escpos/print-order`
  now require Point of Sale user rights and a configured
  `network_escpos` printer (pos.printer record of one of the user's
  companies). Jobs are no longer sent to a bare IP address coming from
  the browser; errors shown in the POS are generic (details in the
  server log).
- **Uber Direct quote:** requires the self-order access token (sent by
  the bundled self-order page), limits address length and is throttled.
- **Self-order processing:** the order payload is sanitized by Odoo's
  core rules; lines with quantity <= 0, empty orders, line commands on
  other orders, client-chosen customers / payments and resends of
  already processed orders are refused. A zero-total order is only
  marked paid when every item is genuinely free.
- **Return to Ordering** link on the payment confirmation page is bound
  to the transaction; old links return 404.
- KDS token checks are constant-time and refuse empty tokens.

## License

LGPL-3

## Author

[WOOWTECH](https://www.woowtech.io)
