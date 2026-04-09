# -*- coding: utf-8 -*-
import json
import logging
from collections import OrderedDict

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

    def _get_line_course_info(self, order, line, fired_courses):
        """Get category-based course info for an order line."""
        categ_id, categ_name = order._get_line_hold_fire_category(line)
        if categ_id == 0:
            return 0, '', True  # always fired

        is_fired = fired_courses.get(str(categ_id), False)
        return categ_id, categ_name, is_fired

    def _order_has_ready_to_cook_line(self, order):
        """True if the order has at least one line the kitchen can act on.

        A line is "ready to cook" when:
        - it has no Hold & Fire category (always ready), or
        - its Hold & Fire category has been fired by staff.

        Combo children inherit their parent's category, so we evaluate
        only parent lines and treat them as representative.
        """
        try:
            fired = json.loads(order.kds_fired_courses or '{}')
        except (json.JSONDecodeError, TypeError):
            fired = {}

        for line in order.lines:
            if line.qty <= 0 or line.price_unit < 0:
                continue
            if line.combo_parent_id:
                continue
            categ_id, _ = order._get_line_hold_fire_category(line)
            if categ_id == 0:
                return True
            if fired.get(str(categ_id), False):
                return True
        return False

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

        # Hide orders whose every line is still held — kitchen has nothing
        # to cook on them yet. They reappear automatically when the cashier
        # fires any of their Hold & Fire categories (fire_course broadcasts
        # KDS_ORDER_UPDATE which triggers a frontend refetch).
        orders = orders.filtered(self._order_has_ready_to_cook_line)

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

            try:
                done_items = json.loads(order.kds_done_items or '{}')
            except (json.JSONDecodeError, TypeError):
                done_items = {}

            try:
                remake_data = json.loads(order.kds_remake_data or '{}')
            except (json.JSONDecodeError, TypeError):
                remake_data = {}

            try:
                fired_courses = json.loads(order.kds_fired_courses or '{}')
            except (json.JSONDecodeError, TypeError):
                fired_courses = {}

            lines = []
            has_active_remake = False
            course_groups_map = OrderedDict()

            for line in order.lines:
                if line.qty <= 0 or line.price_unit < 0:
                    continue

                # Combo children are rendered under their combo parent, not as
                # independent rows. Skip them here so the KDS cannot tick them
                # done independently.
                if line.combo_parent_id:
                    continue

                line_key = str(line.id)
                line_remake = remake_data.get(line_key, {})
                is_done = done_items.get(line_key, False)

                categ_id, course_name, is_fired = self._get_line_course_info(
                    order, line, fired_courses
                )

                if line_remake and not is_done:
                    has_active_remake = True

                combo_children = []
                has_pending_children = False
                child_course_categories = []  # (categ_id, categ_name, is_done)
                for child in line.combo_line_ids:
                    if child.qty <= 0 or child.price_unit < 0:
                        continue
                    child_categ_id, child_categ_name = order._get_line_hold_fire_category(child)
                    # A child is "held" if it has its own H&F category that differs
                    # from the parent's and is not yet fired.
                    child_held = (
                        child_categ_id > 0
                        and child_categ_id != categ_id
                        and not fired_courses.get(str(child_categ_id), False)
                    )
                    if child_held:
                        has_pending_children = True
                    child_is_done = done_items.get(str(child.id), False)
                    if child_categ_id > 0 and child_categ_id != categ_id:
                        child_course_categories.append((child_categ_id, child_categ_name, child_is_done))
                    combo_children.append({
                        'name': child.full_product_name or child.product_id.display_name,
                        'qty': child.qty,
                        'customer_note': child.note or '',
                        'held': child_held,
                        'held_category': child_categ_name if child_held else '',
                        'is_done': child_is_done,
                    })

                lines.append({
                    'id': line.id,
                    'uuid': line.uuid,
                    'product_name': line.full_product_name or line.product_id.display_name,
                    'qty': line.qty,
                    'customer_note': line.note or '',
                    'is_done': is_done,
                    'remake_count': line_remake.get('count', 0),
                    'remake_reason': line_remake.get('reason', ''),
                    'course_id': categ_id,
                    'course_name': course_name,
                    'is_fired': is_fired,
                    'combo_children': combo_children,
                    'has_pending_children': has_pending_children,
                })

                if categ_id > 0:
                    if categ_id not in course_groups_map:
                        course_groups_map[categ_id] = {
                            'id': categ_id,
                            'name': course_name,
                            'is_fired': is_fired,
                            'all_items_done': True,
                        }
                    if not is_done:
                        course_groups_map[categ_id]['all_items_done'] = False

                # Register combo children's own H&F categories so fire
                # buttons appear on KDS for held child categories.
                for cc_categ_id, cc_categ_name, cc_is_done in child_course_categories:
                    if cc_categ_id not in course_groups_map:
                        cc_is_fired = fired_courses.get(str(cc_categ_id), False)
                        course_groups_map[cc_categ_id] = {
                            'id': cc_categ_id,
                            'name': cc_categ_name,
                            'is_fired': cc_is_fired,
                            'all_items_done': True,
                        }
                    if not cc_is_done:
                        course_groups_map[cc_categ_id]['all_items_done'] = False

            course_groups = sorted(
                course_groups_map.values(), key=lambda g: g['name']
            )

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
                'course_groups': course_groups,
                'general_note': getattr(order, 'general_note', '') or '',
            })

        return result

    def _check_all_fired_done(self, order, done_items):
        """Check if all items in fired courses are done.

        Returns (all_done, course_completed) where all_done is True only when
        every line is either done or belongs to a fired course and is done.
        Lines in unfired H&F categories block all_done — the order stays
        active on KDS until every course is fired and its items are done.
        """
        try:
            fired_courses = json.loads(order.kds_fired_courses or '{}')
        except (json.JSONDecodeError, TypeError):
            fired_courses = {}

        all_fired_done = True
        course_items = {}

        for line in order.lines:
            if line.qty <= 0:
                continue
            categ_id, _ = order._get_line_hold_fire_category(line)
            is_done = done_items.get(str(line.id), False)

            if categ_id == 0:
                if not is_done:
                    all_fired_done = False
            elif fired_courses.get(str(categ_id), False):
                if not is_done:
                    all_fired_done = False
                course_items.setdefault(categ_id, []).append(is_done)
            else:
                # Unfired H&F category — line is still pending; block all_done
                all_fired_done = False

        course_completed = None
        for cid, statuses in course_items.items():
            if all(statuses):
                course_completed = cid

        return all_fired_done, course_completed

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
        """Mark all FIRED items as done. Held items are left untouched.

        If there are still held categories (not yet fired), the order stays
        on the KDS — only items in fired categories get bumped.
        """
        config = self._verify_kds_access(config_id, token)
        order = request.env['pos.order'].sudo().browse(int(order_id))
        if not order.exists() or order.config_id.id != config.id:
            return {'success': False, 'error': 'Order not found'}

        try:
            done_items = json.loads(order.kds_done_items or '{}')
        except (json.JSONDecodeError, TypeError):
            done_items = {}

        try:
            fired_courses = json.loads(order.kds_fired_courses or '{}')
        except (json.JSONDecodeError, TypeError):
            fired_courses = {}

        # Mark only items in fired (or non-hold-fire) categories as done
        for line in order.lines:
            if line.qty <= 0:
                continue
            categ_id, _ = order._get_line_hold_fire_category(line)
            if categ_id > 0 and not fired_courses.get(str(categ_id), False):
                continue  # held category — skip
            done_items[str(line.id)] = True

        # Decide final state: 'done' only if no categories remain held
        has_held_categories = any(not v for v in fired_courses.values())
        new_state = 'in_progress' if has_held_categories else 'done'

        order.write({
            'kds_state': new_state,
            'kds_done_items': json.dumps(done_items),
        })
        config._notify('KDS_ORDER_UPDATE', {
            'order_id': order.id,
            'kds_state': new_state,
            'kds_done_items': json.dumps(done_items),
        })
        return {'success': True, 'has_held_categories': has_held_categories}

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

        # Block toggling items in held courses
        line = request.env['pos.order.line'].sudo().browse(int(line_id))
        if line.exists():
            # Combo children cannot be toggled independently — the KDS does not
            # expose them as clickable rows, but guard defensively against
            # crafted requests.
            if line.combo_parent_id:
                return {'success': False, 'error': 'Combo children cannot be toggled'}
            categ_id, _ = order._get_line_hold_fire_category(line)
            if categ_id > 0:
                try:
                    fired_courses = json.loads(order.kds_fired_courses or '{}')
                except (json.JSONDecodeError, TypeError):
                    fired_courses = {}
                if not fired_courses.get(str(categ_id), False):
                    return {'success': False, 'error': 'Course not fired yet'}

        try:
            done_items = json.loads(order.kds_done_items or '{}')
        except (json.JSONDecodeError, TypeError):
            done_items = {}

        key = str(line_id)
        done_items[key] = not done_items.get(key, False)

        # Cascade the new state to combo children, but skip children whose
        # own H&F category is not yet fired (partial-done for mixed combos).
        if line.exists():
            new_state = done_items[key]
            try:
                fired_courses_for_cascade = json.loads(order.kds_fired_courses or '{}')
            except (json.JSONDecodeError, TypeError):
                fired_courses_for_cascade = {}
            parent_categ_id, _ = order._get_line_hold_fire_category(line)
            for child in line.combo_line_ids:
                child_categ_id, _ = order._get_line_hold_fire_category(child)
                # Skip held children: they have their own unfired H&F category
                if (child_categ_id > 0
                        and child_categ_id != parent_categ_id
                        and not fired_courses_for_cascade.get(str(child_categ_id), False)):
                    continue
                done_items[str(child.id)] = new_state

        all_done, course_completed = self._check_all_fired_done(order, done_items)

        vals = {'kds_done_items': json.dumps(done_items)}
        if all_done:
            vals['kds_state'] = 'done'
        elif order.kds_state == 'new':
            vals['kds_state'] = 'in_progress'

        order.write(vals)
        notify_data = {
            'order_id': order.id,
            'kds_state': vals.get('kds_state', order.kds_state),
            'kds_done_items': json.dumps(done_items),
        }
        if course_completed:
            notify_data['course_completed'] = course_completed
        config._notify('KDS_ORDER_UPDATE', notify_data)
        return {'success': True, 'all_done': all_done, 'course_completed': course_completed}

    @http.route('/pos-kds/recall/<int:config_id>', type='json', auth='public')
    def kds_recall_order(self, config_id, token=None, order_id=None, **kwargs):
        """Recall a bumped order back to the active KDS."""
        config = self._verify_kds_access(config_id, token)

        if order_id:
            order = request.env['pos.order'].sudo().browse(int(order_id))
        else:
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
            'kds_done_items': '{}',
        })
        return {'success': True, 'order_id': order.id}

    @http.route('/pos-kds/fire-course/<int:config_id>', type='json', auth='public')
    def kds_fire_course(self, config_id, token=None, order_id=None, category_id=None, **kwargs):
        """Fire a specific category group for kitchen preparation."""
        config = self._verify_kds_access(config_id, token)
        if not order_id or category_id is None:
            return {'success': False, 'error': 'Missing order_id or category_id'}

        order = request.env['pos.order'].sudo().browse(int(order_id))
        if not order.exists() or order.config_id.id != config.id:
            return {'success': False, 'error': 'Order not found'}

        order.fire_course(int(category_id))
        return {'success': True}

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

            try:
                fired_courses = json.loads(order.kds_fired_courses or '{}')
            except (json.JSONDecodeError, TypeError):
                fired_courses = {}

            changed = False
            for line in order.lines:
                if line.qty <= 0 or line.price_unit < 0:
                    continue
                # Combo children are handled through their combo parent.
                if line.combo_parent_id:
                    continue
                categ_id, _ = order._get_line_hold_fire_category(line)
                if categ_id > 0 and not fired_courses.get(str(categ_id), False):
                    continue

                line_name = line.full_product_name or line.product_id.display_name
                if line_name == product_name and not done_items.get(str(line.id), False):
                    done_items[str(line.id)] = True
                    # Cascade to combo children so state stays consistent.
                    for child in line.combo_line_ids:
                        done_items[str(child.id)] = True
                    changed = True
                    updated_count += 1

            if not changed:
                continue

            all_done, course_completed = self._check_all_fired_done(order, done_items)

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
                'kds_done_items': json.dumps(done_items),
            })

        return {
            'success': True,
            'updated_count': updated_count,
            'bumped_order_ids': bumped_order_ids,
        }

    @http.route('/pos-kds/batch-lines-done/<int:config_id>', type='json', auth='public')
    def kds_batch_lines_done(self, config_id, token=None, items=None, **kwargs):
        """Mark a specific list of order lines done.

        ``items`` is a list of ``{order_id, line_id}`` dicts. Combo parents
        cascade to their children, so the items aggregator on the KDS can group
        combos by ``(name, combo_children)`` and bump only the matching parents.
        """
        config = self._verify_kds_access(config_id, token)
        if not items:
            return {'success': False, 'error': 'Missing items'}

        by_order = {}
        for it in items:
            try:
                oid = int(it.get('order_id') or 0)
                lid = int(it.get('line_id') or 0)
            except (TypeError, ValueError):
                continue
            if oid and lid:
                by_order.setdefault(oid, []).append(lid)

        bumped_order_ids = []
        updated_count = 0

        for order_id, line_ids in by_order.items():
            order = request.env['pos.order'].sudo().browse(order_id)
            if not order.exists() or order.config_id.id != config.id:
                continue

            try:
                done_items = json.loads(order.kds_done_items or '{}')
            except (json.JSONDecodeError, TypeError):
                done_items = {}

            try:
                fired_courses = json.loads(order.kds_fired_courses or '{}')
            except (json.JSONDecodeError, TypeError):
                fired_courses = {}

            changed = False
            for line in request.env['pos.order.line'].sudo().browse(line_ids):
                if not line.exists() or line.order_id.id != order.id:
                    continue
                # Combo children are handled through their parent's cascade.
                if line.combo_parent_id:
                    continue
                categ_id, _ = order._get_line_hold_fire_category(line)
                if categ_id > 0 and not fired_courses.get(str(categ_id), False):
                    continue
                if done_items.get(str(line.id)):
                    continue
                done_items[str(line.id)] = True
                # Cascade parent → children so bookkeeping stays consistent.
                for child in line.combo_line_ids:
                    done_items[str(child.id)] = True
                changed = True
                updated_count += 1

            if not changed:
                continue

            all_done, _ = self._check_all_fired_done(order, done_items)
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
                'kds_done_items': json.dumps(done_items),
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
