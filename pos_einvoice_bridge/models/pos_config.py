from odoo import models, fields, api


class PosConfig(models.Model):
    _inherit = 'pos.config'

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
