# -*- coding: utf-8 -*-
"""Payment and e-invoice authorization regressions."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.tests.common import JsonRpcException, tagged

from odoo.addons.pos_self_order_enhancement.models.payment_transaction import PaymentTransaction
from odoo.addons.pos_self_order_enhancement.tests.test_security_fixes import SelfOrderSecurityCommon


@tagged('post_install', '-at_install')
class TestPaymentHardening(SelfOrderSecurityCommon):

    def _order_with_token(self, **vals):
        order = self._create_draft_order(self.table_1, **vals)
        order._ensure_access_token()
        return order

    def _route(self, route, config, order, **vals):
        return self.make_jsonrpc_request('/pos-self-order/' + route, {
            'access_token': config.access_token,
            'order_id': order.id,
            'order_access_token': order.access_token,
            **vals,
        })

    def test_counter_selection_rejects_paid_order_without_downgrade(self):
        order = self._order_with_token(state='paid', self_order_payment_status='paid')
        with self.assertRaises(JsonRpcException):
            self._route('select-counter-payment', self.pos_config, order)
        self.env.invalidate_all()
        self.assertEqual(order.self_order_payment_status, 'paid')

    def test_counter_selection_accepts_pending_order(self):
        order = self._order_with_token(self_order_payment_status='pending_online')
        result = self._route('select-counter-payment', self.pos_config, order)
        self.assertTrue(result['success'])
        self.env.invalidate_all()
        self.assertEqual(order.self_order_payment_status, 'pending_counter')

    def test_takeaway_counter_payment_obeys_server_setting(self):
        order = self._order_with_token(
            takeaway=True, self_order_payment_status='pending_online',
        )
        with self.assertRaises(JsonRpcException):
            self._route('select-counter-payment', self.pos_config, order)
        self.pos_config.self_ordering_takeaway_allow_counter = True
        result = self._route('select-counter-payment', self.pos_config, order)
        self.assertTrue(result['success'])

    def test_invoice_preferences_reject_paid_order_without_overwrite(self):
        order = self._order_with_token(
            state='paid', self_order_payment_status='paid', tw_carrier_type='print',
        )
        with self.assertRaises(JsonRpcException):
            self._route('save-einvoice-data', self.pos_config, order,
                        carrier_type='mobile', carrier_num='/ABC1234')
        self.env.invalidate_all()
        self.assertEqual(order.tw_carrier_type, 'print')

    def test_invoice_preferences_accept_pending_order(self):
        order = self._order_with_token(self_order_payment_status='pending_online')
        result = self._route('save-einvoice-data', self.pos_config, order,
                             carrier_type='mobile', carrier_num='/ABC1234')
        self.assertTrue(result['success'])
        self.env.invalidate_all()
        self.assertEqual(order.tw_carrier_num, '/ABC1234')

    def test_routes_reject_draft_order_with_payment_recorded(self):
        order = self._order_with_token(
            amount_paid=5, self_order_payment_status='pending_online',
        )
        for route in ('select-counter-payment', 'save-einvoice-data'):
            with self.subTest(route=route), self.assertRaises(JsonRpcException):
                self._route(route, self.pos_config, order)
        self.env.invalidate_all()
        self.assertEqual(order.self_order_payment_status, 'pending_online')
        self.assertFalse(order.tw_carrier_type)

    def test_routes_reject_cross_config_even_with_order_token(self):
        other = self.env['pos.config'].create({
            'name': 'Other Self Order',
            'module_pos_restaurant': True,
            'self_ordering_mode': 'mobile',
            'self_ordering_service_mode': 'table',
            'self_ordering_pay_after': 'each',
            'self_ordering_default_user_id': self.pos_user.id,
            'payment_method_ids': [(4, self.bank_payment_method.id)],
        })
        other.open_ui()
        other.current_session_id.set_opening_control(0, '')
        order = self._order_with_token(self_order_payment_status='pending_online')
        for route in ('select-counter-payment', 'save-einvoice-data'):
            with self.subTest(route=route), self.assertRaises(JsonRpcException):
                self._route(route, other, order)
        self.env.invalidate_all()
        self.assertEqual(order.self_order_payment_status, 'pending_online')
        self.assertFalse(order.tw_carrier_type)

    def test_manual_invoice_requires_paid_order_before_sdk(self):
        order = self._order_with_token(self_order_payment_status='pending_online')
        with patch.object(type(order), '_ensure_ecpay_sdk') as sdk:
            result = order.action_issue_einvoice({'carrier_type': 'print'})
        self.assertFalse(result['success'])
        self.assertIn('not paid', result['error'])
        sdk.assert_not_called()

    def test_paid_order_continues_to_invoice_configuration_check(self):
        order = self._order_with_token(state='paid', self_order_payment_status='paid')
        result = order.action_issue_einvoice({'carrier_type': 'print'})
        self.assertEqual(result['error'], 'E-Invoice not enabled')

    def test_authorization_does_not_auto_issue_invoice(self):
        order = SimpleNamespace(
            state='paid',
            config_id=SimpleNamespace(ecpay_einvoice_enabled=True, is_ecpay_installed=True),
            ecpay_invoice_id=False, tw_invoice_status='none',
            action_issue_einvoice=Mock(),
        )
        tx = SimpleNamespace(state='authorized', pos_order_id=order)
        PaymentTransaction._auto_issue_einvoice(tx)
        order.action_issue_einvoice.assert_not_called()

    def test_done_transaction_can_auto_issue_after_capture(self):
        config = SimpleNamespace(ecpay_einvoice_enabled=True, is_ecpay_installed=True)
        order = SimpleNamespace(
            state='paid', config_id=config, ecpay_invoice_id=False,
            tw_invoice_status='none', tw_carrier_type='mobile',
            tw_carrier_num='/ABC1234', tw_love_code='', tw_buyer_tax_id='',
            tw_buyer_name='', pos_reference='TEST', id=1,
            action_issue_einvoice=Mock(return_value={'success': True}),
        )
        tx = SimpleNamespace(state='done', pos_order_id=order)
        PaymentTransaction._auto_issue_einvoice(tx)
        order.action_issue_einvoice.assert_called_once_with({
            'carrier_type': 'mobile', 'carrier_num': '/ABC1234',
            'love_code': '', 'buyer_tax_id': '', 'buyer_name': '',
        })
