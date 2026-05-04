from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_sold_out = fields.Boolean(
        string='Sold Out (86)',
        default=False,
        help='Temporarily mark as sold out. Auto-resets when POS session closes.',
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result += ['is_sold_out']
        return result

    def write(self, vals):
        res = super().write(vals)
        if 'is_sold_out' in vals:
            # Notify connected POS sessions about sold-out status change
            # via the bus so the self-order UI updates in real time.
            for record in self:
                config_ids = self.env['pos.config'].sudo().search([
                    ('self_ordering_mode', 'in', ['mobile', 'kiosk']),
                    ('current_session_id', '!=', False),
                ])
                for config in config_ids:
                    self.env['bus.bus']._sendone(
                        f'pos_config-{config.access_token}',
                        'PRODUCT_AVAILABILITY',
                        {'id': record.id, 'is_sold_out': record.is_sold_out},
                    )
        return res
