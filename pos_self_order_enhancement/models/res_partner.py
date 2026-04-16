from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    portal_pos_config_id = fields.Many2one(
        'pos.config',
        string='Portal POS Config',
        help="POS configuration this portal user can access from their "
             "'My Account' page. Leave empty to disable portal POS access for "
             "this partner.",
    )
