import json as json_lib

from odoo import models, fields, api


class PosOrder(models.Model):
    _inherit = 'pos.order'

    kds_state = fields.Selection([
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
    ], string='Kitchen Status', default='new', index=True)

    kds_done_items = fields.Text(
        string='KDS Done Items',
        default='{}',
        help='JSON dict of line UUIDs marked as done on the KDS',
    )

    def _is_sent_to_kitchen(self):
        """Check if staff clicked 訂單 (lines populated in last_order_preparation_change)."""
        if not self.last_order_preparation_change:
            return False
        try:
            change = json_lib.loads(self.last_order_preparation_change)
            return bool(change.get('lines'))
        except (json_lib.JSONDecodeError, TypeError):
            return False

    def _send_notification(self, order_ids):
        """Extend to also notify KDS screens (only for kitchen-confirmed orders)."""
        super()._send_notification(order_ids)
        config_ids = order_ids.config_id
        for config in config_ids:
            if config.kds_enabled:
                kitchen_orders = order_ids.filtered(lambda o: o._is_sent_to_kitchen())
                if kitchen_orders:
                    config._notify('KDS_ORDER_UPDATE', {})

    @api.model
    def sync_from_ui(self, orders):
        """Reset kds_state to 'new' only when new lines are actually added."""
        existing_order_ids = []
        for order in orders:
            if order.get('id') and isinstance(order['id'], int):
                existing_order_ids.append(order['id'])

        # Capture line IDs before sync
        old_line_ids = {}
        if existing_order_ids:
            for order in self.browse(existing_order_ids).exists():
                old_line_ids[order.id] = set(order.lines.ids)

        result = super().sync_from_ui(orders)

        # Only reset kds_state if genuinely new lines were added
        if existing_order_ids:
            updated_orders = self.browse(existing_order_ids).exists()
            for order in updated_orders:
                if order.kds_state in ('in_progress', 'done'):
                    prev_ids = old_line_ids.get(order.id, set())
                    curr_ids = set(order.lines.ids)
                    if curr_ids - prev_ids:
                        order.write({
                            'kds_state': 'new',
                            'kds_done_items': '{}',
                        })

        return result
