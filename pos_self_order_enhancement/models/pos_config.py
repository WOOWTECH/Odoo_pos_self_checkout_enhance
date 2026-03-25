from odoo import models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    def _compute_selection_pay_after(self):
        """
        Override to remove Enterprise version restriction from 'each' option.
        This allows Community version to use the 'Pay per Order' feature.
        """
        return [
            ('meal', '餐點'),
            ('each', '整單'),
        ]
