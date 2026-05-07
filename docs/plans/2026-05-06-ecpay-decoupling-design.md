# ECPay Decoupling Design: pos_einvoice_bridge

## Goal

Decouple `pos_self_order_enhancement` from `ecpay_invoice_tw` so the POS
module can be installed independently without any Taiwan e-invoice
dependency. A new bridge module `pos_einvoice_bridge` holds all
integration logic. Customers who need e-invoices install the bridge;
those who don't simply skip it.

## Dependency Graph

```
ecpay_invoice_tw          pos_self_order_enhancement
     ^                            ^
     |                            |
     +---- pos_einvoice_bridge ---+
```

## Repo Structure

```
Odoo_pos_self_checkout_enhance/
  pos_self_order_enhancement/    (existing, cleaned)
  pos_einvoice_bridge/           (new)
```

Both modules live in the same GitHub repo as sibling directories.

---

## What Moves to pos_einvoice_bridge

### Python Models

**pos_config.py** (extend `pos.config`):
- `ecpay_einvoice_enabled` Boolean field
- `ecpay_seller_tax_id` Char related field
- `einvoice_printer_id` Many2one field
- Override `_load_pos_self_data_fields()` to append these 3 fields

**pos_order.py** (extend `pos.order`):
- `ecpay_invoice_id` Many2one -> `uniform.invoice`
- 12 `tw_` fields (tw_invoice_number, tw_carrier_type, tw_carrier_num,
  tw_love_code, tw_buyer_tax_id, tw_buyer_name, tw_b2b_print,
  tw_invoice_status, tw_qrcode_left, tw_qrcode_right, tw_pos_barcode,
  tw_invoice_random_code)
- `_EINVOICE_PROTECTED_FIELDS` constant
- `sync_from_ui()` override for field protection
- `action_issue_einvoice()` - ECPay SDK issue flow
- `_pos_query_invoice_info()` - ECPay SDK query
- `action_void_einvoice()` - ECPay SDK void
- `get_einvoice_print_html()` - QWeb render for printing

**payment_transaction.py** (extend `payment.transaction`):
- `_auto_issue_einvoice()` method
- Override `_post_process_after_done()` to call it

### Controller

**controllers/orders.py**:
- `/pos-self-order/save-einvoice-data` route (moved as-is)

### Views

**views/pos_config_einvoice_view.xml**:
- POS config form e-invoice settings section (moved as-is, change
  `inherit_id` module prefix if needed)

### Frontend (JS/XML)

**POS cashier assets** (`point_of_sale._assets_pos`):
- `pos/overrides/payment_screen_einvoice.js` - OWL patch on
  PaymentScreen for e-invoice carrier selection + issue flow
- `pos/overrides/payment_screen_einvoice.xml` - t-inherit extending
  PaymentScreenButtons
- `pos/overrides/tw_invoice_receipt.js` - TwInvoiceReceipt OWL
  component
- `pos/pos_store_einvoice.js` - OWL patch on PosStore for
  EINVOICE_PRINT WebSocket listener
- `printer/select_einvoice_printer.js` - printer selection helper

**Self-order assets** (`pos_self_order_enhancement.assets_self_order`):
- `app/pages/payment_page/payment_page_einvoice.js` - OWL patch
  injecting invoiceState, saveInvoiceData(), validateInvoiceData(),
  etc. into PaymentPage
- `app/pages/payment_page/payment_page_einvoice.xml` - t-inherit
  injecting carrier form UI into payment page template

---

## What Gets Removed from pos_self_order_enhancement

### __manifest__.py
- Remove `"ecpay_invoice_tw"` from `depends`
- Remove `"views/pos_config_einvoice_view.xml"` from `data`
- Remove einvoice JS/XML file paths from `assets`

### Python
- `models/pos_config.py`: delete 3 ecpay fields + 2 append lines
- `models/pos_order.py`: delete ecpay_invoice_id + 12 tw_ fields +
  _EINVOICE_PROTECTED_FIELDS + 4 methods (action_issue_einvoice,
  _pos_query_invoice_info, action_void_einvoice,
  get_einvoice_print_html)
- `models/payment_transaction.py`: delete _auto_issue_einvoice() +
  its call site
- `controllers/orders.py`: delete /save-einvoice-data route

### Views
- Delete `views/pos_config_einvoice_view.xml`

### Frontend
- Delete `payment_screen_einvoice.js`, `payment_screen_einvoice.xml`
- Delete `tw_invoice_receipt.js`
- Delete `select_einvoice_printer.js`
- `pos_store.js`: remove EINVOICE_PRINT listener + related imports
- `payment_page.js`: remove invoiceState, showEinvoiceForm,
  setCarrierType, validateInvoiceData, onTaxIdInput, saveInvoiceData,
  and saveInvoiceData() calls in payment flows
- `payment_page.xml`: remove einvoice-settings div block

---

## Risk Points

1. **pos_store.js partial edit**: must preserve non-einvoice logic
   (KDS, order sync, etc.) while removing only EINVOICE_PRINT code
2. **payment_page.js partial edit**: must preserve payment flow
   (selectCounterPayment, selectOnlinePayment) while removing
   saveInvoiceData() calls without breaking await chains
3. **__manifest__.py assets**: all deleted file paths must be removed
   from asset declarations to avoid Odoo startup errors
4. **Database migration**: existing installations that upgrade will
   need the bridge module installed to retain their tw_ field data.
   The fields move to a different module but remain on the same
   database table (pos_order), so data is preserved as long as the
   bridge is installed before upgrading.

## Bridge __manifest__.py

```python
{
    "name": "POS E-Invoice Bridge (ECPay)",
    "version": "18.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Integrates ECPay Taiwan e-invoice into POS",
    "depends": ["pos_self_order_enhancement", "ecpay_invoice_tw"],
    "data": [
        "views/pos_config_einvoice_view.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_einvoice_bridge/static/src/printer/**/*",
            "pos_einvoice_bridge/static/src/pos/**/*",
        ],
        "pos_self_order_enhancement.assets_self_order": [
            "pos_einvoice_bridge/static/src/app/**/*",
        ],
    },
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
```
