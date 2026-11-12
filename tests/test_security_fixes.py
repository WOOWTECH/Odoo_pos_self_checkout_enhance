# -*- coding: utf-8 -*-
"""Regression tests for the 2026-11-06 security sweep fixes."""
import hashlib
import hmac
import json
from unittest.mock import patch
from uuid import uuid4

from odoo import Command
from odoo.tests.common import HttpCase, JsonRpcException, new_test_user, tagged

from odoo.addons.pos_self_order_enhancement.controllers import uber_quote as uber_quote_ctrl

ESCPOS_SEND_BYTES = 'odoo.addons.pos_self_order_enhancement.vendor.escpos_min._send_bytes'
UBER_GET_QUOTE = 'odoo.addons.pos_self_order_enhancement.models.uber_direct.UberDirect._get_quote'


@tagged('post_install', '-at_install')
class SelfOrderSecurityCommon(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_user = new_test_user(
            cls.env, login='sec_pos_user',
            groups='base.group_user,point_of_sale.group_pos_user',
        )
        cls.internal_user = new_test_user(cls.env, login='sec_internal', groups='base.group_user')
        cls.portal_user = new_test_user(cls.env, login='sec_portal', groups='base.group_portal')

        cls.product = cls.env['product.product'].create({
            'name': 'Sec Burger',
            'list_price': 10.0,
            'taxes_id': False,
            'available_in_pos': True,
        })
        cls.free_product = cls.env['product.product'].create({
            'name': 'Sec Ketchup',
            'list_price': 0.0,
            'taxes_id': False,
            'available_in_pos': True,
        })

        bank_journal = cls.env['account.journal'].create({
            'name': 'Sec Bank',
            'type': 'bank',
            'code': 'SECB',
            'company_id': cls.env.company.id,
        })
        cls.bank_payment_method = cls.env['pos.payment.method'].create({
            'name': 'Sec Bank',
            'journal_id': bank_journal.id,
        })

        cls.pos_config = cls.env['pos.config'].create({
            'name': 'Sec Self Order',
            'module_pos_restaurant': True,
            'self_ordering_mode': 'mobile',
            'self_ordering_service_mode': 'table',
            'self_ordering_pay_after': 'each',
            'self_ordering_default_user_id': cls.pos_user.id,
            'payment_method_ids': [Command.link(cls.bank_payment_method.id)],
        })
        floor = cls.env['restaurant.floor'].create({
            'name': 'Sec Floor',
            'pos_config_ids': [Command.link(cls.pos_config.id)],
        })
        cls.table_1 = cls.env['restaurant.table'].create({'table_number': 1, 'floor_id': floor.id})
        cls.table_2 = cls.env['restaurant.table'].create({'table_number': 2, 'floor_id': floor.id})

        cls.pos_config.open_ui()
        cls.pos_session = cls.pos_config.current_session_id
        cls.pos_session.set_opening_control(0, '')

    # ── helpers ──────────────────────────────────────────────

    def _line(self, product, qty, **vals):
        price = product.lst_price
        return [Command.CREATE, 0, dict({
            'uuid': str(uuid4()),
            'product_id': product.id,
            'qty': qty,
            'price_unit': price,
            'price_subtotal': price * qty,
            'price_subtotal_incl': price * qty,
            'full_product_name': product.name,
            'attribute_value_ids': [],
        }, **vals)]

    def _order(self, lines, **vals):
        return dict({
            'id': None,
            'uuid': str(uuid4()),
            'access_token': None,
            'state': 'draft',
            'amount_total': 0,
            'amount_tax': 0,
            'amount_paid': 0,
            'amount_return': 0,
            'takeaway': False,
            'table_id': False,
            'lines': lines,
        }, **vals)

    def _process(self, order, table_identifier=None):
        return self.make_jsonrpc_request('/pos-self-order/process-order/mobile/', {
            'order': order,
            'access_token': self.pos_config.access_token,
            'table_identifier': table_identifier,
        })

    def _session_orders(self):
        self.env.invalidate_all()
        return self.env['pos.order'].search([('session_id', '=', self.pos_session.id)])

    def _create_draft_order(self, table=None, **vals):
        return self.env['pos.order'].create(dict({
            'session_id': self.pos_session.id,
            'table_id': table.id if table else False,
            'amount_tax': 0,
            'amount_total': 10,
            'amount_paid': 0,
            'amount_return': 0,
            'lines': [Command.create({
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 10,
                'price_subtotal': 10,
                'price_subtotal_incl': 10,
                'full_product_name': self.product.name,
            })],
        }, **vals))


@tagged('post_install', '-at_install')
class TestSelfOrderProcessOrder(SelfOrderSecurityCommon):

    def test_regular_order_goes_through_payment_gate(self):
        result = self._process(self._order([self._line(self.product, 2)]), self.table_1.identifier)
        order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        self.env.invalidate_all()
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.self_order_payment_status, 'pending_online')
        self.assertAlmostEqual(order.amount_total, 20.0)
        self.assertEqual(order.table_id, self.table_1)

    def test_free_order_is_still_paid_immediately(self):
        result = self._process(self._order([self._line(self.free_product, 1)]), self.table_1.identifier)
        order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        self.env.invalidate_all()
        self.assertEqual(order.state, 'paid')

    def test_plus_minus_same_product_is_rejected(self):
        before = self._session_orders()
        order = self._order([self._line(self.product, 1), self._line(self.product, -1)])
        with self.assertRaises(JsonRpcException):
            self._process(order, self.table_1.identifier)
        after = self._session_orders()
        self.assertEqual(after, before, "no order may be created")
        self.assertFalse(after.filtered(lambda o: o.state == 'paid'))

    def test_zero_quantity_is_rejected(self):
        before = self._session_orders()
        with self.assertRaises(JsonRpcException):
            self._process(self._order([self._line(self.product, 0)]), self.table_1.identifier)
        self.assertEqual(self._session_orders(), before)

    def test_takeaway_with_other_table_id_does_not_touch_that_table(self):
        victim = self._create_draft_order(table=self.table_2)
        victim._ensure_access_token()
        victim_lines = victim.lines
        victim_token = victim.access_token

        order = self._order(
            [self._line(self.product, 1)],
            takeaway=True,
            table_id=self.table_2.id,
        )
        result = self._process(order, table_identifier=None)

        self.env.invalidate_all()
        new_order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        self.assertNotEqual(new_order, victim)
        self.assertFalse(new_order.table_id)
        self.assertEqual(victim.lines, victim_lines)
        self.assertEqual(len(victim.lines), 1)
        self.assertEqual(victim.state, 'draft')
        returned_tokens = [o.get('access_token') for o in result['pos.order']]
        self.assertNotIn(victim_token, returned_tokens)

    def test_foreign_line_commands_are_rejected(self):
        victim = self._create_draft_order(table=self.table_2)
        victim_line = victim.lines

        update = self._order([[Command.UPDATE, victim_line.id, {
            'product_id': self.product.id,
            'qty': 99,
            'price_unit': 10,
            'uuid': victim_line.uuid,
        }]])
        with self.assertRaises(JsonRpcException):
            self._process(update, self.table_1.identifier)

        delete = self._order([self._line(self.product, 1), [Command.DELETE, victim_line.id]])
        with self.assertRaises(JsonRpcException):
            self._process(delete, self.table_1.identifier)

        self.env.invalidate_all()
        self.assertTrue(victim_line.exists())
        self.assertEqual(victim_line.qty, 1)
        self.assertEqual(victim_line.order_id, victim)

    def test_client_payment_ids_are_ignored(self):
        order = self._order(
            [self._line(self.product, 1)],
            amount_paid=10,
            payment_ids=[[Command.CREATE, 0, {
                'amount': 10,
                'payment_method_id': self.bank_payment_method.id,
                'payment_date': '2026-11-06 00:00:00',
            }]],
            partner_id=self.portal_user.partner_id.id,
            state='paid',
        )
        result = self._process(order, self.table_1.identifier)
        self.env.invalidate_all()
        new_order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        self.assertFalse(new_order.payment_ids)
        self.assertEqual(new_order.amount_paid, 0)
        self.assertFalse(new_order.partner_id)
        self.assertNotEqual(new_order.email, self.portal_user.partner_id.email)
        self.assertEqual(new_order.state, 'draft')
        self.assertEqual(new_order.self_order_payment_status, 'pending_online')


    def _resend(self, payload, result, lines):
        """Resend the caller's own order (same uuid / id) with new line commands."""
        return dict(payload, id=result['pos.order'][0]['id'], lines=lines)

    def test_resend_of_paid_order_is_rejected(self):
        payload = self._order([self._line(self.free_product, 1)])
        result = self._process(payload, self.table_1.identifier)
        order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        self.env.invalidate_all()
        self.assertEqual(order.state, 'paid')
        status = order.self_order_payment_status

        with self.assertRaises(JsonRpcException):
            self._process(
                self._resend(payload, result, [self._line(self.product, 1)]),
                self.table_1.identifier,
            )
        self.env.invalidate_all()
        self.assertEqual(order.state, 'paid')
        self.assertEqual(order.self_order_payment_status, status)
        self.assertEqual(len(order.lines), 1)

    def test_empty_order_is_rejected(self):
        before = self._session_orders()
        with self.assertRaises(JsonRpcException):
            self._process(self._order([]), self.table_1.identifier)
        after = self._session_orders()
        self.assertEqual(after, before)
        self.assertFalse(after.filtered(lambda o: o.state == 'paid'))

    def test_foreign_line_cannot_be_adopted_as_combo_child(self):
        victim = self._create_draft_order(table=self.table_2)
        victim_line = victim.lines
        order = self._order([
            self._line(self.product, 1, combo_line_ids=[victim_line.id]),
            self._line(self.product, 1, combo_parent_id=victim_line.id),
        ])
        try:
            result = self._process(order, self.table_1.identifier)
        except JsonRpcException:
            result = None
        self.env.invalidate_all()
        self.assertEqual(victim_line.order_id, victim)
        self.assertFalse(victim_line.combo_parent_id)
        self.assertFalse(victim_line.combo_line_ids)
        self.assertEqual(victim.lines, victim_line)
        if result:
            new_order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
            self.assertNotIn(victim_line, new_order.lines.combo_line_ids)
            self.assertFalse(new_order.lines.combo_parent_id - new_order.lines)

    def test_decrement_and_remove_already_sent_lines(self):
        # Core self-order JS never sends qty 0 for an already-sent line: the
        # cart cannot go below the sent quantity and removing a line deletes
        # it (DELETE command). Both must keep working on the caller's order.
        payload = self._order([self._line(self.product, 2), self._line(self.free_product, 1)])
        result = self._process(payload, self.table_1.identifier)
        order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        burger_line = order.lines.filtered(lambda l: l.product_id == self.product)
        ketchup_line = order.lines - burger_line

        result = self._process(self._resend(payload, result, [
            [Command.UPDATE, burger_line.id, {
                'uuid': burger_line.uuid,
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 10.0,
                'price_subtotal': 10.0,
                'price_subtotal_incl': 10.0,
                'full_product_name': self.product.name,
                'attribute_value_ids': [],
            }],
            [Command.DELETE, ketchup_line.id],
        ]), self.table_1.identifier)
        self.env.invalidate_all()
        self.assertEqual(result['pos.order'][0]['id'], order.id)
        self.assertEqual(order.lines, burger_line)
        self.assertEqual(burger_line.qty, 1)
        self.assertFalse(ketchup_line.exists())
        self.assertEqual(order.state, 'draft')
        self.assertAlmostEqual(order.amount_total, 10.0)


@tagged('post_install', '-at_install')
class TestReturnToOrder(SelfOrderSecurityCommon):

    def _assert_no_token(self, response):
        token = self.pos_config.access_token
        self.assertTrue(token)
        self.assertNotIn(token, response.headers.get('Location', ''))
        self.assertNotIn(token, response.text)

    def test_anonymous_does_not_get_config_token(self):
        for url in (
            '/pos-self-order/return-to-order',
            f'/pos-self-order/return-to-order?reference=Self-Order%2000001-{self.pos_config.id:03d}-0001',
            f'/pos-self-order/return-to-order?tx_id=1&token=deadbeef',
        ):
            response = self.url_open(url, allow_redirects=False)
            self.assertEqual(response.status_code, 404, url)
            self._assert_no_token(response)

    def test_transaction_token_is_required(self):
        pos_order = self._create_draft_order(table=self.table_1)
        # Same fixture order as payment.tests.common: the provider supporting
        # the method must exist (and be enabled) before the method is activated.
        payment_method = self.env.ref('payment.payment_method_unknown')
        provider = self.env['payment.provider'].create({
            'name': 'Sec Dummy Provider',
            'code': 'none',
            'state': 'test',
            'is_published': True,
            'payment_method_ids': [Command.set(payment_method.ids)],
            'available_currency_ids': [Command.set(self.env.company.currency_id.ids)],
        })
        payment_method.write({'active': True})
        tx = self.env['payment.transaction'].create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'reference': f'SEC-{uuid4().hex[:8]}',
            'amount': 10.0,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.env.company.partner_id.id,
            'operation': 'online_redirect',
            'pos_order_id': pos_order.id,
        })

        response = self.url_open(
            f'/pos-self-order/return-to-order?tx_id={tx.id}&token=wrong', allow_redirects=False,
        )
        self.assertEqual(response.status_code, 404)
        self._assert_no_token(response)

        token = tx._get_pos_self_return_token()
        response = self.url_open(
            f'/pos-self-order/return-to-order?tx_id={tx.id}&token={token}', allow_redirects=False,
        )
        self.assertIn(response.status_code, (301, 302, 303))
        self.assertIn(
            f'/pos-self/{self.pos_config.id}?access_token={self.pos_config.access_token}',
            response.headers.get('Location', ''),
        )


@tagged('post_install', '-at_install')
class TestUberDirectQuote(SelfOrderSecurityCommon):

    def setUp(self):
        super().setUp()
        self.pos_config.write({'uber_direct_enabled': True})
        uber_quote_ctrl._quote_hits.clear()

    def test_quote_without_token_is_rejected(self):
        with patch(UBER_GET_QUOTE) as get_quote:
            with self.assertRaises(JsonRpcException):
                self.make_jsonrpc_request('/pos-self/uber-direct/quote', {
                    'config_id': self.pos_config.id,
                    'dropoff_address': 'Somewhere 1',
                })
            with self.assertRaises(JsonRpcException):
                self.make_jsonrpc_request('/pos-self/uber-direct/quote', {
                    'access_token': 'not-the-token',
                    'config_id': self.pos_config.id,
                    'dropoff_address': 'Somewhere 1',
                })
            get_quote.assert_not_called()

    def test_quote_with_token_and_generic_errors(self):
        params = {
            'access_token': self.pos_config.access_token,
            'config_id': self.pos_config.id,
            'dropoff_address': 'Somewhere 1',
        }
        with patch(UBER_GET_QUOTE, return_value={
            'success': True, 'fee': 65, 'currency': self.pos_config.currency_id.name,
            'estimated_pickup_minutes': 20, 'quote_id': 'dqt_1',
        }):
            result = self.make_jsonrpc_request('/pos-self/uber-direct/quote', params)
        self.assertTrue(result['success'])
        self.assertEqual(result['fee'], 65)

        with patch(UBER_GET_QUOTE, return_value={
            'success': False, 'error': 'raw uber message', 'status_code': 400,
            'detail': {'secret': 'raw uber body'},
        }):
            result = self.make_jsonrpc_request('/pos-self/uber-direct/quote', params)
        self.assertFalse(result['success'])
        self.assertNotIn('detail', result)
        self.assertNotIn('raw uber', json.dumps(result))

        with patch(UBER_GET_QUOTE) as get_quote:
            result = self.make_jsonrpc_request(
                '/pos-self/uber-direct/quote', dict(params, dropoff_address='x' * 1000),
            )
            get_quote.assert_not_called()
        self.assertFalse(result['success'])

    def test_quote_throttle(self):
        key = [(('client', 'test', str(uuid4())), 3)]
        self.assertFalse(uber_quote_ctrl._quote_throttled(key, now=1000.0))
        self.assertFalse(uber_quote_ctrl._quote_throttled(key, now=1001.0))
        self.assertFalse(uber_quote_ctrl._quote_throttled(key, now=1002.0))
        self.assertTrue(uber_quote_ctrl._quote_throttled(key, now=1003.0))
        # window slides
        self.assertFalse(uber_quote_ctrl._quote_throttled(
            key, now=1000.0 + uber_quote_ctrl.QUOTE_WINDOW_SECONDS + 1,
        ))


@tagged('post_install', '-at_install')
class TestEscPosPrintRoutes(SelfOrderSecurityCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.printer = cls.env['pos.printer'].create({
            'name': 'Sec Kitchen',
            'printer_type': 'network_escpos',
            'escpos_printer_ip': '192.0.2.10',
        })

    def _call_both_routes(self):
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/pos-escpos/print', {
                'action': 'cashbox',
                'printer_ip': '127.0.0.1',
            })
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/pos-escpos/print-order', {
                'order_id': self._create_draft_order().id,
                'printer_id': self.printer.id,
            })

    def test_portal_user_is_refused(self):
        self.authenticate('sec_portal', 'sec_portal')
        with patch(ESCPOS_SEND_BYTES) as send_bytes:
            self._call_both_routes()
            send_bytes.assert_not_called()

    def test_internal_user_without_pos_group_is_refused(self):
        self.authenticate('sec_internal', 'sec_internal')
        with patch(ESCPOS_SEND_BYTES) as send_bytes:
            self._call_both_routes()
            send_bytes.assert_not_called()

    def test_pos_user_cannot_target_arbitrary_ip(self):
        self.authenticate('sec_pos_user', 'sec_pos_user')
        with patch(ESCPOS_SEND_BYTES) as send_bytes:
            result = self.make_jsonrpc_request('/pos-escpos/print', {
                'action': 'cashbox',
                'printer_ip': '127.0.0.1',
            })
            send_bytes.assert_not_called()
        self.assertFalse(result['success'])

    def test_pos_user_configured_printer_generic_error(self):
        self.pos_config.write({'printer_ids': [Command.link(self.printer.id)]})
        self.pos_session.write({'user_id': self.pos_user.id})
        self.authenticate('sec_pos_user', 'sec_pos_user')
        with patch(ESCPOS_SEND_BYTES, side_effect=OSError('connection refused by 10.9.8.7')) as send_bytes:
            result = self.make_jsonrpc_request('/pos-escpos/print', {
                'action': 'cashbox',
                'printer_id': self.printer.id,
                'printer_ip': self.printer.escpos_printer_ip,
            })
            send_bytes.assert_called_once()
            self.assertEqual(send_bytes.call_args[0][0], '192.0.2.10')
        self.assertFalse(result['success'])
        self.assertNotIn('10.9.8.7', result['error'])
        self.assertNotIn('refused', result['error'])


@tagged('post_install', '-at_install')
class TestUberDirectWebhook(SelfOrderSecurityCommon):

    SIGNING_KEY = 'sec-test-signing-key'

    def setUp(self):
        super().setUp()
        self.pos_config.write({
            'uber_direct_enabled': True,
            'uber_direct_webhook_signing_key': self.SIGNING_KEY,
        })
        self.order = self._create_draft_order(
            uber_delivery_id='del_sec_123',
            uber_delivery_status='pending',
        )
        self.body = json.dumps({
            'kind': 'event.delivery_status',
            'delivery_id': 'del_sec_123',
            'meta': {'resource_id': 'del_sec_123'},
            'data': {
                'status': 'delivered',
                'courier': {'name': 'Mallory', 'phone_number': '+886900000000'},
            },
        }).encode()

    def _post(self, headers):
        return self.url_open(
            '/uber-direct/webhook',
            data=self.body,
            headers=dict({'Content-Type': 'application/json'}, **headers),
        )

    def _signature(self, key):
        return hmac.new(key.encode(), self.body, hashlib.sha256).hexdigest()

    def _assert_unchanged(self):
        self.env.invalidate_all()
        self.assertEqual(self.order.uber_delivery_status, 'pending')
        self.assertFalse(self.order.uber_courier_name)

    def test_missing_signature_is_rejected(self):
        response = self._post({})
        self.assertEqual(response.status_code, 401)
        self._assert_unchanged()

    def test_wrong_signature_is_rejected(self):
        response = self._post({'X-Uber-Signature': self._signature('another-key')})
        self.assertEqual(response.status_code, 401)
        self._assert_unchanged()

    def test_no_configured_key_is_rejected(self):
        self.pos_config.write({'uber_direct_webhook_signing_key': False})
        response = self._post({'X-Uber-Signature': self._signature(self.SIGNING_KEY)})
        self.assertEqual(response.status_code, 401)
        self._assert_unchanged()

    def test_valid_signature_updates_status_idempotently(self):
        response = self._post({'X-Uber-Signature': self._signature(self.SIGNING_KEY)})
        self.assertEqual(response.status_code, 200)
        self.env.invalidate_all()
        self.assertEqual(self.order.uber_delivery_status, 'delivered')
        self.assertEqual(self.order.uber_courier_name, 'Mallory')

        with patch.object(type(self.env['pos.order']), 'write', autospec=True) as write:
            response = self._post({'X-Postmates-Signature': self._signature(self.SIGNING_KEY)})
            self.assertEqual(response.status_code, 200)
            write.assert_not_called()

    def test_non_ascii_signature_is_rejected_not_500(self):
        response = self._post({'X-Uber-Signature': '\u00e9' * 64})
        self.assertEqual(response.status_code, 401)
        self._assert_unchanged()


@tagged('post_install', '-at_install')
class TestKdsAndRoutingHardening(SelfOrderSecurityCommon):

    def test_kds_rejects_bad_tokens_without_server_error(self):
        self.pos_config.write({'kds_enabled': True, 'kds_access_token': 'a1b2c3d4e5f60718'})
        route = f'/pos-kds/orders/{self.pos_config.id}'
        for token in (None, '', 'wrong-token', '\u00e9' * 16):
            with self.assertRaises(JsonRpcException) as ctx:
                self.make_jsonrpc_request(route, {'token': token})
            self.assertEqual(str(ctx.exception), 'werkzeug.exceptions.Forbidden', token)
        result = self.make_jsonrpc_request(route, {'token': 'a1b2c3d4e5f60718'})
        self.assertIn('orders', result)

    def test_kds_rejects_empty_configured_token(self):
        self.pos_config.write({'kds_enabled': True, 'kds_access_token': False})
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(f'/pos-kds/orders/{self.pos_config.id}', {'token': None})

    def test_write_routes_are_not_readonly(self):
        from odoo.addons.pos_self_order_enhancement.controllers import kds, orders, uber_webhook
        endpoints = [
            uber_webhook.UberDirectWebhook.receive_webhook,
            orders.PosSelfOrderControllerEnh.process_order,
            orders.PosSelfOrderControllerEnh.process_order_args,
            orders.PosSelfOrderControllerEnh.select_counter_payment,
            orders.PosSelfOrderControllerEnh.save_einvoice_data,
            kds.PosKitchenDisplay.kds_bump_order,
            kds.PosKitchenDisplay.kds_change_state,
            kds.PosKitchenDisplay.kds_toggle_item_done,
            kds.PosKitchenDisplay.kds_recall_order,
            kds.PosKitchenDisplay.kds_fire_course,
            kds.PosKitchenDisplay.kds_batch_item_done,
            kds.PosKitchenDisplay.kds_batch_lines_done,
        ]
        for endpoint in endpoints:
            self.assertIs(endpoint.original_routing.get('readonly'), False, endpoint.__name__)
