#!/usr/bin/env python3
"""Backend tests for no-ecpay environment (port 9102).

T2: is_ecpay_installed=False (already verified by seed)
T5: action_issue_einvoice returns graceful error
"""
import xmlrpc.client
import sys
import json

URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:9102'
DB = 'odoopostestnoecpay'
USER = 'admin'
PASS = 'admin'

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PASS, {})
models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def call(model, method, *args, **kw):
    return models.execute_kw(DB, uid, PASS, model, method, list(args), kw)

print("=" * 60)
print("T2: Verify is_ecpay_installed = False")
print("=" * 60)
config_ids = call('pos.config', 'search', [])
config_data = call('pos.config', 'read', config_ids, fields=['is_ecpay_installed', 'ecpay_einvoice_enabled'])
for c in config_data:
    assert c['is_ecpay_installed'] == False, f"FAIL: is_ecpay_installed should be False, got {c['is_ecpay_installed']}"
    print(f"  pos.config id={c['id']}: is_ecpay_installed={c['is_ecpay_installed']} ✓")
print("T2 PASSED\n")

print("=" * 60)
print("T5: action_issue_einvoice returns graceful error (SDK missing)")
print("=" * 60)
# Find any POS order, or create one
order_ids = call('pos.order', 'search', [], limit=1)
if not order_ids:
    print("  No POS orders found — creating a minimal test order")
    session_ids = call('pos.session', 'search', [('state', '=', 'opened')], limit=1)
    if not session_ids:
        print("  ERROR: no open POS session")
        sys.exit(1)
    order_id = call('pos.order', 'create', {
        'session_id': session_ids[0],
        'lines': [],
        'amount_total': 0,
        'amount_tax': 0,
        'amount_paid': 0,
        'amount_return': 0,
    })
    order_ids = [order_id]
    print(f"  Created pos.order id={order_id}")

# Get the order's config_id and enable einvoice on it
order_data = call('pos.order', 'read', order_ids[:1], fields=['config_id'])
order_config_id = order_data[0]['config_id'][0]
call('pos.config', 'write', [order_config_id], {'ecpay_einvoice_enabled': True})
print(f"  Temporarily enabled ecpay_einvoice on config {order_config_id}")

try:
    result = call('pos.order', 'action_issue_einvoice', order_ids[:1], {'carrier_type': 'print'})
    print(f"  Result: {json.dumps(result, ensure_ascii=False)}")
    if isinstance(result, dict):
        assert result.get('success') == False, f"FAIL: expected success=False"
        assert '模組未安裝' in result.get('error', ''), \
            f"FAIL: expected '模組未安裝' in error, got: {result.get('error')}"
        print(f"  Error message: {result['error']} ✓")
    print("T5 PASSED\n")
except Exception as e:
    err_str = str(e)
    if '模組未安裝' in err_str or 'ecpay_invoice_tw' in err_str:
        print(f"  Got expected error (via exception): {err_str[:200]}")
        print("T5 PASSED (via exception)\n")
    else:
        print(f"  UNEXPECTED ERROR: {err_str[:500]}")
        print("T5 FAILED\n")
        sys.exit(1)
finally:
    # Restore config
    call('pos.config', 'write', [order_config_id], {'ecpay_einvoice_enabled': False})

print("=" * 60)
print("All backend tests PASSED for no-ecpay environment")
print("=" * 60)
