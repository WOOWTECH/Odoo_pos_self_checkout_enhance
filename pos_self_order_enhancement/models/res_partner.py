from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    portal_pos_config_ids = fields.Many2many(
        'pos.config',
        'res_partner_pos_config_portal_rel',
        'partner_id', 'config_id',
        string='Portal POS Configs',
        help="POS configurations this portal user can access from their "
             "'My Account' page. Assign one config to take the user straight "
             "to that shop's POS; assign multiple and the user gets a shop "
             "picker at /my/pos. Leave empty to disable portal POS access.",
    )
