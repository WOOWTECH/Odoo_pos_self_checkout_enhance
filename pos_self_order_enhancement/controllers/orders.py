# -*- coding: utf-8 -*-
import re

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import MissingError
from odoo.tools import consteq

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


class PosSelfOrderControllerEnh(PosSelfOrderController):
    """Override order processing to implement payment gate for self-order.

    All self-order modes (meal + each) apply a payment gate:
    - Orders are created as draft with self_order_payment_status='pending_online'
    - POS is notified immediately (staff can see the order)
    - Kitchen (KDS/printer) is blocked until payment is confirmed
    - Meal mode: auto-fires to kitchen after payment
    - Each mode: staff manually fires to kitchen after payment
    """

    @http.route("/pos-self-order/process-order/<device_type>/", auth="public", type="json", website=True)
    def process_order(self, order, access_token, table_identifier, device_type):
        return self.process_order_args(order, access_token, table_identifier, device_type, **{})

    @http.route("/pos-self-order/process-order-args/<device_type>/", auth="public", type="json", website=True)
    def process_order_args(self, order, access_token, table_identifier, device_type, **kwargs):
        is_takeaway = order.get('takeaway')
        pos_config, table = self._verify_authorization(access_token, table_identifier, is_takeaway)
        pos_session = pos_config.current_session_id

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
        # preparation=True suppresses base point_of_sale notify_synchronisation
        # during sync_from_ui. We send our own notification after setting payment gate.
        order_model = pos_config.env['pos.order'].sudo().with_company(pos_config.company_id.id)
        order_model = order_model.with_context(preparation=True)
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

        # ── Payment gate: apply to ALL self-order modes ──
        if amount_total > 0:
            order_ids.write({'self_order_payment_status': 'pending_online'})

        # Notify POS so staff can see the order (but kitchen is blocked
        # by mark_sent_to_kitchen guard until payment is confirmed)
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

