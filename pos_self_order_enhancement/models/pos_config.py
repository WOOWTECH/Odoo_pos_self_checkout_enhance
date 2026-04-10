import uuid

from odoo import models, fields, api, _


class PosConfig(models.Model):
    _inherit = 'pos.config'

    kds_enabled = fields.Boolean('Kitchen Display', default=False)
    kds_access_token = fields.Char(
        'KDS Access Token',
        copy=False,
        default=lambda self: uuid.uuid4().hex[:16],
    )
    kds_url = fields.Char('KDS URL', compute='_compute_kds_url')

    @api.depends('kds_enabled', 'kds_access_token')
    def _compute_kds_url(self):
        base_url = self.env['pos.session'].get_base_url()
        for record in self:
            if record.kds_enabled and record.kds_access_token:
                record.kds_url = f"{base_url}/pos-kds/{record.id}?token={record.kds_access_token}"
            else:
                record.kds_url = ''

    def action_regenerate_kds_token(self):
        self.ensure_one()
        self.kds_access_token = uuid.uuid4().hex[:16]

    # ── E-Invoice (電子發票) ────────────────────────────────
    ecpay_einvoice_enabled = fields.Boolean('E-Invoice (電子發票)', default=False)
    ecpay_einvoice_env = fields.Selection([
        ('stage', 'Staging (測試)'),
        ('prod', 'Production (正式)'),
    ], string='ECPay Environment', default='stage')
    ecpay_einvoice_merchant_id = fields.Char('ECPay Merchant ID (特店編號)')
    ecpay_einvoice_hash_key = fields.Char('ECPay HashKey')
    ecpay_einvoice_hash_iv = fields.Char('ECPay HashIV')
    ecpay_seller_tax_id = fields.Char('Seller Tax ID (賣方統編)')

    def _compute_selection_pay_after(self):
        """
        Override to remove Enterprise version restriction from 'each' option.
        This allows Community version to use the 'Pay per Order' feature.
        """
        return [
            ('meal', _('Meal')),
            ('each', _('Each Order')),
        ]
