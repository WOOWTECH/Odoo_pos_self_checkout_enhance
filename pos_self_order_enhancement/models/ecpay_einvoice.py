"""ECPay e-invoice API wrapper for POS integration.

Adapted from Odoo's l10n_tw_edi_ecpay/utils.py — uses AES-CBC-128
encryption with explicit credentials (no company_id dependency).

Public API:
    issue_b2c(config, order, carrier_type, carrier_num, love_code)
    issue_b2b(config, order, buyer_tax_id)
    void_invoice(config, invoice_no, invoice_date, reason)
    check_barcode(config, barcode)
    check_love_code(config, love_code)
"""
import base64
import datetime
import json
import logging
import urllib.parse

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_logger = logging.getLogger(__name__)

PRODUCTION_URL = "https://einvoice.ecpay.com.tw/"
STAGING_URL = "https://einvoice-stage.ecpay.com.tw/"
TIMEOUT = 20

# ECPay staging test credentials (MerchantID 2000132)
DEFAULT_STAGING_MERCHANT_ID = "2000132"
DEFAULT_STAGING_HASH_KEY = "ejCk326UnaZWKisg"
DEFAULT_STAGING_HASH_IV = "q9jcZX8Ib9LM8wYk"


# ── AES-CBC encryption helpers ────────────────────────

def _encrypt(data, cipher):
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data.encode("utf-8")) + padder.finalize()
    encryptor = cipher.encryptor()
    return encryptor.update(padded_data) + encryptor.finalize()


def _decrypt(data, cipher):
    decryptor = cipher.decryptor()
    decrypted_data = decryptor.update(base64.b64decode(data)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(decrypted_data) + unpadder.finalize()


# ── Core API call ─────────────────────────────────────

def call_einvoice_api(endpoint, json_data, merchant_id, hash_key, hash_iv,
                      is_staging=True, is_b2b=False):
    """Call ECPay e-invoice API with AES-CBC encrypted payload.

    :param endpoint: e.g. "/Issue", "/Invalid", "/CheckBarcode"
    :param json_data: dict payload to encrypt
    :param merchant_id: ECPay MerchantID
    :param hash_key: 16-byte AES key
    :param hash_iv: 16-byte AES IV
    :param is_staging: use staging URL
    :param is_b2b: use B2BInvoice path instead of B2CInvoice
    :returns: dict with API response (includes RtnCode, RtnMsg, etc.)
    """
    base_url = STAGING_URL if is_staging else PRODUCTION_URL
    request_url = base_url + ("B2BInvoice" if is_b2b else "B2CInvoice")

    try:
        cipher = Cipher(
            algorithms.AES(hash_key.encode('utf-8')),
            modes.CBC(hash_iv.encode('utf-8')),
        )
        urlencode_data = urllib.parse.quote(json.dumps(json_data))
        encrypted_data = _encrypt(urlencode_data, cipher)
        json_body = {
            "MerchantID": merchant_id,
            "RqHeader": {
                "Timestamp": round(datetime.datetime.now().timestamp()),
            },
            "Data": base64.b64encode(encrypted_data).decode('utf-8'),
        }

        _logger.info("ECPay e-invoice → %s%s", request_url, endpoint)
        response = requests.post(
            request_url + endpoint, json=json_body, timeout=TIMEOUT,
        )
        response_json = response.json()

        if response.status_code != 200:
            return {"RtnCode": 0, "RtnMsg": f"HTTP {response.status_code}: {response_json.get('TransMsg', '')}"}

        if not response_json.get("Data"):
            return {"RtnCode": 0, "RtnMsg": f"ECPay error: {response_json.get('TransMsg', '')}, code={response_json.get('TransCode', '')}"}

        decrypted = _decrypt(response_json["Data"], cipher)
        result = json.loads(urllib.parse.unquote(decrypted))
        _logger.info("ECPay e-invoice ← RtnCode=%s RtnMsg=%s", result.get("RtnCode"), result.get("RtnMsg"))
        return result

    except ValueError as e:
        msg = str(e)
        if "key" in msg:
            return {"RtnCode": 0, "RtnMsg": "Invalid HashKey. Check ECPay configuration."}
        if "IV" in msg:
            return {"RtnCode": 0, "RtnMsg": "Invalid HashIV. Check ECPay configuration."}
        return {"RtnCode": 0, "RtnMsg": f"ECPay API error: {msg}"}
    except requests.RequestException as e:
        _logger.warning("ECPay e-invoice network error: %s", e)
        return {"RtnCode": 0, "RtnMsg": f"Network error: {e}"}
    except Exception as e:
        _logger.exception("ECPay e-invoice unexpected error")
        return {"RtnCode": 0, "RtnMsg": f"Unexpected error: {e}"}


# ── Credential helpers ────────────────────────────────

def _get_creds(config):
    """Extract ECPay credentials from pos.config, falling back to staging defaults."""
    is_staging = config.ecpay_einvoice_env != 'prod'
    merchant_id = config.ecpay_einvoice_merchant_id or DEFAULT_STAGING_MERCHANT_ID
    hash_key = config.ecpay_einvoice_hash_key or DEFAULT_STAGING_HASH_KEY
    hash_iv = config.ecpay_einvoice_hash_iv or DEFAULT_STAGING_HASH_IV
    return merchant_id, hash_key, hash_iv, is_staging


def _carrier_type_code(carrier_type):
    """Map internal carrier_type to ECPay CarrierType code."""
    return {
        'mobile': '3',
        'donation': '',
        'print': '',
        'b2b': '',
    }.get(carrier_type, '')


def _build_item(seq, line):
    """Build an ECPay Items entry from a pos.order.line."""
    return {
        "ItemSeq": seq,
        "ItemName": (line.full_product_name or line.product_id.name or "Item")[:100],
        "ItemCount": line.qty,
        "ItemWord": "份",
        "ItemPrice": round(line.price_unit, 2),
        "ItemTaxType": "1",
        "ItemAmount": round(line.price_subtotal_incl, 2),
    }


# ── Public API ────────────────────────────────────────

def issue_b2c(config, order, carrier_type, carrier_num='', love_code=''):
    """Issue a B2C e-invoice via ECPay API.

    :param config: pos.config record
    :param order: pos.order record
    :param carrier_type: 'print' | 'mobile' | 'donation'
    :param carrier_num: e.g. '/ABC+123' for mobile barcode
    :param love_code: charity code for donation
    :returns: dict with RtnCode, InvoiceNo, RandomNumber, QRCode_Left, etc.
    """
    merchant_id, hash_key, hash_iv, is_staging = _get_creds(config)
    partner = order.partner_id

    # Determine print flag and donation flag
    is_donation = carrier_type == 'donation'
    print_flag = "1" if carrier_type == 'print' else "0"

    # Build unique relate number: use order ID + timestamp to ensure uniqueness
    # ECPay requires alphanumeric, max 30 chars, must be unique per merchant
    import re
    base = re.sub(r'[^A-Za-z0-9]', '', order.pos_reference or order.name or '')
    ts = str(int(datetime.datetime.now().timestamp()))[-8:]
    relate_number = (base[:21] + ts)[:30]

    items = [_build_item(i, line) for i, line in enumerate(order.lines, 1)]
    if not items:
        return {"RtnCode": 0, "RtnMsg": "Order has no lines"}

    payload = {
        "MerchantID": merchant_id,
        "RelateNumber": relate_number,
        "CustomerIdentifier": "",
        "CustomerName": (partner.name if partner else "顧客")[:60],
        "CustomerAddr": (partner.contact_address_complete if partner else "N/A")[:200],
        "CustomerEmail": (partner.email if partner else "noreply@pos.local")[:200],
        "CustomerPhone": (partner.phone or partner.mobile if partner else "")[:20],
        "ClearanceMark": "",
        "Print": print_flag,
        "Donation": "1" if is_donation else "0",
        "LoveCode": (love_code or "")[:7] if is_donation else "",
        "CarrierType": _carrier_type_code(carrier_type),
        "CarrierNum": carrier_num if carrier_type == 'mobile' else "",
        "TaxType": "1",
        "SalesAmount": int(round(order.amount_total)),
        "InvType": "07",
        "vat": "1",
        "Items": items,
    }

    return call_einvoice_api("/Issue", payload, merchant_id, hash_key, hash_iv,
                             is_staging=is_staging, is_b2b=False)


def issue_b2b(config, order, buyer_tax_id):
    """Issue a B2B e-invoice via ECPay API.

    :param config: pos.config record
    :param order: pos.order record
    :param buyer_tax_id: 8-digit 統一編號
    :returns: dict with RtnCode, InvoiceNo, etc.
    """
    merchant_id, hash_key, hash_iv, is_staging = _get_creds(config)
    partner = order.partner_id

    import re
    base = re.sub(r'[^A-Za-z0-9]', '', order.pos_reference or order.name or '')
    ts = str(int(datetime.datetime.now().timestamp()))[-8:]
    relate_number = (base[:21] + ts)[:30]

    # B2C endpoint with CustomerIdentifier set (ECPay treats it as B2B-style)
    items = [_build_item(i, line) for i, line in enumerate(order.lines, 1)]
    if not items:
        return {"RtnCode": 0, "RtnMsg": "Order has no lines"}

    payload = {
        "MerchantID": merchant_id,
        "RelateNumber": relate_number,
        "CustomerIdentifier": buyer_tax_id[:8],
        "CustomerName": (partner.name if partner else "顧客")[:60],
        "CustomerAddr": (partner.contact_address_complete if partner else "N/A")[:200],
        "CustomerEmail": (partner.email if partner else "noreply@pos.local")[:200],
        "CustomerPhone": (partner.phone or partner.mobile if partner else "")[:20],
        "ClearanceMark": "",
        "Print": "1",
        "Donation": "0",
        "LoveCode": "",
        "CarrierType": "",
        "CarrierNum": "",
        "TaxType": "1",
        "SalesAmount": int(round(order.amount_total)),
        "InvType": "07",
        "vat": "1",
        "Items": items,
    }

    return call_einvoice_api("/Issue", payload, merchant_id, hash_key, hash_iv,
                             is_staging=is_staging, is_b2b=False)


def void_invoice(config, invoice_no, invoice_date, reason=''):
    """Void a previously issued e-invoice.

    :param config: pos.config record
    :param invoice_no: e.g. "AB12345678"
    :param invoice_date: "YYYY-MM-DD HH:MM:SS" format
    :param reason: reason for voiding
    :returns: dict with RtnCode
    """
    merchant_id, hash_key, hash_iv, is_staging = _get_creds(config)

    payload = {
        "MerchantID": merchant_id,
        "InvoiceNo": invoice_no,
        "InvoiceDate": invoice_date,
        "Reason": (reason or "POS order voided")[:200],
    }

    return call_einvoice_api("/Invalid", payload, merchant_id, hash_key, hash_iv,
                             is_staging=is_staging, is_b2b=False)


def check_barcode(config, barcode):
    """Validate a mobile barcode (手機條碼) via ECPay API.

    :returns: True if valid, False otherwise
    """
    merchant_id, hash_key, hash_iv, is_staging = _get_creds(config)
    payload = {"MerchantID": merchant_id, "BarCode": barcode}
    result = call_einvoice_api("/CheckBarcode", payload, merchant_id, hash_key, hash_iv,
                               is_staging=is_staging, is_b2b=False)
    return result.get("RtnCode") == 1 and result.get("IsExist") == "Y"


def check_love_code(config, love_code):
    """Validate a charity love code (愛心碼) via ECPay API.

    :returns: True if valid, False otherwise
    """
    merchant_id, hash_key, hash_iv, is_staging = _get_creds(config)
    payload = {"MerchantID": merchant_id, "LoveCode": love_code}
    result = call_einvoice_api("/CheckLoveCode", payload, merchant_id, hash_key, hash_iv,
                               is_staging=is_staging, is_b2b=False)
    return result.get("RtnCode") == 1 and result.get("IsExist") == "Y"
