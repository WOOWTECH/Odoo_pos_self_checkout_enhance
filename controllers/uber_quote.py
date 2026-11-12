# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import json
import logging
import math
import threading
import time
from collections import deque

from werkzeug.exceptions import BadRequest, Unauthorized

from odoo import http
from odoo.http import request

from .utils import safe_token_eq

_logger = logging.getLogger(__name__)

# Upper bound for the customer-supplied drop-off address.
MAX_DROPOFF_ADDRESS_LENGTH = 300

# In-process throttle (per worker process): quotes per sliding window.
QUOTE_WINDOW_SECONDS = 60
QUOTE_LIMIT_PER_CONFIG = 60
QUOTE_LIMIT_PER_CLIENT = 20
_QUOTE_MAX_KEYS = 10000

_quote_hits = {}
_quote_lock = threading.Lock()

GENERIC_QUOTE_ERROR = '無法取得外送報價，請確認地址或稍後再試'
THROTTLED_QUOTE_ERROR = '查詢過於頻繁，請稍後再試'
QUOTE_TTL_SECONDS = 600


def _quote_key(env):
    secret = env['ir.config_parameter'].sudo().get_param('database.secret')
    if not secret:
        raise RuntimeError('Database signing secret is unavailable')
    return hmac.new(secret.encode(), b'pos-self-uber-direct-quote-v1', hashlib.sha256).digest()


def _address_digest(address):
    return hashlib.sha256(address.strip().encode('utf-8')).hexdigest()


def _sign_quote(env, config, address, result, now=None):
    """Issue an opaque receipt for the exact Uber quote and destination."""
    fee = result.get('fee')
    quote_id = result.get('quote_id')
    currency = result.get('currency')
    if (isinstance(fee, bool) or not isinstance(fee, (int, float))
            or not math.isfinite(fee) or fee < 0
            or not isinstance(quote_id, str) or not quote_id or len(quote_id) > 128
            or currency != config.currency_id.name):
        raise ValueError('Invalid Uber quote')
    payload = {'v': 1, 'c': config.id, 'a': _address_digest(address),
               'f': fee, 'u': currency, 'q': quote_id,
               'e': int(time.time() if now is None else now) + QUOTE_TTL_SECONDS}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()).rstrip(b'=')
    signature = hmac.new(_quote_key(env), body, hashlib.sha256).hexdigest().encode()
    return (body + b'.' + signature).decode('ascii')


def verify_quote_receipt(env, config, address, receipt, now=None):
    """Return trusted quote details or raise BadRequest for a stale/tampered quote."""
    if not isinstance(receipt, str) or len(receipt) > 512 or not address or len(address) > MAX_DROPOFF_ADDRESS_LENGTH:
        raise BadRequest('Invalid delivery quote')
    try:
        body, supplied = receipt.encode('ascii').split(b'.', 1)
        expected = hmac.new(_quote_key(env), body, hashlib.sha256).hexdigest().encode()
        if not hmac.compare_digest(supplied, expected):
            raise ValueError('signature mismatch')
        payload = json.loads(base64.urlsafe_b64decode(body + b'=' * (-len(body) % 4)))
        current = int(time.time() if now is None else now)
        fee = payload['f']
        if (payload['v'] != 1 or payload['c'] != config.id
                or payload['a'] != _address_digest(address)
                or payload['u'] != config.currency_id.name
                or payload['e'] < current or payload['e'] > current + QUOTE_TTL_SECONDS
                or isinstance(fee, bool) or not isinstance(fee, (int, float))
                or not math.isfinite(fee) or fee < 0
                or not isinstance(payload['q'], str) or not payload['q']):
            raise ValueError('invalid quote')
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise BadRequest('Invalid delivery quote') from None
    return {'fee': fee, 'currency': payload['u'], 'quote_id': payload['q']}


def _quote_throttled(keys_limits, now=None):
    """Sliding-window counter. Returns True when any key is over its limit.

    A request is only counted when it is allowed, so a throttled client
    does not keep extending its own ban.
    """
    now = time.monotonic() if now is None else now
    cutoff = now - QUOTE_WINDOW_SECONDS
    with _quote_lock:
        if len(_quote_hits) > _QUOTE_MAX_KEYS:
            for key in [k for k, hits in _quote_hits.items() if not hits or hits[-1] < cutoff]:
                del _quote_hits[key]
        buckets = []
        for key, limit in keys_limits:
            hits = _quote_hits.setdefault(key, deque())
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return True
            buckets.append(hits)
        for hits in buckets:
            hits.append(now)
    return False


class UberDirectQuote(http.Controller):
    """Public endpoint for self-order customers to get delivery quotes."""

    @staticmethod
    def _verify_quote_config(access_token, config_id=None):
        """Same gate as core pos_self_order ``_verify_pos_config``.

        The caller must hold the self-order access token of an active
        mobile/kiosk config (the token printed in the table QR / kiosk URL).
        """
        if not access_token or not isinstance(access_token, str):
            raise Unauthorized("Invalid access token")
        config_sudo = request.env['pos.config'].sudo().search(
            [('access_token', '=', access_token)], limit=1,
        )
        if (
            not config_sudo
            or not safe_token_eq(config_sudo.access_token, access_token)
            or config_sudo.self_ordering_mode not in ('mobile', 'kiosk')
            or not config_sudo.has_active_session
        ):
            raise Unauthorized("Invalid access token")
        if config_id not in (None, False, ''):
            try:
                if int(config_id) != config_sudo.id:
                    raise Unauthorized("Invalid access token")
            except (TypeError, ValueError):
                raise Unauthorized("Invalid access token")
        return config_sudo

    @http.route('/pos-self/uber-direct/quote', type='json', auth='public', methods=['POST'], csrf=False)
    def get_delivery_quote(self, access_token=None, dropoff_address=None, config_id=None,
                           dropoff_name='Customer', dropoff_phone=''):
        """Get an Uber Direct delivery quote.

        :param access_token: pos.config self-order access token
        :param dropoff_address: Customer delivery address string
        :param config_id: pos.config id (optional, must match the token)
        :param dropoff_name: Customer name (optional)
        :param dropoff_phone: Customer phone (optional)
        :returns: dict with fee, currency, estimated_minutes, quote_id, or error
        """
        config = self._verify_quote_config(access_token, config_id)
        if not config.uber_direct_enabled:
            return {'success': False, 'error': 'Uber Direct is not enabled'}

        if not isinstance(dropoff_address, str):
            return {'success': False, 'error': GENERIC_QUOTE_ERROR}
        dropoff_address = dropoff_address.strip()
        if not dropoff_address or len(dropoff_address) > MAX_DROPOFF_ADDRESS_LENGTH:
            return {'success': False, 'error': GENERIC_QUOTE_ERROR}

        client = request.httprequest.remote_addr or 'unknown'
        if _quote_throttled([
            (('config', config.id), QUOTE_LIMIT_PER_CONFIG),
            (('client', config.id, client), QUOTE_LIMIT_PER_CLIENT),
        ]):
            _logger.warning("[uber-direct] quote throttled for config %s", config.id)
            return {'success': False, 'error': THROTTLED_QUOTE_ERROR}

        UberDirect = request.env['uber.direct'].sudo()
        result = UberDirect._get_quote(
            config,
            pickup_address=config.uber_direct_pickup_address,
            dropoff_address=dropoff_address,
        )
        if not result.get('success'):
            # Details (Uber's raw response) are logged by _get_quote; never
            # hand them to the anonymous caller.
            return {'success': False, 'error': GENERIC_QUOTE_ERROR}
        try:
            receipt = _sign_quote(request.env, config, dropoff_address, result)
        except ValueError:
            _logger.warning('[uber-direct] invalid quote from provider for config %s', config.id)
            return {'success': False, 'error': GENERIC_QUOTE_ERROR}
        return {
            'success': True,
            'fee': result.get('fee'),
            'currency': result.get('currency'),
            'estimated_pickup_minutes': result.get('estimated_pickup_minutes'),
            'quote_id': receipt,
        }
