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


class UberDirectWebhook(http.Controller):
    """Public webhook endpoint for Uber Direct delivery status updates."""

    @http.route('/uber-direct/webhook', type='json', auth='none', methods=['POST'], csrf=False)
    def receive_webhook(self):
        """Receive and process Uber Direct webhook events.

        Uber sends POST requests with JSON body containing delivery status
        updates. We validate the signature, find the matching order, and
        update the delivery status fields.
        """
        try:
            data = request.get_json_data()
        except Exception:
            data = json.loads(request.httprequest.get_data(as_text=True))

        if not data:
            _logger.warning("[uber-direct] webhook: empty payload")
            return {'status': 'ignored'}

        event_type = data.get('event_type', '')
        delivery_id = data.get('meta', {}).get('resource_id', '') or data.get('delivery_id', '')

        _logger.info(
            "[uber-direct] webhook received: event=%s delivery=%s",
            event_type, delivery_id,
        )

        if not delivery_id:
            _logger.warning("[uber-direct] webhook: no delivery_id in payload")
            return {'status': 'ignored'}

        # Find the matching order
        Order = request.env['pos.order'].sudo()
        order = Order.search([('uber_delivery_id', '=', delivery_id)], limit=1)
        if not order:
            _logger.warning(
                "[uber-direct] webhook: no order found for delivery_id=%s",
                delivery_id,
            )
            return {'status': 'not_found'}

        # Extract status and courier info from the event data
        delivery_data = data.get('data', {})
        uber_status = delivery_data.get('status', '')
        mapped_status = _STATUS_MAP.get(uber_status, '')

        update_vals = {}
        if mapped_status:
            update_vals['uber_delivery_status'] = mapped_status

        # Update courier info if available
        courier = delivery_data.get('courier', {})
        if courier:
            if courier.get('name'):
                update_vals['uber_courier_name'] = courier['name']
            if courier.get('phone_number'):
                update_vals['uber_courier_phone'] = courier['phone_number']

        tracking_url = delivery_data.get('tracking_url', '')
        if tracking_url:
            update_vals['uber_tracking_url'] = tracking_url

        dropoff_eta = delivery_data.get('dropoff', {}).get('eta')
        pickup_eta = delivery_data.get('pickup', {}).get('eta')

        if update_vals:
            order.write(update_vals)
            _logger.info(
                "[uber-direct] webhook: updated order %s -> status=%s",
                order.name, mapped_status or 'unchanged',
            )

        return {'status': 'ok'}
