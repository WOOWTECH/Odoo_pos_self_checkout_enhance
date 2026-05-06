import json
import logging
import requests

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.osv.expression import OR

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    kds_state = fields.Selection([
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('served', 'Served'),
    ], string='Kitchen Status', default='new', index=True)

    kds_done_items = fields.Text(
        string='KDS Done Items',
        default='{}',
        help='JSON dict of line UUIDs marked as done on the KDS',
    )

    kds_sent_to_kitchen = fields.Boolean(
        string='Sent to Kitchen by Staff',
        default=False,
        help='Set to True when FOH staff clicks the Order button to send to kitchen',
    )

    kds_remake_data = fields.Text(
        string='KDS Remake Data',
        default='{}',
        help='JSON: {"<line_id>": {"count": N, "reason": "..."}}',
    )

    kds_fired_courses = fields.Text(
        string='KDS Fired Courses',
        default='{}',
        help='JSON dict: {"<category_id>": true/false}. Tracks which category groups are fired.',
    )

    kds_served_items = fields.Text(
        string='KDS Served Items',
        default='{}',
        help='JSON dict: {"<line_id>": true}. Tracks which items have been served to the table.',
    )

    # ── Payment Gate (pay-per-order) ──────────────────────────
    self_order_payment_status = fields.Selection([
        ('none', 'No Payment Gate'),
        ('pending_online', 'Pending Online Payment'),
        ('pending_counter', 'Pending Counter Payment'),
        ('paid', 'Payment Confirmed'),
    ], string='Self-Order Payment Status', default='none',
       help='Controls when POS/KDS is notified about self-order orders in pay-per-order mode.')

    # ── helpers ──────────────────────────────────────────────

    @api.model
    def action_lookup_tax_id(self, tax_id):
        """Look up company name from Taiwan GCIS open data by 統一編號.

        Tries the company registry first, then the business registry.
        Returns {'success': True, 'name': '...'} or {'success': False}.
        """
        if not tax_id or not isinstance(tax_id, str) or len(tax_id) != 8 or not tax_id.isdigit():
            return {'success': False, 'error': 'Invalid tax ID format'}

        # Company registry (公司登記)
        company_url = (
            'https://data.gcis.nat.gov.tw/od/data/api/'
            '236EE382-4942-41A9-BD03-CA0709025E7C'
            '?$format=json&$filter=Business_Accounting_NO eq ' + tax_id
            + '&$skip=0&$top=1'
        )

        for url, name_key in [(company_url, 'Company_Name')]:
            try:
                resp = requests.get(url, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list) and data[0].get(name_key):
                        return {'success': True, 'name': data[0][name_key]}
            except Exception:
                _logger.debug("GCIS lookup failed for %s", tax_id, exc_info=True)

        return {'success': False, 'error': 'Company not found'}

    def _get_line_hold_fire_category(self, line):
        """Return (category_id, category_name) for the line's effective Hold & Fire category.

        Checks the line's own product category first; falls back to the combo
        parent only if the child has no H&F category of its own.  This lets
        combo choices declare their own Hold & Fire course (e.g. a dessert
        choice inside a non-H&F lunch set combo).

        Returns (0, '') if no H&F category found (always fired).
        """
        candidates = [line]
        if line.combo_parent_id:
            candidates.append(line.combo_parent_id)
        for candidate in candidates:
            categs = candidate.product_id.pos_categ_ids
            if categs and categs[0].kds_hold_fire:
                return categs[0].id, categs[0].name
        return 0, ''

    def _compute_fired_courses(self):
        """Build the kds_fired_courses JSON for this order.

        All hold-fire categories start held — staff must manually fire each
        category from the POS.
        """
        self.ensure_one()
        categories = set()
        for line in self.lines:
            if line.qty <= 0:
                continue
            categ_id, _ = self._get_line_hold_fire_category(line)
            if categ_id > 0:
                categories.add(categ_id)

        if not categories:
            return '{}'

        fired = {str(cid): False for cid in categories}
        return json.dumps(fired)

    # ── course actions ───────────────────────────────────────

    def fire_course(self, category_id):
        """Fire a specific category group for kitchen preparation."""
        for order in self:
            try:
                fired = json.loads(order.kds_fired_courses or '{}')
            except (json.JSONDecodeError, TypeError):
                fired = {}

            key = str(category_id)
            if key not in fired:
                continue

            fired[key] = True
            vals = {'kds_fired_courses': json.dumps(fired)}

            # If order was done (all previous courses complete), reset to in_progress
            if order.kds_state == 'done':
                vals['kds_state'] = 'in_progress'

            # Un-done combo parents that have a child in the just-fired
            # category, so the KDS card reverts to active state and the
            # newly-fired child appears at normal brightness.
            try:
                done_items = json.loads(order.kds_done_items or '{}')
            except (json.JSONDecodeError, TypeError):
                done_items = {}

            changed_done = False
            for line in order.lines:
                if line.combo_parent_id:
                    continue
                has_fired_child = False
                for child in line.combo_line_ids:
                    child_categ_id, _ = order._get_line_hold_fire_category(child)
                    if child_categ_id == category_id:
                        has_fired_child = True
                        if done_items.get(str(child.id), False):
                            done_items[str(child.id)] = False
                            changed_done = True
                if has_fired_child and done_items.get(str(line.id), False):
                    done_items[str(line.id)] = False
                    changed_done = True

            if changed_done:
                vals['kds_done_items'] = json.dumps(done_items)
                if order.kds_state != 'done' and 'kds_state' not in vals:
                    vals['kds_state'] = 'in_progress'

            order.write(vals)
            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': vals.get('kds_state', order.kds_state),
                        'course_fired': category_id,
                    })
        return True

    # ── existing methods (modified) ──────────────────────────

    def mark_sent_to_kitchen(self):
        """Called by POS frontend when staff clicks Order button."""
        # Guard: reject unpaid self-order orders
        blocked = self.filtered(
            lambda o: o.self_order_payment_status in ('pending_online', 'pending_counter')
        )
        if blocked:
            raise UserError(
                "Cannot send to kitchen: payment not confirmed.\n%s"
                % ', '.join(blocked.mapped('name'))
            )

        # Set kds_sent_to_kitchen on all orders, but only set kds_state
        # on orders that don't already have one (avoids resetting
        # in_progress/done orders back to 'new' in batch writes).
        need_state = self.filtered(lambda o: not o.kds_state)
        already_has_state = self - need_state
        if need_state:
            need_state.write({'kds_sent_to_kitchen': True, 'kds_state': 'new'})
        if already_has_state:
            already_has_state.write({'kds_sent_to_kitchen': True})

        # Initialize / merge course fire state for each order.
        # Preserve any categories already fired by staff — only add newly
        # introduced categories as held.
        for order in self:
            try:
                existing = json.loads(order.kds_fired_courses or '{}')
            except (json.JSONDecodeError, TypeError):
                existing = {}

            current_categories = set()
            for line in order.lines:
                if line.qty <= 0:
                    continue
                categ_id, _ = order._get_line_hold_fire_category(line)
                if categ_id > 0:
                    current_categories.add(str(categ_id))

            merged = dict(existing)
            for key in current_categories:
                if key not in merged:
                    merged[key] = False

            if merged:
                order.write({'kds_fired_courses': json.dumps(merged)})

        for order in self:
            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': order.kds_state,
                    })
        return True

    def mark_served(self):
        """Mark done items as served. Only sets kds_state='served' when ALL items are served."""
        for order in self:
            try:
                done_items = json.loads(order.kds_done_items or '{}')
            except (json.JSONDecodeError, TypeError):
                done_items = {}
            try:
                served_items = json.loads(order.kds_served_items or '{}')
            except (json.JSONDecodeError, TypeError):
                served_items = {}

            # Mark all done-but-not-served items as served
            for key, is_done in done_items.items():
                if is_done and not served_items.get(key, False):
                    served_items[key] = True

            vals = {'kds_served_items': json.dumps(served_items)}

            # Check if ALL items are now served
            all_served = True
            for line in order.lines:
                if line.qty > 0 and not served_items.get(str(line.id), False):
                    all_served = False
                    break

            if all_served:
                vals['kds_state'] = 'served'

            order.write(vals)
            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': vals.get('kds_state', order.kds_state),
                        'kds_served_items': json.dumps(served_items),
                    })
        return True

    def mark_remake(self, line_ids, reason='remake'):
        """Called by POS frontend to send items back to kitchen for remake."""
        for order in self:
            try:
                remake_data = json.loads(order.kds_remake_data or '{}')
            except (json.JSONDecodeError, TypeError):
                remake_data = {}

            done_items = {}
            if order.kds_state in ('done', 'served'):
                for line in order.lines:
                    if line.qty > 0:
                        done_items[str(line.id)] = True
            else:
                try:
                    done_items = json.loads(order.kds_done_items or '{}')
                except (json.JSONDecodeError, TypeError):
                    done_items = {}

            try:
                served_items = json.loads(order.kds_served_items or '{}')
            except (json.JSONDecodeError, TypeError):
                served_items = {}

            for lid in line_ids:
                key = str(lid)
                if key not in remake_data:
                    remake_data[key] = {'count': 0, 'reason': ''}
                remake_data[key]['count'] += 1
                remake_data[key]['reason'] = reason
                done_items[key] = False
                served_items.pop(key, None)  # clear served status

            order.write({
                'kds_state': 'in_progress',
                'kds_done_items': json.dumps(done_items),
                'kds_remake_data': json.dumps(remake_data),
                'kds_served_items': json.dumps(served_items),
            })

            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': 'new',
                        'is_remake': True,
                        'kds_done_items': json.dumps(done_items),
                        'kds_remake_data': json.dumps(remake_data),
                        'kds_served_items': json.dumps(served_items),
                    })
        return True

    def _send_notification(self, order_ids):
        """Extend to also notify KDS screens (only for kitchen-confirmed orders).

        POS is always notified so staff can see orders. Kitchen (KDS) is only
        notified for orders that have been sent to kitchen (kds_sent_to_kitchen=True).
        The mark_sent_to_kitchen() guard prevents unpaid orders from reaching kitchen.
        """
        if self.env.context.get('suppress_self_order_notification'):
            return

        # Notify POS for ALL orders (staff needs to see them)
        super()._send_notification(order_ids)

        config_ids = order_ids.config_id
        for config in config_ids:
            if config.kds_enabled:
                kitchen_orders = order_ids.filtered(
                    lambda o, c=config: o.kds_sent_to_kitchen and o.config_id == c
                )
                if kitchen_orders:
                    config._notify('KDS_ORDER_UPDATE', {})

    _KDS_PROTECTED_FIELDS = (
        'kds_state', 'kds_sent_to_kitchen', 'kds_done_items',
        'kds_remake_data', 'kds_fired_courses', 'kds_served_items',
        'self_order_payment_status',
    )

    @api.model
    def _load_pos_data_domain(self, data):
        """Include all self-order orders (including pending) + paid gated orders."""
        domain = super()._load_pos_data_domain(data)
        session_id = data['pos.session']['data'][0]['id']
        paid_gated = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('self_order_payment_status', '=', 'paid'),
            ('session_id', '=', session_id),
        ]
        return OR([domain, paid_gated])

    @api.model
    def sync_from_ui(self, orders):
        """Protect KDS fields from frontend overwrite."""
        for order in orders:
            for field in self._KDS_PROTECTED_FIELDS:
                order.pop(field, None)

        existing_order_ids = []
        for order in orders:
            if order.get('id') and isinstance(order['id'], int):
                existing_order_ids.append(order['id'])

        old_line_ids = {}
        if existing_order_ids:
            for order in self.browse(existing_order_ids).exists():
                old_line_ids[order.id] = set(order.lines.ids)

        result = super().sync_from_ui(orders)

        # When new lines are added to an already-sent order, only merge any
        # newly introduced Hold & Fire categories into kds_fired_courses.
        # Do NOT touch kds_done_items / kds_served_items / kds_state — those
        # are owned by the kitchen workflow and adding new lines must never
        # un-mark previously done or served items (that would resurrect them
        # in KDS and confuse staff).
        if existing_order_ids:
            updated_orders = self.browse(existing_order_ids).exists()
            for order in updated_orders:
                if not order.kds_sent_to_kitchen:
                    continue
                prev_ids = old_line_ids.get(order.id, set())
                curr_ids = set(order.lines.ids)
                new_lines = curr_ids - prev_ids
                if not new_lines:
                    continue

                try:
                    fired = json.loads(order.kds_fired_courses or '{}')
                except (json.JSONDecodeError, TypeError):
                    fired = {}

                new_line_records = self.env['pos.order.line'].browse(list(new_lines))
                changed = False
                for line in new_line_records:
                    categ_id, _ = order._get_line_hold_fire_category(line)
                    if categ_id > 0 and str(categ_id) not in fired:
                        fired[str(categ_id)] = False
                        changed = True

                if changed:
                    order.write({'kds_fired_courses': json.dumps(fired)})

        return result

    # ── Payment Gate: detect payment completion ───────────

    def _process_saved_order(self, draft):
        """Sync payment-gated orders to POS BEFORE state changes to 'paid'.

        POS can only load 'draft' orders (JS-hardcoded domain in sync).
        We sync while still draft, then super() changes state to 'paid'.
        read_config_open_orders override ensures paid gated orders are
        also found during the async POS sync that follows.
        """
        gated = self.filtered(
            lambda o: o.self_order_payment_status in ('pending_online', 'pending_counter')
        )
        if gated:
            super(PosOrder, gated).write({'self_order_payment_status': 'paid'})
            for config in gated.config_id:
                config.notify_synchronisation(
                    config.current_session_id.id,
                    self.env.context.get('login_number', 0)
                )
                config._notify('ORDER_STATE_CHANGED', {})
            tables = gated.mapped('table_id')
            if tables:
                gated.send_table_count_notification(tables)

            # Auto-fire paid orders to kitchen — ONLY for meal mode.
            # In meal mode, payment confirmation = kitchen starts immediately.
            # In each mode, staff must manually click Order to send to kitchen.
            to_fire = gated.filtered(
                lambda o: not o.kds_sent_to_kitchen
                          and o.config_id.kds_enabled
                          and o.config_id.self_ordering_pay_after == 'meal'
            )
            if to_fire:
                to_fire.mark_sent_to_kitchen()
                # Pre-fire ALL Hold & Fire categories — in pay-per-order
                # mode there is no cashier to sequence courses, so
                # everything must be immediately visible to the kitchen.
                for order in to_fire:
                    try:
                        fired = json.loads(order.kds_fired_courses or '{}')
                    except (json.JSONDecodeError, TypeError):
                        fired = {}
                    if fired and not all(fired.values()):
                        for key in fired:
                            fired[key] = True
                        order.write({'kds_fired_courses': json.dumps(fired)})

                # Notify POS frontend to print kitchen ticket.
                # Kitchen printing is frontend-controlled (sendOrderInPreparation),
                # so we signal via bus for the POS to trigger printing.
                for order in to_fire:
                    for config in order.config_id:
                        config._notify('AUTO_FIRE_PRINT', {
                            'order_id': order.id,
                        })

        return super()._process_saved_order(draft)

    def write(self, vals):
        """Update payment status when payment-gated orders become paid.

        Notifications are handled by _process_saved_order() (before state
        transition).  This override just ensures the status field is updated
        for any remaining code paths (e.g. counter payment via POS cashier).
        """
        completing = self.env['pos.order']
        if vals.get('state') in ('paid', 'done', 'invoiced'):
            completing = self.filtered(
                lambda o: o.self_order_payment_status in ('pending_online', 'pending_counter')
            )

        res = super().write(vals)

        if completing:
            # Update payment status for orders not already handled by _process_saved_order
            still_pending = completing.filtered(
                lambda o: o.self_order_payment_status != 'paid'
            )
            if still_pending:
                super(PosOrder, still_pending).write({'self_order_payment_status': 'paid'})
                for config in still_pending.config_id:
                    config.notify_synchronisation(
                        config.current_session_id.id,
                        self.env.context.get('login_number', 0)
                    )
                    config._notify('ORDER_STATE_CHANGED', {})
                tables = still_pending.mapped('table_id')
                if tables:
                    still_pending.send_table_count_notification(tables)

        return res
