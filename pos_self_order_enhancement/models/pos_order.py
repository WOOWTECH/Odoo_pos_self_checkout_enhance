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

    def _send_notification(self, order_ids):
        """Extend to also notify KDS screens."""
        super()._send_notification(order_ids)
        config_ids = order_ids.config_id
        for config in config_ids:
            if config.kds_enabled:
                config._notify('KDS_ORDER_UPDATE', {})

    @api.model
    def sync_from_ui(self, orders):
        """Reset kds_state to 'new' when existing orders get new lines."""
        existing_order_ids = []
        for order in orders:
            if order.get('id') and isinstance(order['id'], int):
                existing_order_ids.append(order['id'])

        result = super().sync_from_ui(orders)

        if existing_order_ids:
            updated_orders = self.browse(existing_order_ids).exists()
            for order in updated_orders:
                if order.kds_state in ('in_progress', 'done'):
                    order.write({
                        'kds_state': 'new',
                        'kds_done_items': '{}',
                    })

        return result
