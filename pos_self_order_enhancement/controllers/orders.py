# -*- coding: utf-8 -*-
import re

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import MissingError
from odoo.tools import consteq

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


class PosSelfOrderControllerEnh(PosSelfOrderController):
    """Override order processing to implement payment gate for pay-per-order mode.

    In 'each' (pay-per-order) mode, orders are created as draft but POS/KDS
    notifications are suppressed until payment is confirmed. This matches
    industry standard where payment is a gate before kitchen starts cooking.
    """

    @http.route("/pos-self-order/process-order/<device_type>/", auth="public", type="json", website=True)
    def process_order(self, order, access_token, table_identifier, device_type):
        return self.process_order_args(order, access_token, table_identifier, device_type, **{})

    @http.route("/pos-self-order/process-order-args/<device_type>/", auth="public", type="json", website=True)
    def process_order_args(self, order, access_token, table_identifier, device_type, **kwargs):
        is_takeaway = order.get('takeaway')
        pos_config, table = self._verify_authorization(access_token, table_identifier, is_takeaway)
        pos_session = pos_config.current_session_id
        is_each_mode = pos_config.self_ordering_pay_after == 'each'

        # ── Build order reference (same as base) ──
        ir_sequence_session = pos_config.env['ir.sequence'].with_context(
            company_id=pos_config.company_id.id
        ).next_by_code(f'pos.order_{pos_session.id}')
        sequence_number = order.get('sequence_number')
        if not sequence_number:
            sequence_number = re.findall(r'\d+', ir_sequence_session)[0]
        order_reference = self._generate_unique_id(
            pos_session.id, pos_config.id, sequence_number, device_type
        )
        fiscal_position = (
            pos_config.takeaway_fp_id
            if is_takeaway
            else pos_config.default_fiscal_position_id
        )

        if 'picking_type_id' in order:
            del order['picking_type_id']

        order['name'] = order_reference
        order['pos_reference'] = order_reference
        order['sequence_number'] = sequence_number
        order['user_id'] = request.session.uid
        order['date_order'] = str(fields.Datetime.now())
        order['fiscal_position_id'] = fiscal_position.id if fiscal_position else False

        # ── Create order ──
        # In "each" mode, suppress ALL POS notifications during sync_from_ui.
        # Two flags needed:
        #   - preparation=True: suppresses base point_of_sale notify_synchronisation (line 1133)
        #   - suppress_self_order_notification=True: suppresses pos_self_order _send_notification
        order_model = pos_config.env['pos.order'].sudo().with_company(pos_config.company_id.id)
        if is_each_mode:
            order_model = order_model.with_context(
                suppress_self_order_notification=True,
                preparation=True,
            )
        results = order_model.sync_from_ui([order])
        line_ids = pos_config.env['pos.order.line'].browse(
            [line['id'] for line in results['pos.order.line']]
        )
        order_ids = pos_config.env['pos.order'].browse(
            [o['id'] for o in results['pos.order']]
        )

        self._verify_line_price(line_ids, pos_config)

        amount_total, amount_untaxed = self._get_order_prices(order_ids.lines)
        order_ids.write({
            'state': 'paid' if amount_total == 0 else 'draft',
            'amount_tax': amount_total - amount_untaxed,
            'amount_total': amount_total,
        })

        if amount_total == 0:
            order_ids._process_saved_order(False)

        # ── Payment gate: suppress notification for pay-per-order ──
        if is_each_mode and amount_total > 0:
            order_ids.write({'self_order_payment_status': 'pending_online'})
            # Do NOT call send_table_count_notification — order stays invisible
            # to POS until payment is confirmed or customer selects counter payment
        else:
            order_ids.send_table_count_notification(order_ids.mapped('table_id'))

        return self._generate_return_values(order_ids, pos_config)

    @http.route('/pos-self-order/select-counter-payment', auth='public', type='json', website=True)
    def select_counter_payment(self, access_token, order_id, order_access_token):
        """Customer chose to pay at counter — make order visible to POS cashier.

        This is called when the customer clicks "Pay at Counter" on the payment
        page. The order becomes visible to the POS cashier who can then process
        the payment and send the order to kitchen.
        """
        pos_config = self._verify_pos_config(access_token)
        order = pos_config.env['pos.order'].sudo().browse(order_id)

        if not order.exists() or not consteq(order.access_token, order_access_token):
            raise MissingError(_("Order not found"))

        order.write({'self_order_payment_status': 'pending_counter'})

        # Now notify POS so cashier can see and process the order.
        # notify_synchronisation triggers POS to sync/load the order data;
        # ORDER_STATE_CHANGED alone is not enough.
        for config in order.config_id:
            config.notify_synchronisation(
                config.current_session_id.id,
                0
            )
            config._notify('ORDER_STATE_CHANGED', {})
        order.send_table_count_notification(order.mapped('table_id'))

        return {'success': True}

    @http.route('/pos-self-order/save-einvoice-data', auth='public', type='json', website=True)
    def save_einvoice_data(self, access_token, order_id, order_access_token,
                           carrier_type='print', carrier_num='', love_code='', buyer_tax_id='',
                           b2b_print=True):
        """Save customer's e-invoice carrier preferences before payment.

        Called from the self-order payment page so the auto-issuance trigger
        (in payment_transaction.py) knows which carrier type to use.
        """
        pos_config = self._verify_pos_config(access_token)
        order = pos_config.env['pos.order'].sudo().browse(order_id)

        if not order.exists() or not consteq(order.access_token, order_access_token):
            raise MissingError(_("Order not found"))

        # Validate carrier_type
        allowed_types = ('cloud', 'print', 'mobile', 'donation', 'b2b')
        if carrier_type not in allowed_types:
            carrier_type = 'cloud'

        # Validate conditional fields
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
            'tw_b2b_print': bool(b2b_print) if carrier_type == 'b2b' else True,
        })

        return {'success': True}
