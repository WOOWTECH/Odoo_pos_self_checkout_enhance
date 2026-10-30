#!/usr/bin/env python3
"""Seed test data for POS self-order decoupling test on port 9102.

Creates: company, products, POS config with self-order enabled,
opens a POS session.
"""
import xmlrpc.client
import sys

URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:9102'
DB = 'odoopostestnoecpay'
USER = 'admin'
PASS = 'admin'

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PASS, {})
if not uid:
    print("ERROR: authentication failed")
    sys.exit(1)
print(f"Authenticated as uid={uid}")

models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def call(model, method, *args, **kw):
    return models.execute_kw(DB, uid, PASS, model, method, list(args), kw)


# 1. Create product category
cat_ids = call('pos.category', 'search', [('name', '=', 'Test Category')])
if not cat_ids:
    cat_id = call('pos.category', 'create', {'name': 'Test Category'})
    print(f"Created pos.category id={cat_id}")
else:
    cat_id = cat_ids[0]
    print(f"pos.category exists id={cat_id}")


# 2. Create products
products = [
    {'name': '珍珠奶茶', 'list_price': 60.0, 'type': 'consu',
     'available_in_pos': True, 'pos_categ_ids': [(6, 0, [cat_id])]},
    {'name': '鹹酥雞', 'list_price': 80.0, 'type': 'consu',
     'available_in_pos': True, 'pos_categ_ids': [(6, 0, [cat_id])]},
    {'name': '滷肉飯', 'list_price': 50.0, 'type': 'consu',
     'available_in_pos': True, 'pos_categ_ids': [(6, 0, [cat_id])]},
]
prod_ids = []
for p in products:
    existing = call('product.template', 'search', [('name', '=', p['name'])])
    if existing:
        prod_ids.append(existing[0])
        print(f"Product '{p['name']}' exists id={existing[0]}")
    else:
        pid = call('product.template', 'create', p)
        prod_ids.append(pid)
        print(f"Created product '{p['name']}' id={pid}")


# 3. Find or configure POS config
pos_configs = call('pos.config', 'search', [])
if pos_configs:
    config_id = pos_configs[0]
    print(f"Using existing pos.config id={config_id}")
else:
    config_id = call('pos.config', 'create', {'name': 'Test POS'})
    print(f"Created pos.config id={config_id}")

# Enable self-order on the config
lang_id = call('res.lang', 'search', [('code', '=', 'en_US')], limit=1)
call('pos.config', 'write', [config_id], {
    'self_ordering_mode': 'mobile',
    'self_ordering_default_language_id': lang_id[0] if lang_id else False,
    'self_ordering_pay_after': 'each',
})
print(f"Enabled self-order mobile mode on config {config_id}")

# 4. Add a cash journal / payment method if needed
journals = call('pos.payment.method', 'search', [])
if not journals:
    # find cash journal
    cash_journal = call('account.journal', 'search', [('type', '=', 'cash')], limit=1)
    if cash_journal:
        pm_id = call('pos.payment.method', 'create', {
            'name': 'Cash',
            'journal_id': cash_journal[0],
        })
        print(f"Created payment method id={pm_id}")

# 5. Open POS session
sessions = call('pos.session', 'search', [
    ('config_id', '=', config_id),
    ('state', '=', 'opened'),
])
if sessions:
    print(f"POS session already open: id={sessions[0]}")
else:
    try:
        session_id = call('pos.session', 'create', {
            'config_id': config_id,
            'user_id': uid,
        })
        print(f"Opened POS session id={session_id}")
    except Exception as e:
        print(f"WARNING: Could not open POS session: {e}")

# 6. Verify is_ecpay_installed
config_data = call('pos.config', 'read', [config_id], fields=['is_ecpay_installed', 'ecpay_einvoice_enabled'])
print(f"\nPOS Config state:")
print(f"  is_ecpay_installed = {config_data[0]['is_ecpay_installed']}")
print(f"  ecpay_einvoice_enabled = {config_data[0]['ecpay_einvoice_enabled']}")

print("\n=== Seed complete ===")
