import uuid

from odoo import models, fields, api, _
from odoo.osv.expression import OR


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
    ecpay_seller_tax_id = fields.Char(
        related='company_id.seller_Identifier',
        string='Seller Tax ID (賣方統編)',
        readonly=True,
    )
    einvoice_printer_id = fields.Many2one(
        'pos.printer',
        string='E-Invoice Printer (電子發票印表機)',
        domain="[('printer_type', '=', 'network_escpos'), ('id', 'in', printer_ids)]",
        help="ESC/POS printer used to print Taiwan 電子統一發票 receipts. "
             "If empty, the first network ESC/POS printer on this POS is used. "
             "Leave kitchen-routed printers (those with Printed Product Categories) "
             "unselected here so kitchen tickets and invoices land on separate devices.",
    )

    @api.model
    def _load_pos_self_data_fields(self, config_id):
        params = super()._load_pos_self_data_fields(config_id)
        # When params is empty, search_read returns ALL fields (Odoo convention).
        # Only append our fields if the parent already specified a field list;
        # otherwise, returning a partial list would suppress every other field.
        if params:
            params.append('ecpay_einvoice_enabled')
            params.append('einvoice_printer_id')
        return params

    def _compute_selection_pay_after(self):
        """
        Override to remove Enterprise version restriction from 'each' option.
        This allows Community version to use the 'Pay per Order' feature.
        """
        return [
            ('meal', _('Meal')),
            ('each', _('Each Order')),
        ]

    def read_config_open_orders(self, domain, record_ids=None):
        if record_ids is None:
            record_ids = []
        """Include paid payment-gated orders in POS sync.

        POS JS only requests state='draft' orders. Payment-gated orders
        transition draft→paid before POS sees them. We inject paid gated
        orders into the domain so POS discovers them during sync.
        """
        if 'pos.order' in domain:
            paid_gated = [
                ('state', 'in', ['paid', 'done', 'invoiced']),
                ('self_order_payment_status', '=', 'paid'),
                ('session_id', '=', self.current_session_id.id),
            ]
            domain['pos.order'] = OR([domain['pos.order'], paid_gated])
        return super().read_config_open_orders(domain, record_ids)
