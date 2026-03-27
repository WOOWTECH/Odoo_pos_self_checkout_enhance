from odoo import models, _


class PosConfig(models.Model):
    _inherit = 'pos.config'

    def _compute_selection_pay_after(self):
        """
        Override to remove Enterprise version restriction from 'each' option.
        This allows Community version to use the 'Pay per Order' feature.
        """
        return [
            ('meal', _('Meal')),
            ('each', _('Each Order')),
        ]
