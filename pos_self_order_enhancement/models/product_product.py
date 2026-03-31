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
            for record in self:
                record._send_availability_status()
        return res
