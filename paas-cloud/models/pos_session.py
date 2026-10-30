from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """Reset sold-out flags scoped to this session's POS config.

        If the config restricts product categories, only reset products in
        those categories.  Otherwise reset all sold-out products (same as
        before but still safe in single-store setups).
        """
        config = self.config_id
        domain = [('is_sold_out', '=', True), ('available_in_pos', '=', True)]
        if config.limit_categories and config.iface_available_categ_ids:
            domain.append(('pos_categ_ids', 'in', config.iface_available_categ_ids.ids))
        sold_out_products = self.env['product.product'].search(domain)
        if sold_out_products:
            sold_out_products.write({'is_sold_out': False})

        return super()._validate_session(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )
