# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class UberDirectQuote(http.Controller):
    """Public endpoint for self-order customers to get delivery quotes."""

    @http.route('/pos-self/uber-direct/quote', type='json', auth='public', methods=['POST'], csrf=False)
    def get_delivery_quote(self, config_id, dropoff_address, dropoff_name='Customer', dropoff_phone=''):
        """Get an Uber Direct delivery quote.

        :param config_id: pos.config id
        :param dropoff_address: Customer delivery address string
        :param dropoff_name: Customer name (optional)
        :param dropoff_phone: Customer phone (optional)
        :returns: dict with fee, currency, estimated_minutes, quote_id, or error
        """
        config = request.env['pos.config'].sudo().browse(int(config_id)).exists()
        if not config or not config.uber_direct_enabled:
            return {'success': False, 'error': 'Uber Direct is not enabled'}

        UberDirect = request.env['uber.direct'].sudo()
        result = UberDirect._get_quote(
            config,
            pickup_address=config.uber_direct_pickup_address,
            dropoff_address=dropoff_address,
        )
        return result
