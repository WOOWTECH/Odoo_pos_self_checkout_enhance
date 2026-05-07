from odoo import models, fields, api


class PosCategory(models.Model):
    _inherit = 'pos.category'

    kds_hold_fire = fields.Boolean(
        string='Hold & Fire',
        default=False,
        help='When enabled, items in this category are held until fired by staff. '
             'When disabled, items fire immediately to the kitchen.',
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result += ['kds_hold_fire']
        return result
