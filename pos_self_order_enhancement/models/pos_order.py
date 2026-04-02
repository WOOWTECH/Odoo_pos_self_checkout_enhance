import json

from odoo import models, fields, api


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

    # ── helpers ──────────────────────────────────────────────

    def _get_line_hold_fire_category(self, line):
        """Return (category_id, category_name) if the line's category has Hold & Fire enabled.

        Returns (0, '') if no category or Hold & Fire is disabled (always fired).
        """
        categs = line.product_id.pos_categ_ids
        if categs and categs[0].kds_hold_fire:
            return categs[0].id, categs[0].name
        return 0, ''

    def _compute_fired_courses(self):
        """Build the kds_fired_courses JSON for this order.

        Auto-fires the first hold-fire category (by name alphabetically).
        """
        self.ensure_one()
        categories = {}  # {categ_id: categ_name}
        for line in self.lines:
            if line.qty <= 0:
                continue
            categ_id, categ_name = self._get_line_hold_fire_category(line)
            if categ_id > 0:
                categories[categ_id] = categ_name

        if not categories:
            return '{}'

        # Auto-fire the first category alphabetically
        sorted_categs = sorted(categories.items(), key=lambda x: x[1])
        first_id = sorted_categs[0][0]

        fired = {}
        for categ_id in categories:
            fired[str(categ_id)] = (categ_id == first_id)
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
        vals = {'kds_sent_to_kitchen': True}
        for order in self:
            if not order.kds_state:
                vals['kds_state'] = 'new'
                break
        self.write(vals)

        # Initialize course fire state for each order
        for order in self:
            fired_json = order._compute_fired_courses()
            if fired_json != '{}':
                order.write({'kds_fired_courses': fired_json})

        for order in self:
            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': order.kds_state,
                    })
        return True

    def mark_served(self):
        """Called by POS frontend when staff confirms food has been served."""
        self.write({'kds_state': 'served'})
        for order in self:
            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': 'served',
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

            for lid in line_ids:
                key = str(lid)
                if key not in remake_data:
                    remake_data[key] = {'count': 0, 'reason': ''}
                remake_data[key]['count'] += 1
                remake_data[key]['reason'] = reason
                done_items[key] = False

            order.write({
                'kds_state': 'in_progress',
                'kds_done_items': json.dumps(done_items),
                'kds_remake_data': json.dumps(remake_data),
            })

            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': 'new',
                        'is_remake': True,
                    })
        return True

    def _send_notification(self, order_ids):
        """Extend to also notify KDS screens (only for kitchen-confirmed orders)."""
        super()._send_notification(order_ids)
        config_ids = order_ids.config_id
        for config in config_ids:
            if config.kds_enabled:
                kitchen_orders = order_ids.filtered(lambda o: o.kds_sent_to_kitchen)
                if kitchen_orders:
                    config._notify('KDS_ORDER_UPDATE', {})

    _KDS_PROTECTED_FIELDS = (
        'kds_state', 'kds_sent_to_kitchen', 'kds_done_items',
        'kds_remake_data', 'kds_fired_courses',
    )

    @api.model
    def sync_from_ui(self, orders):
        """Protect KDS fields from frontend overwrite; reset kds_state on new lines."""
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

        if existing_order_ids:
            updated_orders = self.browse(existing_order_ids).exists()
            for order in updated_orders:
                if order.kds_state in ('in_progress', 'done'):
                    prev_ids = old_line_ids.get(order.id, set())
                    curr_ids = set(order.lines.ids)
                    new_lines = curr_ids - prev_ids
                    if new_lines:
                        try:
                            fired = json.loads(order.kds_fired_courses or '{}')
                        except (json.JSONDecodeError, TypeError):
                            fired = {}

                        new_line_records = self.env['pos.order.line'].browse(list(new_lines))
                        for line in new_line_records:
                            categ_id, _ = order._get_line_hold_fire_category(line)
                            if categ_id > 0 and str(categ_id) not in fired:
                                fired[str(categ_id)] = False

                        order.write({
                            'kds_state': 'new',
                            'kds_done_items': '{}',
                            'kds_fired_courses': json.dumps(fired),
                        })

        return result
