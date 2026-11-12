# -*- coding: utf-8 -*-
"""Focused Uber Direct hardening regression tests.

Import this module from tests/__init__.py when the integration worker can edit
that file; this worker's file scope does not include the existing initializer.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from werkzeug.exceptions import BadRequest

from odoo.tests.common import JsonRpcException, TransactionCase, tagged

from odoo.addons.pos_self_order_enhancement.controllers.uber_quote import (
    _sign_quote, verify_quote_receipt,
)
from odoo.addons.pos_self_order_enhancement.models.uber_direct import UberDirect, _token_cache
from .test_security_fixes import SelfOrderSecurityCommon


@tagged('post_install', '-at_install')
class TestUberHardening(TransactionCase):

    def setUp(self):
        super().setUp()
        self.config = SimpleNamespace(id=73, currency_id=SimpleNamespace(name='TWD'))
        self.quote = {'fee': 78, 'currency': 'TWD', 'quote_id': 'dqt_123'}

    def test_signed_quote_binds_address_config_fee_and_expiry(self):
        token = _sign_quote(self.env, self.config, ' Taipei 1 ', self.quote, now=1000)
        self.assertEqual(
            verify_quote_receipt(self.env, self.config, 'Taipei 1', token, now=1001),
            {'fee': 78, 'currency': 'TWD', 'quote_id': 'dqt_123'},
        )
        for config, address, receipt, now in (
            (self.config, 'Taipei 2', token, 1001),
            (SimpleNamespace(id=74, currency_id=self.config.currency_id), 'Taipei 1', token, 1001),
            (self.config, 'Taipei 1', token[:-1] + ('0' if token[-1] != '0' else '1'), 1001),
            (self.config, 'Taipei 1', token, 1601),
        ):
            with self.assertRaises(BadRequest):
                verify_quote_receipt(self.env, config, address, receipt, now=now)

    def test_invalid_provider_fee_is_not_signed(self):
        for fee in (-1, True, float('nan')):
            with self.assertRaises(ValueError):
                _sign_quote(self.env, self.config, 'Taipei 1', dict(self.quote, fee=fee))

    def test_delivery_uses_persisted_order_fields(self):
        config = SimpleNamespace(
            id=73, uber_direct_customer_id='customer',
            uber_direct_pickup_name='Store', uber_direct_pickup_address='Pickup',
            uber_direct_pickup_phone='123',
        )
        order = SimpleNamespace(
            name='Order 1', uber_delivery_address='Trusted address',
            uber_quote_id='dqt_123', partner_id=False, lines=[],
        )
        response = Mock(status_code=201)
        response.json.return_value = {'id': 'del_123', 'status': 'pending'}
        with (patch.object(UberDirect, '_auth_headers', return_value={'Authorization': 'Bearer token'}),
              patch.object(UberDirect, '_api_base', return_value='https://example.test'),
              patch.object(UberDirect, '_request', return_value=response) as send):
            result = self.env['uber.direct']._create_delivery(config, order)
        self.assertTrue(result['success'])
        body = send.call_args.kwargs['json']
        self.assertEqual(body['dropoff']['address'], 'Trusted address')
        self.assertEqual(body['quote_id'], 'dqt_123')

    def test_quote_uses_the_configured_shop_name(self):
        config = SimpleNamespace(
            id=73, uber_direct_customer_id='customer',
            uber_direct_pickup_name='Another Shop',
        )
        response = Mock(status_code=200)
        response.json.return_value = {
            'fee': 78, 'currency': 'TWD', 'id': 'dqt_123',
        }
        with (patch.object(UberDirect, '_auth_headers', return_value={'Authorization': 'Bearer token'}),
              patch.object(UberDirect, '_api_base', return_value='https://example.test'),
              patch.object(UberDirect, '_request', return_value=response) as send):
            result = self.env['uber.direct']._get_quote(config, 'Pickup', 'Dropoff')
        self.assertTrue(result['success'])
        self.assertEqual(send.call_args.kwargs['json']['pickup_name'], 'Another Shop')

    def test_token_cache_separates_credentials(self):
        config = SimpleNamespace(
            id=73, uber_direct_env='production', uber_direct_client_id='id',
            uber_direct_client_secret='first', uber_direct_customer_id='customer',
        )
        config.sudo = lambda: config
        response = Mock(status_code=200)
        response.json.return_value = {'access_token': 'token', 'expires_in': 3600}
        model = self.env['uber.direct']
        _token_cache.clear()
        with (patch.object(UberDirect, '_auth_url', return_value='https://example.test/token'),
              patch('odoo.addons.pos_self_order_enhancement.models.uber_direct.requests.post',
                    return_value=response) as post):
            model._get_access_token(config)
            model._get_access_token(config)
            self.assertEqual(post.call_count, 1)
            config.uber_direct_client_secret = 'second'
            model._get_access_token(config)
            self.assertEqual(post.call_count, 2)
        _token_cache.clear()


@tagged('post_install', '-at_install')
class TestUberOrderIntegration(SelfOrderSecurityCommon):

    def setUp(self):
        super().setUp()
        self.pos_config.write({
            'uber_direct_enabled': True,
            'self_ordering_takeaway': True,
        })

    def _delivery_order(self, receipt=None, product=None, **extra):
        address = 'Taipei Main Street 1'
        quote = {'fee': 65, 'currency': self.pos_config.currency_id.name,
                 'quote_id': 'dqt_verified_123'}
        receipt = receipt or _sign_quote(self.env, self.pos_config, address, quote)
        return self._order(
            [self._line(product or self.product, 1)],
            takeaway=True,
            uber_delivery_address=address,
            uber_quote_id=receipt,
            uber_delivery_fee=0,
            **extra,
        )

    def test_valid_quote_adds_exactly_one_server_fee_and_requires_payment(self):
        result = self._process(self._delivery_order(product=self.free_product))
        self.env.invalidate_all()
        order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        fee_product = self.env.ref('pos_self_order_enhancement.product_product_delivery_fee')
        fee_lines = order.lines.filtered(lambda line: line.product_id == fee_product)
        self.assertEqual(len(fee_lines), 1)
        self.assertEqual(fee_lines.price_unit, 65)
        self.assertEqual(order.amount_total, 65)
        self.assertEqual(order.uber_quote_id, 'dqt_verified_123')
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.self_order_payment_status, 'pending_online')

    def test_tampered_quote_cannot_create_order(self):
        payload = self._delivery_order()
        payload['uber_quote_id'] += 'x'
        with self.assertRaises(JsonRpcException):
            self._process(payload)
        self.assertFalse(self._session_orders())

    def test_unsigned_delivery_and_client_fee_line_rejected(self):
        payload = self._delivery_order()
        payload['uber_quote_id'] = 'dqt_raw'
        with self.assertRaises(JsonRpcException):
            self._process(payload)
        fee_product = self.env.ref('pos_self_order_enhancement.product_product_delivery_fee')
        payload = self._delivery_order()
        payload['lines'].append(self._line(fee_product, 1))
        with self.assertRaises(JsonRpcException):
            self._process(payload)

    def test_delivery_fields_ignored_without_delivery_address(self):
        result = self._process(self._order(
            [self._line(self.product, 1)],
            uber_delivery_fee=9999, uber_quote_id='dqt_fake',
        ), self.table_1.identifier)
        self.env.invalidate_all()
        order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        self.assertFalse(order.uber_quote_id)
        self.assertFalse(order.uber_delivery_address)
        self.assertFalse(order.uber_delivery_fee)
