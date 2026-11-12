# -*- coding: utf-8 -*-
"""Security regression tests for KDS writes and POS printer routes."""
import json
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import tagged

from .test_security_fixes import SelfOrderSecurityCommon


@tagged('post_install', '-at_install')
class TestKdsPrinterHardening(SelfOrderSecurityCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_config.write({'kds_enabled': True, 'kds_access_token': 'kds-hardening-token'})
        cls.printer = cls.env['pos.printer'].create({
            'name': 'Bound kitchen printer',
            'printer_type': 'network_escpos',
            'escpos_printer_ip': '192.0.2.40',
            'escpos_proxy_url': 'https://example.invalid',
            'escpos_proxy_api_key': 'relay-secret',
        })
        cls.other_printer = cls.env['pos.printer'].create({
            'name': 'Other kitchen printer',
            'printer_type': 'network_escpos',
            'escpos_printer_ip': '192.0.2.41',
            'escpos_proxy_url': 'https://example.invalid',
        })
        cls.pos_config.write({'printer_ids': [Command.link(cls.printer.id)]})

    def _kds(self, route, params):
        return self.make_jsonrpc_request(
            '/pos-kds/%s/%s' % (route, self.pos_config.id),
            dict(params, token=self.pos_config.kds_access_token),
        )

    def test_kds_page_does_not_expose_pos_token(self):
        response = self.url_open(self.pos_config.kds_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.pos_config.access_token, response.text)
        self.assertNotIn('bus_token', response.text)

    def test_kds_writes_require_sent_active_order(self):
        order = self._create_draft_order()
        line = order.lines[0]
        for route, params in (
            ('bump', {'order_id': order.id}),
            ('state', {'order_id': order.id, 'state': 'done'}),
            ('item-done', {'order_id': order.id, 'line_id': line.id}),
            ('fire-course', {'order_id': order.id, 'category_id': 1}),
            ('recall', {'order_id': order.id}),
        ):
            self.assertFalse(self._kds(route, params)['success'], route)
        self.assertEqual(order.kds_state, 'new')
        order.write({'kds_sent_to_kitchen': True, 'state': 'cancel'})
        self.assertFalse(self._kds('bump', {'order_id': order.id})['success'])
        self.assertFalse(self._kds('batch-lines-done', {
            'items': [{'order_id': order.id, 'line_id': line.id}],
        })['updated_count'])

    def test_kds_rejects_order_from_previous_session(self):
        previous = self.env['pos.session'].create({
            'config_id': self.pos_config.id,
            'user_id': self.pos_user.id,
            'state': 'closed',
        })
        order = self._create_draft_order(
            session_id=previous.id, kds_sent_to_kitchen=True,
        )
        self.assertFalse(self._kds('bump', {'order_id': order.id})['success'])
        self.assertFalse(self._kds('batch-lines-done', {
            'items': [{'order_id': order.id, 'line_id': order.lines[0].id}],
        })['updated_count'])

    def test_kds_batch_limit_and_valid_order(self):
        order = self._create_draft_order(kds_sent_to_kitchen=True)
        line = order.lines[0]
        self.assertFalse(self._kds('batch-lines-done', {
            'items': [{'order_id': order.id, 'line_id': line.id}] * 201,
        })['success'])
        self.assertFalse(self._kds('batch-item-done', {'product_name': 'x' * 257})['success'])
        self.assertTrue(self._kds('item-done', {
            'order_id': order.id, 'line_id': line.id,
        })['success'])
        order.invalidate_recordset()
        self.assertTrue(json.loads(order.kds_done_items)[str(line.id)])

    def test_relay_key_hidden_from_pos_user(self):
        with self.assertRaises(AccessError):
            self.printer.with_user(self.pos_user).read(['escpos_proxy_api_key'])
        self.assertNotIn('escpos_proxy_api_key',
                         self.printer._load_pos_data_fields(self.pos_config.id))

    def test_printer_must_belong_to_order_config(self):
        self.authenticate('sec_pos_user', 'sec_pos_user')
        order = self._create_draft_order()
        with patch('odoo.addons.pos_self_order_enhancement.controllers.print_proxy.PosEscPosProxy._render_ticket_image') as render:
            result = self.make_jsonrpc_request('/pos-escpos/print-order', {
                'order_id': order.id, 'printer_id': self.other_printer.id,
                'lines': [{'name': 'Meal', 'quantity': 1}],
            })
            self.assertFalse(result['success'])
            render.assert_not_called()
            result = self.make_jsonrpc_request('/pos-escpos/print-order', {
                'order_id': order.id, 'printer_id': self.printer.id,
                'lines': [{'name': 'x' * 257, 'quantity': 1}],
            })
            self.assertFalse(result['success'])
            render.assert_not_called()

    def test_browser_receipt_limit_and_wrong_printer(self):
        self.authenticate('sec_pos_user', 'sec_pos_user')
        with patch('odoo.addons.pos_self_order_enhancement.models.pos_printer.PosPrinter._send_via_relay') as send:
            result = self.make_jsonrpc_request('/pos-escpos/print', {
                'action': 'print_receipt', 'printer_id': self.other_printer.id,
                'receipt': 'aGVsbG8=',
            })
            self.assertFalse(result['success'])
            result = self.make_jsonrpc_request('/pos-escpos/print', {
                'action': 'print_receipt', 'printer_id': self.printer.id,
                'receipt': 'A' * 2_000_001,
            })
            self.assertFalse(result['success'])
            send.assert_not_called()
