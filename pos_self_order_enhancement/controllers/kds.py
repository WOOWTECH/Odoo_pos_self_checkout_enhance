# -*- coding: utf-8 -*-
import json
import logging

import werkzeug

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosKitchenDisplay(http.Controller):
    """Controller for the Kitchen Display Screen (KDS)."""

    # ── helpers ──────────────────────────────────────────────

    def _verify_kds_access(self, config_id, token):
        """Validate token and return pos.config sudo record."""
        if not config_id or not str(config_id).isnumeric():
            raise werkzeug.exceptions.NotFound()

        config = request.env['pos.config'].sudo().search([
            ('id', '=', int(config_id)),
            ('kds_enabled', '=', True),
            ('kds_access_token', '=', token),
        ], limit=1)

        if not config:
            raise werkzeug.exceptions.Forbidden()

        return config

    def _get_active_orders(self, config):
        """Fetch active kitchen orders sent to kitchen by staff."""
        session = config.current_session_id
        if not session:
            return []

        orders = request.env['pos.order'].sudo().search([
            ('session_id', '=', session.id),
            ('state', 'not in', ('cancel',)),
            ('kds_state', 'in', ('new', 'in_progress')),
            ('kds_sent_to_kitchen', '=', True),
        ], order='date_order asc')

        return self._serialize_orders(orders)

    def _get_done_orders(self, config, limit=20):
        """Fetch recently completed orders for recall/history."""
        session = config.current_session_id
        if not session:
            return []

        orders = request.env['pos.order'].sudo().search([
            ('session_id', '=', session.id),
            ('kds_state', '=', 'done'),
            ('kds_sent_to_kitchen', '=', True),
        ], order='write_date desc', limit=limit)

        return self._serialize_orders(orders)

    def _serialize_orders(self, orders):
        """Convert pos.order records to JSON-friendly dicts."""
        now = fields.Datetime.now()
        result = []
        for order in orders:
            elapsed = (now - order.date_order).total_seconds()
            elapsed_minutes = int(elapsed // 60)
            elapsed_seconds = int(elapsed % 60)

            # Parse done items
            try:
                done_items = json.loads(order.kds_done_items or '{}')
            except (json.JSONDecodeError, TypeError):
                done_items = {}

            # Parse remake data
            try:
                remake_data = json.loads(order.kds_remake_data or '{}')
            except (json.JSONDecodeError, TypeError):
                remake_data = {}

            # Build order lines
            lines = []
            has_active_remake = False
            for line in order.lines:
                if line.qty <= 0 or line.price_unit < 0:
                    continue
                line_key = str(line.id)
                line_remake = remake_data.get(line_key, {})
                is_done = done_items.get(line_key, False)
                # A line is actively remade if it has remake data and is not yet done
                if line_remake and not is_done:
                    has_active_remake = True
                lines.append({
                    'id': line.id,
                    'uuid': line.uuid,
                    'product_name': line.full_product_name or line.product_id.display_name,
                    'qty': line.qty,
                    'customer_note': line.note or '',
                    'is_done': is_done,
                    'remake_count': line_remake.get('count', 0),
                    'remake_reason': line_remake.get('reason', ''),
                })

            # Table info
            table_name = ''
            floor_name = ''
            if hasattr(order, 'table_id') and order.table_id:
                table_name = str(order.table_id.table_number or order.table_id.display_name or '')
                if order.table_id.floor_id:
                    floor_name = order.table_id.floor_id.display_name or ''

            is_takeaway = getattr(order, 'takeaway', False)

            result.append({
                'id': order.id,
                'name': order.pos_reference or order.name,
                'table_name': table_name,
                'floor_name': floor_name,
                'is_takeaway': is_takeaway,
                'kds_state': order.kds_state,
                'is_remake': has_active_remake,
                'date_order': order.date_order.strftime('%H:%M'),
                'elapsed_minutes': elapsed_minutes,
                'elapsed_seconds': elapsed_seconds,
                'elapsed_total_seconds': int(elapsed),
                'lines': lines,
                'general_note': getattr(order, 'general_note', '') or '',
            })

        return result

    # ── routes ───────────────────────────────────────────────

    @http.route(
        ['/pos-kds/<int:config_id>', '/pos-kds/<int:config_id>/<path:subpath>'],
        type='http', auth='public', website=True, sitemap=False,
    )
    def kds_page(self, config_id, token=None, subpath=None, **kwargs):
        """Serve the KDS HTML page."""
        config = self._verify_kds_access(config_id, token)
        session_info = {
            'config_id': config.id,
            'config_name': config.name,
            'access_token': config.kds_access_token,
            'bus_token': config.access_token,
            'db': request.env.cr.dbname,
            'base_url': request.env['pos.session'].get_base_url(),
            'csrf_token': request.csrf_token(),
        }
        return request.render(
            'pos_self_order_enhancement.kds_index',
            {
                'session_info_json': json.dumps(session_info),
            },
        )

    @http.route('/pos-kds/orders/<int:config_id>', type='json', auth='public')
    def kds_get_orders(self, config_id, token=None, **kwargs):
        """Fetch active orders for the KDS."""
        config = self._verify_kds_access(config_id, token)
        return {
            'orders': self._get_active_orders(config),
            'has_session': bool(config.current_session_id),
        }

    @http.route('/pos-kds/bump/<int:config_id>', type='json', auth='public')
    def kds_bump_order(self, config_id, token=None, order_id=None, **kwargs):
        """Mark an order as done (bump it off the KDS)."""
        config = self._verify_kds_access(config_id, token)
        order = request.env['pos.order'].sudo().browse(int(order_id))
        if not order.exists() or order.config_id.id != config.id:
            return {'success': False, 'error': 'Order not found'}

        order.write({'kds_state': 'done'})
        config._notify('KDS_ORDER_UPDATE', {
            'order_id': order.id,
            'kds_state': 'done',
        })
        return {'success': True}

    @http.route('/pos-kds/state/<int:config_id>', type='json', auth='public')
    def kds_change_state(self, config_id, token=None, order_id=None, state=None, **kwargs):
        """Change the KDS state of an order."""
        config = self._verify_kds_access(config_id, token)
        if state not in ('new', 'in_progress', 'done'):
            return {'success': False, 'error': 'Invalid state'}

        order = request.env['pos.order'].sudo().browse(int(order_id))
        if not order.exists() or order.config_id.id != config.id:
            return {'success': False, 'error': 'Order not found'}

        order.write({'kds_state': state})
        config._notify('KDS_ORDER_UPDATE', {
            'order_id': order.id,
            'kds_state': state,
        })
        return {'success': True}

    @http.route('/pos-kds/item-done/<int:config_id>', type='json', auth='public')
    def kds_toggle_item_done(self, config_id, token=None, order_id=None, line_id=None, **kwargs):
        """Toggle an order line's done status on the KDS."""
        config = self._verify_kds_access(config_id, token)
        order = request.env['pos.order'].sudo().browse(int(order_id))
        if not order.exists() or order.config_id.id != config.id:
            return {'success': False, 'error': 'Order not found'}

        try:
            done_items = json.loads(order.kds_done_items or '{}')
        except (json.JSONDecodeError, TypeError):
            done_items = {}

        key = str(line_id)
        done_items[key] = not done_items.get(key, False)

        # Check if all items are done → auto-bump
        all_done = True
        for line in order.lines:
            if line.qty > 0 and not done_items.get(str(line.id), False):
                all_done = False
                break

        vals = {'kds_done_items': json.dumps(done_items)}
        if all_done:
            vals['kds_state'] = 'done'
        elif order.kds_state == 'new':
            vals['kds_state'] = 'in_progress'

        order.write(vals)
        config._notify('KDS_ORDER_UPDATE', {
            'order_id': order.id,
            'kds_state': vals.get('kds_state', order.kds_state),
        })
        return {'success': True, 'all_done': all_done}

    @http.route('/pos-kds/recall/<int:config_id>', type='json', auth='public')
    def kds_recall_order(self, config_id, token=None, order_id=None, **kwargs):
        """Recall a bumped order back to the active KDS."""
        config = self._verify_kds_access(config_id, token)

        if order_id:
            # Recall specific order
            order = request.env['pos.order'].sudo().browse(int(order_id))
        else:
            # Recall last bumped order
            session = config.current_session_id
            if not session:
                return {'success': False, 'error': 'No active session'}
            order = request.env['pos.order'].sudo().search([
                ('session_id', '=', session.id),
                ('kds_state', '=', 'done'),
            ], order='write_date desc', limit=1)

        if not order.exists() or order.config_id.id != config.id:
            return {'success': False, 'error': 'No order to recall'}

        order.write({
            'kds_state': 'new',
            'kds_done_items': '{}',
        })
        config._notify('KDS_ORDER_UPDATE', {
            'order_id': order.id,
            'kds_state': 'new',
        })
        return {'success': True, 'order_id': order.id}

    @http.route('/pos-kds/batch-item-done/<int:config_id>', type='json', auth='public')
    def kds_batch_item_done(self, config_id, token=None, product_name=None, **kwargs):
        """Mark all order lines matching a product name as done across active orders."""
        config = self._verify_kds_access(config_id, token)
        if not product_name:
            return {'success': False, 'error': 'Missing product_name'}

        session = config.current_session_id
        if not session:
            return {'success': False, 'error': 'No active session'}

        orders = request.env['pos.order'].sudo().search([
            ('session_id', '=', session.id),
            ('state', 'not in', ('cancel',)),
            ('kds_state', 'in', ('new', 'in_progress')),
            ('kds_sent_to_kitchen', '=', True),
        ])

        updated_count = 0
        bumped_order_ids = []

        for order in orders:
            try:
                done_items = json.loads(order.kds_done_items or '{}')
            except (json.JSONDecodeError, TypeError):
                done_items = {}

            changed = False
            for line in order.lines:
                if line.qty <= 0 or line.price_unit < 0:
                    continue
                line_name = line.full_product_name or line.product_id.display_name
                if line_name == product_name and not done_items.get(str(line.id), False):
                    done_items[str(line.id)] = True
                    changed = True
                    updated_count += 1

            if not changed:
                continue

            # Check if all items in order are now done
            all_done = True
            for line in order.lines:
                if line.qty > 0 and not done_items.get(str(line.id), False):
                    all_done = False
                    break

            vals = {'kds_done_items': json.dumps(done_items)}
            if all_done:
                vals['kds_state'] = 'done'
                bumped_order_ids.append(order.id)
            elif order.kds_state == 'new':
                vals['kds_state'] = 'in_progress'

            order.write(vals)
            config._notify('KDS_ORDER_UPDATE', {
                'order_id': order.id,
                'kds_state': vals.get('kds_state', order.kds_state),
            })

        return {
            'success': True,
            'updated_count': updated_count,
            'bumped_order_ids': bumped_order_ids,
        }

    @http.route('/pos-kds/completed/<int:config_id>', type='json', auth='public')
    def kds_get_completed(self, config_id, token=None, **kwargs):
        """Fetch recently completed orders."""
        config = self._verify_kds_access(config_id, token)
        return {'orders': self._get_done_orders(config)}
