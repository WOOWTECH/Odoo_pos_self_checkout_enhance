# True Decoupling: Remove ecpay_invoice_tw Hard Dependency

**Date:** 2026-05-07
**Status:** Approved

## Problem

`__manifest__.py` lists `ecpay_invoice_tw` in `depends`, forcing Odoo to
install the ECPay module (and its SDK / Python dependencies) on every
deployment — even when the operator does not need Taiwan e-invoicing.

## Goal

Make `ecpay_invoice_tw` **optional**. The module installs and runs without
it. When ecpay IS installed, e-invoice features appear automatically.

## Design Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Decoupling strategy | **A — Fully hidden**: all e-invoice UI invisible when ecpay absent |
| 2 | `ecpay_invoice_id` field | **A — Change to Integer**: drop Many2one to `uniform.invoice` |
| 3 | SDK import protection | **C — Helper + guard**: `_ensure_ecpay_sdk()` combines detection and import |
| 4 | Frontend JS handling | **A — Existing guard sufficient**: `ecpay_einvoice_enabled` is False when ecpay absent |
| 5 | Config UI visibility | **B — Hide entire section**: computed `is_ecpay_installed` field + XML invisible |
| 6 | Database migration | **B — Write pre-migration**: DROP FK constraint before ORM converts field type |

## Files to Modify (7 files)

### 1. `__manifest__.py`
- Remove `ecpay_invoice_tw` from `depends`
- Bump version to `18.0.1.4.0`

### 2. `models/pos_order.py`
- `ecpay_invoice_id`: `Many2one('uniform.invoice')` → `fields.Integer`
- New helper: `_ensure_ecpay_sdk()` — try-import EcpayInvoice, return (class, None) or (None, error_dict)
- New helper: `_get_ecpay_invoice_record()` — browse uniform.invoice by ID with KeyError guard
- Guard added to: `action_issue_einvoice()`, `_pos_query_invoice_info()`, `action_void_einvoice()`, `get_einvoice_print_html()`
- `action_lookup_tax_id()` — no change needed (calls government API, not ecpay)

### 3. `models/pos_config.py`
- New computed field: `is_ecpay_installed` (checks ir.module.module)
- Add to `_load_pos_self_data_fields` and pos data fields for frontend access

### 4. `models/payment_transaction.py`
- `_auto_issue_einvoice()` — add try/except around `action_issue_einvoice()` call

### 5. `views/pos_config_einvoice_view.xml`
- Add `invisible="not is_ecpay_installed"` to outer `<setting>` element

### 6. `migrations/18.0.1.4.0/pre-migration.py`
- DROP CONSTRAINT IF EXISTS `pos_order_ecpay_invoice_id_fkey`

### 7. `.gitignore` (already done)

## Files NOT Modified
- All JS/XML frontend files (existing `ecpay_einvoice_enabled` guard is sufficient)
- `controllers/orders.py` (save-einvoice-data writes to pos.order fields, no ecpay import)
- `vendor/escpos_min.py` (pure ESC/POS printing, no ecpay reference)

## Migration Path

1. Operator upgrades module → pre-migration drops FK constraint
2. ORM sees `ecpay_invoice_id` changed from Many2one to Integer → column type already integer, no data loss
3. If ecpay is installed: `is_ecpay_installed=True`, all UI visible, SDK imports succeed
4. If ecpay is NOT installed: `is_ecpay_installed=False`, UI hidden, SDK guards return structured errors
