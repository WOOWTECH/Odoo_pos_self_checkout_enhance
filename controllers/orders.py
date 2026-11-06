# -*- coding: utf-8 -*-
import logging
import re

from odoo import Command, http, fields, _
from odoo.http import request
from odoo.exceptions import MissingError
from odoo.tools import consteq
from werkzeug.exceptions import BadRequest, Unauthorized

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController

_logger = logging.getLogger(__name__)


class PosSelfOrderControllerEnh(PosSelfOrderController):
    """Override order processing to implement payment gate for self-order.

    All self-order modes (meal + each) apply a payment gate:
    - Orders are created as draft with self_order_payment_status='pending_online'
    - POS is notified immediately (staff can see the order)
    - Kitchen (KDS/printer) is blocked until payment is confirmed
    - Meal mode: auto-fires to kitchen after payment
    - Each mode: staff manually fires to kitchen after payment
    """

    @http.route("/pos-self-order/process-order/<device_type>/", auth="public", type="json", website=True, readonly=False)
    def process_order(self, order, access_token, table_identifier, device_type):
        return self.process_order_args(order, access_token, table_identifier, device_type, **{})

    @http.route("/pos-self-order/process-order-args/<device_type>/", auth="public", type="json", website=True, readonly=False)
    def process_order_args(self, order, access_token, table_identifier, device_type, **kwargs):
        is_takeaway = order.get('takeaway')
        # Log entry for post-mortem debugging of kiosk sync failures.
        _logger.info(
            "process_order_args called: table=%s uuid=%s id=%s",
            table_identifier,
            (order.get('uuid') or 'N/A')[:12],
            order.get('id', 'N/A'),
        )
        try:
            pos_config, table = self._verify_authorization(
                access_token, table_identifier, is_takeaway,
            )
        except Exception as e:
            _logger.error("_verify_authorization FAILED: %s", e)
            raise
        pos_session = pos_config.current_session_id
        _logger.info(
            "Authorization OK: config=%s session=%s(%s)",
            pos_config.id, pos_session.id, pos_session.state,
        )

        self._check_existing_order(pos_config, pos_session, order)

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
        order['name'] = order_reference
        order['pos_reference'] = order_reference
        order['sequence_number'] = sequence_number

        # ── Sanitize the client payload exactly like core ──
        # Core `_check_pos_order` keeps only whitelisted order/line fields
        # (drops payment_ids, discount, combo_parent_uuid, ...),
        # forces table_id to the table resolved from `table_identifier`
        # (never the client value) and only lets the client delete lines of
        # its own order. We then add our own stricter checks and re-apply the
        # module-specific values on top of the sanitized dict.
        self._check_foreign_line_commands(pos_config, order)
        safe_data = pos_config.env['pos.order']._check_pos_order(pos_config, order, table)
        if hasattr(self, '_check_records'):
            self._check_records(pos_config, safe_data)
        self._check_line_quantities(safe_data)

        fiscal_position = (
            pos_config.takeaway_fp_id
            if is_takeaway
            else pos_config.default_fiscal_position_id
        )
        safe_data['name'] = order_reference
        safe_data['pos_reference'] = order_reference
        safe_data['sequence_number'] = sequence_number
        safe_data['user_id'] = request.session.uid
        safe_data['date_order'] = str(fields.Datetime.now())
        safe_data['fiscal_position_id'] = fiscal_position.id if fiscal_position else False
        safe_data['session_id'] = pos_session.id
        safe_data['company_id'] = pos_config.company_id.id
        safe_data['table_id'] = table.id if table else False
        # Newer 18.0 cores pass the client partner_id through (and copy that
        # partner's email onto the order). No self-order frontend sets a
        # customer, so an anonymous caller must not attach an arbitrary
        # res.partner to its order.
        safe_data['partner_id'] = False
        safe_data['email'] = order.get('email') if isinstance(order.get('email'), str) else False
        pricelist = pos_config.pricelist_id
        safe_data['pricelist_id'] = pricelist.id if pricelist else False
        # Self-order payloads always come in as draft: the state is decided
        # below from the server-side recomputed amounts.
        safe_data['state'] = 'draft'
        # Missing amounts caused kiosk syncs to fail with cryptic ORM errors.
        for amount_field in ('amount_tax', 'amount_total', 'amount_paid', 'amount_return'):
            if safe_data.get(amount_field) is None:
                safe_data[amount_field] = 0

        # Module-specific order fields set by the self-order frontend
        # (Uber Direct delivery flow).
        for char_field in ('uber_delivery_address', 'uber_quote_id'):
            value = order.get(char_field)
            if value and isinstance(value, str):
                safe_data[char_field] = value[:512]
        delivery_fee = order.get('uber_delivery_fee')
        if isinstance(delivery_fee, (int, float)) and not isinstance(delivery_fee, bool):
            safe_data['uber_delivery_fee'] = max(float(delivery_fee), 0.0)

        # ── Create order ──
        # preparation=True suppresses base point_of_sale notify_synchronisation
        # during sync_from_ui. We send our own notification after setting payment gate.
        order_model = pos_config.env['pos.order'].sudo().with_company(pos_config.company_id.id)
        order_model = order_model.with_context(preparation=True)
        results = order_model.sync_from_ui([safe_data])
        line_ids = pos_config.env['pos.order.line'].browse(
            [line['id'] for line in results['pos.order.line']]
        )
        order_ids = pos_config.env['pos.order'].browse(
            [o['id'] for o in results['pos.order']]
        )

        if not order_ids or order_ids.filtered(lambda o: o.state != 'draft'):
            # sync_from_ui leaves non-draft orders untouched; never go on to
            # rewrite their state / payment status below.
            raise BadRequest("This order has already been processed")
        if not order_ids.lines:
            # The self-order frontend never sends an order without lines.
            raise BadRequest("An order needs at least one line")
        self._check_saved_order_lines(order_ids)
        self._verify_line_price(line_ids, pos_config)

        amount_total, amount_untaxed = self._get_order_prices(order_ids.lines)
        # A zero total is only "free" when every line is genuinely free:
        # positive quantities and a server-recomputed unit price of 0.
        # Anything else (e.g. lines cancelling each other out) goes through
        # the normal online-payment gate.
        currency = pos_config.currency_id
        is_free_order = bool(order_ids.lines) and currency.is_zero(amount_total) and all(
            line.qty > 0 and currency.is_zero(line.price_unit)
            for line in order_ids.lines
        )
        order_ids.write({
            'state': 'paid' if is_free_order else 'draft',
            'amount_tax': amount_total - amount_untaxed,
            'amount_total': amount_total,
        })

        if is_free_order:
            order_ids._process_saved_order(False)
        else:
            # ── Payment gate: apply to ALL self-order modes ──
            order_ids.write({'self_order_payment_status': 'pending_online'})

        # Notify POS so staff can see the order (but kitchen is blocked
        # by mark_sent_to_kitchen guard until payment is confirmed)
        order_ids.send_table_count_notification(order_ids.mapped('table_id'))

        return self._generate_return_values(order_ids, pos_config)

    # ── Payload validation helpers ──

    @staticmethod
    def _check_existing_order(pos_config, pos_session, order):
        """A resend may only target a draft order of this config's session.

        Core self-order never resends a paid order (its frontend starts a
        new one), and sync_from_ui ignores non-draft orders; without this
        check the state/payment-status writes below would reopen a paid
        order. Orders of another config/session are never reachable.
        """
        uuid = order.get('uuid')
        if not uuid:
            return
        if not isinstance(uuid, str):
            raise BadRequest("Invalid order")
        existing_sudo = request.env['pos.order'].sudo().search([('uuid', '=', uuid)], limit=1)
        if not existing_sudo:
            return
        if existing_sudo.config_id != pos_config or existing_sudo.session_id != pos_session:
            raise Unauthorized("Order does not belong to this point of sale")
        if existing_sudo.state != 'draft':
            raise BadRequest("This order has already been processed")

    @staticmethod
    def _get_existing_line_ids(pos_config, order):
        # Same lookup as core `_check_pos_order_lines`.
        existing_order = pos_config.env['pos.order'].search(
            [('uuid', '=', order.get('uuid'))], limit=1,
        )
        return set(existing_order.lines.ids)

    def _check_foreign_line_commands(self, pos_config, order):
        """Reject line commands that target lines of another order.

        Core silently drops DELETE/UNLINK commands on foreign lines but lets
        UPDATE commands through with any line id; a self-order customer may
        only touch the lines of its own order.
        """
        lines = order.get('lines') or []
        if not isinstance(lines, list):
            raise BadRequest("Invalid order lines")
        existing_line_ids = None
        for command in lines:
            if not isinstance(command, (list, tuple)) or not command:
                raise BadRequest("Invalid order lines")
            if command[0] in (Command.UPDATE, Command.DELETE, Command.UNLINK):
                if existing_line_ids is None:
                    existing_line_ids = self._get_existing_line_ids(pos_config, order)
                if len(command) < 2 or command[1] not in existing_line_ids:
                    raise Unauthorized("Order line does not belong to this order")

    @staticmethod
    def _check_line_quantities(safe_data):
        """Every created/updated line must have a strictly positive quantity."""
        for command in safe_data.get('lines', []):
            if command[0] not in (Command.CREATE, Command.UPDATE):
                continue
            qty = command[2].get('qty')
            if (
                not isinstance(qty, (int, float))
                or isinstance(qty, bool)
                or qty <= 0
            ):
                raise BadRequest("Invalid line quantity")

    @staticmethod
    def _check_saved_order_lines(order_ids):
        """Post-sync checks on the stored lines, before prices are recomputed."""
        for line in order_ids.lines:
            if line.combo_parent_id and line.combo_parent_id.order_id != line.order_id:
                raise Unauthorized("Combo line does not belong to this order")
            # Core links combo children by uuid within the order, but the
            # sanitized payload still carries client combo_line_ids ints:
            # never accept a child line from another order.
            if line.combo_line_ids and line.combo_line_ids.order_id != line.order_id:
                raise Unauthorized("Combo line does not belong to this order")
            if line.combo_line_ids and (
                line.price_unit or line.price_subtotal or line.price_subtotal_incl
            ):
                # The combo price is carried by the children (recomputed by
                # core); the parent line itself is always 0, as in the
                # self-order frontend. Never keep a client-supplied amount.
                line.write({
                    'price_unit': 0,
                    'price_subtotal': 0,
                    'price_subtotal_incl': 0,
                })

    @http.route('/pos-self-order/select-counter-payment', auth='public', type='json', website=True, readonly=False)
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

    @http.route('/pos-self-order/save-einvoice-data', auth='public', type='json', website=True, readonly=False)
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
