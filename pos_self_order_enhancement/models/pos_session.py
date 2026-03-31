from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """Reset sold-out flags when POS session closes."""
        sold_out_products = self.env['product.product'].search([('is_sold_out', '=', True)])
        if sold_out_products:
            sold_out_products.write({'is_sold_out': False})

        return super()._validate_session(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )
