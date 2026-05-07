# ECPay Decoupling Test Plan

## Environments

| | Port 9102 (NEW) | Port 9101 (EXISTING) |
|---|---|---|
| **addons** | `pos_self_order_enhancement` only | Full: pos_self_order_enhancement + ecpay_invoice_tw + pos_einvoice_bridge |
| **purpose** | Verify POS works without ecpay | Verify e-invoice logic not broken by refactor |
| **init** | Shell script: create containers → install module → XML-RPC seed data | Existing data, no rebuild |

## Test Matrix

### 9102 — No ECPay (T1–T5)

| ID | Test | Method | Pass Criteria |
|----|------|--------|---------------|
| T1 | Module install + Odoo boots | Shell (`--stop-after-init`) | Exit 0, no ERROR in logs |
| T2 | `is_ecpay_installed` = False, e-invoice settings hidden | XML-RPC + Playwright | Field returns False; settings section not in DOM |
| T3 | POS self-order → place order → payment | Playwright | Order created, payment confirmed |
| T4 | Receipt (OrderReceipt) renders correctly | Playwright | Receipt popup shows order lines, total, no crash |
| T5 | `action_issue_einvoice` returns graceful error | XML-RPC | Returns `{'success': False, 'error': 'ecpay_invoice_tw 模組未安裝...'}` |

### 9101 — With ECPay (T6–T9)

| ID | Test | Method | Pass Criteria |
|----|------|--------|---------------|
| T6 | `is_ecpay_installed` = True, e-invoice settings visible | XML-RPC + Playwright | Field returns True; settings section visible in DOM |
| T7 | `_ensure_ecpay_sdk()` returns class | XML-RPC (call via `action_issue_einvoice`) | No ImportError; SDK class loaded |
| T8 | `action_issue_einvoice` reaches SDK init (fails on credentials, not import) | XML-RPC | Error message about credentials, NOT about missing module |
| T9 | `get_einvoice_print_html` with existing invoice record | XML-RPC | Returns `{'html': '<style>...'}` (non-empty HTML) |

## Automation

- **Container setup**: Shell script creates docker-compose for 9102, starts containers, installs module
- **Data seeding**: XML-RPC script creates products, POS config, opens session
- **POS flow tests**: Playwright browser automation
- **Backend API tests**: XML-RPC calls to verify model methods
