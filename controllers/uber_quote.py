# -*- coding: utf-8 -*-
import logging
import threading
import time
from collections import deque

from werkzeug.exceptions import Unauthorized

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
        return {
            'success': True,
            'fee': result.get('fee'),
            'currency': result.get('currency'),
            'estimated_pickup_minutes': result.get('estimated_pickup_minutes'),
            'quote_id': result.get('quote_id'),
        }
