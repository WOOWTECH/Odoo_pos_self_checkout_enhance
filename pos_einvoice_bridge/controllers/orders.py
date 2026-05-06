# -*- coding: utf-8 -*-
import re

from odoo import http, _
from odoo.http import request
from odoo.exceptions import MissingError
from odoo.tools import consteq

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


class PosSelfOrderEinvoiceController(PosSelfOrderController):
    """E-Invoice endpoints for POS self-order."""

    @http.route('/pos-self-order/save-einvoice-data', auth='public', type='json', website=True)
    def save_einvoice_data(self, access_token, order_id, order_access_token,
                           carrier_type='print', carrier_num='', love_code='', buyer_tax_id='',
                           buyer_name=''):
        """Save customer's e-invoice carrier preferences before payment.

        Called from the self-order payment page so the auto-issuance trigger
        (in payment_transaction.py) knows which carrier type to use.
        """
        pos_config = self._verify_pos_config(access_token)
        order = pos_config.env['pos.order'].sudo().browse(order_id)

        if not order.exists() or not consteq(order.access_token, order_access_token):
            raise MissingError(_("Order not found"))

        # Validate carrier_type (must match Selection field values)
        allowed_types = ('print', 'mobile', 'donation', 'b2b')
        if carrier_type not in allowed_types:
            carrier_type = 'print'

        # Validate required sub-fields for each carrier type
        if carrier_type == 'mobile' and not carrier_num:
            return {'success': False, 'error': '請輸入手機條碼 (Mobile barcode is required)'}
        if carrier_type == 'donation' and not love_code:
            return {'success': False, 'error': '請輸入愛心碼 (Love code is required)'}
        if carrier_type == 'b2b' and not buyer_tax_id:
            return {'success': False, 'error': '請輸入統一編號 (Tax ID is required)'}

        # Validate format of conditional fields
        if carrier_type == 'mobile' and carrier_num:
            if not re.match(r'^/[0-9A-Z+\-.]{7}$', carrier_num):
                return {'success': False, 'error': '手機條碼格式錯誤 (格式: / + 7碼英數字)'}
        if carrier_type == 'donation' and love_code:
            if not re.match(r'^([xX][0-9]{2,6}|[0-9]{3,7})$', love_code):
                return {'success': False, 'error': '愛心碼格式錯誤 (3~7碼數字)'}
        if carrier_type == 'b2b' and buyer_tax_id:
            if not re.match(r'^[0-9]{8}$', buyer_tax_id):
                return {'success': False, 'error': '統一編號格式錯誤 (8碼數字)'}

        order.write({
            'tw_carrier_type': carrier_type,
            'tw_carrier_num': carrier_num if carrier_type == 'mobile' else '',
            'tw_love_code': love_code if carrier_type == 'donation' else '',
            'tw_buyer_tax_id': buyer_tax_id if carrier_type == 'b2b' else '',
            'tw_buyer_name': buyer_name if carrier_type == 'b2b' else '',
        })

        return {'success': True}

    @http.route('/pos-self-order/lookup-tax-id', auth='public', type='json', website=True)
    def lookup_tax_id(self, access_token, tax_id=''):
        """Proxy Taiwan GCIS open data API to look up company name by 統一編號."""
        self._verify_pos_config(access_token)
        PosOrder = request.env['pos.order'].sudo()
        return PosOrder.action_lookup_tax_id(tax_id)
