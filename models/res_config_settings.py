from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_self_ordering_takeaway_url = fields.Char(
        related="pos_config_id.self_ordering_url",
        string="Takeaway Self-Order URL (外賣自助連結)",
        readonly=True,
    )
