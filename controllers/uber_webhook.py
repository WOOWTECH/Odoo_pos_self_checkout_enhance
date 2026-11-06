# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Uber Direct webhook event types we handle
_STATUS_MAP = {
    'pending': 'pending',
    'pickup': 'en_route_pickup',
    'pickup_complete': 'at_pickup',
    'dropoff': 'en_route_dropoff',
    'delivered': 'delivered',
    'canceled': 'cancelled',
    'returned': 'cancelled',
}

# Headers carrying HMAC-SHA256(signing key, raw body) as lowercase hex.
_SIGNATURE_HEADERS = ('X-Uber-Signature', 'X-Postmates-Signature')


def _compute_signature(signing_key, raw_body):
    return hmac.new(signing_key.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()


class UberDirectWebhook(http.Controller):
    """Public webhook endpoint for Uber Direct delivery status updates."""

    @staticmethod
    def _json_response(payload, status=200):
        return request.make_json_response(payload, status=status)

    def _verified_configs(self, raw_body):
        """Return the Uber-enabled pos.config records whose webhook signing
        key produced the signature sent with the request (sudo), or an empty
        recordset. Configs without a signing key never verify."""
        Config = request.env['pos.config'].sudo()
        signatures = [
            request.httprequest.headers.get(header, '').strip().lower()
            for header in _SIGNATURE_HEADERS
        ]
        signatures = [sig for sig in signatures if sig]
        if not signatures:
            return Config
        configs = Config.search([
            ('uber_direct_enabled', '=', True),
            ('uber_direct_webhook_signing_key', '!=', False),
        ])
        matched = Config
        for config in configs:
            expected = _compute_signature(config.uber_direct_webhook_signing_key, raw_body)
            if any(hmac.compare_digest(expected, sig) for sig in signatures):
                matched |= config
        return matched

    @http.route('/uber-direct/webhook', type='http', auth='none', methods=['POST'], csrf=False, save_session=False)
    def receive_webhook(self, **kwargs):
        """Receive and process Uber Direct webhook events.

        Uber signs every webhook with the per-webhook Signing Key: the
        ``x-uber-signature`` (legacy: ``x-postmates-signature``) header is
        the HMAC-SHA256 hex digest of the raw request body. Requests that do
        not verify against the signing key of an Uber-enabled POS config are
        rejected with 401 before any order is looked up or written. Only
        orders of the verified config(s) can be updated, and re-delivered
        events do not rewrite unchanged values.
        """
        raw_body = request.httprequest.get_data(cache=True) or b''

        configs = self._verified_configs(raw_body)
        if not configs:
            _logger.warning("[uber-direct] webhook rejected: missing or invalid signature")
            return self._json_response({'status': 'unauthorized'}, status=401)

        try:
            data = json.loads(raw_body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            _logger.warning("[uber-direct] webhook: invalid JSON payload")
            return self._json_response({'status': 'invalid'}, status=400)

        if not data or not isinstance(data, dict):
            _logger.warning("[uber-direct] webhook: empty payload")
            return self._json_response({'status': 'ignored'})

        meta = data.get('meta') if isinstance(data.get('meta'), dict) else {}
        event_type = data.get('event_type', '') or data.get('kind', '')
        delivery_id = meta.get('resource_id', '') or data.get('delivery_id', '')

        _logger.info(
            "[uber-direct] webhook received: event=%s delivery=%s",
            event_type, delivery_id,
        )

        if not delivery_id or not isinstance(delivery_id, str):
            _logger.warning("[uber-direct] webhook: no delivery_id in payload")
            return self._json_response({'status': 'ignored'})

        # Find the matching order, only among the verified config(s)
        order = request.env['pos.order'].sudo().search([
            ('uber_delivery_id', '=', delivery_id),
            ('config_id', 'in', configs.ids),
        ], limit=1)
        if not order:
            _logger.warning(
                "[uber-direct] webhook: no order found for delivery_id=%s",
                delivery_id,
            )
            return self._json_response({'status': 'not_found'})

        # Extract status and courier info from the event data
        delivery_data = data.get('data') if isinstance(data.get('data'), dict) else {}
        uber_status = delivery_data.get('status', '') or data.get('status', '')
        mapped_status = _STATUS_MAP.get(uber_status, '') if isinstance(uber_status, str) else ''

        update_vals = {}
        if mapped_status:
            update_vals['uber_delivery_status'] = mapped_status

        # Update courier info if available
        courier = delivery_data.get('courier') if isinstance(delivery_data.get('courier'), dict) else {}
        if courier.get('name') and isinstance(courier['name'], str):
            update_vals['uber_courier_name'] = courier['name']
        if courier.get('phone_number') and isinstance(courier['phone_number'], str):
            update_vals['uber_courier_phone'] = courier['phone_number']

        tracking_url = delivery_data.get('tracking_url', '')
        if tracking_url and isinstance(tracking_url, str):
            update_vals['uber_tracking_url'] = tracking_url

        # Idempotency: a re-delivered (identical) event changes nothing.
        update_vals = {
            field: value for field, value in update_vals.items()
            if order[field] != value
        }
        if update_vals:
            order.write(update_vals)
            _logger.info(
                "[uber-direct] webhook: updated order %s -> status=%s",
                order.name, mapped_status or 'unchanged',
            )

        return self._json_response({'status': 'ok'})
