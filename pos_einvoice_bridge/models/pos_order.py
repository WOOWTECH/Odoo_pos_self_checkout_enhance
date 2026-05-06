import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    # ── E-Invoice (電子發票) ─────────────────────────────────
    ecpay_invoice_id = fields.Many2one('uniform.invoice', string='統一發票', readonly=True, copy=False)
    tw_invoice_number = fields.Char('Invoice Number (發票號碼)')
    tw_invoice_random_code = fields.Char('Random Code (隨機碼)')
    tw_carrier_type = fields.Selection([
        ('print', 'Print (列印)'),
        ('mobile', 'Mobile Barcode (手機條碼)'),
        ('donation', 'Donation (捐贈)'),
        ('b2b', 'B2B (統編)'),
    ], string='Carrier Type (載具類型)')
    tw_carrier_num = fields.Char('Carrier Number (載具號碼)')
    tw_love_code = fields.Char('Love Code (愛心碼)')
    tw_buyer_tax_id = fields.Char('Buyer Tax ID (買方統編)')
    tw_buyer_name = fields.Char('Buyer Name (買方名稱)')
    tw_b2b_print = fields.Boolean('B2B Print Paper', default=True,
        help='When carrier type is B2B, whether to print a paper invoice')
    tw_invoice_status = fields.Selection([
        ('none', 'None'),
        ('issued', 'Issued (已開立)'),
        ('voided', 'Voided (已作廢)'),
    ], string='Invoice Status', default='none')
    tw_qrcode_left = fields.Text('QR Code Left')
    tw_qrcode_right = fields.Text('QR Code Right')
    tw_pos_barcode = fields.Text('POS Barcode')

    _EINVOICE_PROTECTED_FIELDS = (
        'ecpay_invoice_id',
        'tw_invoice_number', 'tw_invoice_random_code', 'tw_invoice_status',
        'tw_qrcode_left', 'tw_qrcode_right', 'tw_pos_barcode',
    )

    @api.model
    def sync_from_ui(self, orders):
        """Protect e-invoice fields from frontend overwrite."""
        for order in orders:
            for field in self._EINVOICE_PROTECTED_FIELDS:
                order.pop(field, None)
        return super().sync_from_ui(orders)

    # ── E-Invoice RPC methods ─────────────────────────────

    def action_issue_einvoice(self, carrier_data):
        """Issue e-invoice via ECPay SDK (ecpay_invoice_tw).

        Creates a uniform.invoice record so the invoice appears in the
        統一發票 admin page.  Called from POS frontend after payment.
        """
        import datetime as _dt

        self.ensure_one()
        config = self.config_id
        if not config.ecpay_einvoice_enabled:
            return {'success': False, 'error': 'E-Invoice not enabled'}

        # Skip if already issued (e.g. via account.move auto-invoice flow)
        if self.ecpay_invoice_id or self.tw_invoice_status == 'issued':
            return {
                'success': True,
                'invoice_no': self.tw_invoice_number or '',
                'random_code': self.tw_invoice_random_code or '',
                'qrcode_left': self.tw_qrcode_left or '',
                'qrcode_right': self.tw_qrcode_right or '',
                'pos_barcode': self.tw_pos_barcode or '',
            }

        company = self.env.company
        if not company.ecpay_MerchantID or not company.ecpay_HashKey or not company.ecpay_HashIV:
            return {'success': False, 'error': '綠界電子發票連線設定不完整 ECPay credentials not configured'}

        carrier_type = carrier_data.get('carrier_type', 'print')
        carrier_num = carrier_data.get('carrier_num', '')
        love_code = carrier_data.get('love_code', '')
        buyer_tax_id = carrier_data.get('buyer_tax_id', '')
        buyer_name = carrier_data.get('buyer_name', '')

        from odoo.addons.ecpay_invoice_tw.sdk.ecpay_main import EcpayInvoice

        invoice_sdk = EcpayInvoice()

        # Initialize SDK with company credentials (reuse ecpay_invoice_tw pattern)
        self.env['account.move'].ecpay_invoice_init(
            invoice_sdk, 'B2CInvoice/Issue', 'INVOICE', company_id=company
        )

        # Create uniform.invoice stub (auto-generates related_number)
        ui_record = self.env['uniform.invoice'].create({
            'company_id': company.id,
        })

        # Build items from pos.order.lines
        items = []
        items_total = 0
        for i, line in enumerate(self.lines, 1):
            if line.qty <= 0:
                continue
            qty = max(int(line.qty), 1)
            item_amount = int(round(line.price_subtotal_incl))
            item_price = round(item_amount / qty, 2)
            items.append({
                'ItemSeq': i,
                'ItemName': (line.full_product_name or line.product_id.name or 'Item')[:30],
                'ItemCount': qty,
                'ItemWord': '份',
                'ItemPrice': item_price,
                'ItemTaxType': '1',
                'ItemAmount': item_amount,
                'ItemRemark': '',
            })
            items_total += item_amount

        if not items:
            ui_record.unlink()
            return {'success': False, 'error': 'Order has no lines'}

        sales_amount = items_total

        # Determine flags
        is_donation = carrier_type == 'donation'
        is_b2b = carrier_type == 'b2b' and buyer_tax_id
        print_flag = '1' if (carrier_type == 'print' or is_b2b) else '0'
        ecpay_carrier_type = '3' if carrier_type == 'mobile' else ''

        partner = self.partner_id
        if is_b2b and buyer_name:
            customer_name = buyer_name
        elif partner:
            customer_name = partner.name
        else:
            customer_name = '顧客'
        invoice_sdk.Send['RelateNumber'] = ui_record.related_number
        invoice_sdk.Send['CustomerIdentifier'] = buyer_tax_id[:8] if is_b2b else ''
        invoice_sdk.Send['CustomerName'] = customer_name[:60]
        invoice_sdk.Send['CustomerAddr'] = (partner.contact_address if partner else 'N/A')[:200]
        invoice_sdk.Send['CustomerEmail'] = (partner.email if partner else 'noreply@pos.local')[:200]
        invoice_sdk.Send['CustomerPhone'] = ((partner.phone or partner.mobile) if partner else '')[:20]
        invoice_sdk.Send['Print'] = print_flag
        invoice_sdk.Send['Donation'] = '1' if is_donation else '0'
        invoice_sdk.Send['LoveCode'] = (love_code or '')[:7] if is_donation else ''
        invoice_sdk.Send['CarrierType'] = ecpay_carrier_type
        invoice_sdk.Send['CarrierNum'] = carrier_num if carrier_type == 'mobile' else ''
        invoice_sdk.Send['TaxType'] = '1'
        invoice_sdk.Send['SalesAmount'] = sales_amount
        invoice_sdk.Send['InvType'] = '07'
        invoice_sdk.Send['vat'] = '1'
        invoice_sdk.Send['Items'] = items
        invoice_sdk.Send['InvoiceRemark'] = self.pos_reference or self.name or ''

        try:
            result = invoice_sdk.Check_Out()
        except Exception as e:
            _logger.warning("ECPay e-invoice API error: %s", e)
            ui_record.unlink()
            return {'success': False, 'error': str(e)}

        if result.get('RtnCode') != 1:
            _logger.info("ECPay e-invoice ← RtnCode=%s RtnMsg=%s", result.get('RtnCode'), result.get('RtnMsg'))
            ui_record.unlink()
            return {'success': False, 'error': result.get('RtnMsg', 'Unknown error')}

        # Store invoice number on uniform.invoice
        ui_record.name = result.get('InvoiceNo', '')
        _logger.info("ECPay e-invoice ← issued %s (uniform.invoice #%s)", ui_record.name, ui_record.id)

        # Query full details from ECPay and populate uniform.invoice fields
        try:
            self._pos_query_invoice_info(ui_record)
        except Exception as e:
            _logger.warning("ECPay e-invoice detail query failed (non-fatal): %s", e)

        # Link and store summary on pos.order
        self.write({
            'ecpay_invoice_id': ui_record.id,
            'tw_invoice_number': result.get('InvoiceNo', ''),
            'tw_invoice_random_code': result.get('RandomNumber', ''),
            'tw_carrier_type': carrier_type,
            'tw_carrier_num': carrier_num,
            'tw_love_code': love_code,
            'tw_buyer_tax_id': buyer_tax_id,
            'tw_buyer_name': buyer_name if carrier_type == 'b2b' else '',
            'tw_invoice_status': 'issued',
            'tw_qrcode_left': result.get('QRCode_Left', ''),
            'tw_qrcode_right': result.get('QRCode_Right', ''),
            'tw_pos_barcode': result.get('PosBarCode', ''),
        })

        return {
            'success': True,
            'invoice_no': result.get('InvoiceNo', ''),
            'random_code': result.get('RandomNumber', ''),
            'qrcode_left': result.get('QRCode_Left', ''),
            'qrcode_right': result.get('QRCode_Right', ''),
            'pos_barcode': result.get('PosBarCode', ''),
        }

    def _pos_query_invoice_info(self, ui_record):
        """Query ECPay for full invoice details — standalone version for POS.

        uniform.invoice.get_ecpay_invoice_info() requires a linked account.move
        which POS orders don't have.  This method calls the GetIssue API directly
        and populates the uniform.invoice record.
        """
        import datetime as _dt

        from odoo.addons.ecpay_invoice_tw.sdk.ecpay_main import EcpayInvoice

        inv = EcpayInvoice()
        self.env['account.move'].ecpay_invoice_init(
            inv, 'B2CInvoice/GetIssue', 'INVOICE_SEARCH',
            company_id=self.env.company
        )
        inv.Send['RelateNumber'] = ui_record.related_number
        result = inv.Check_Out()

        if result.get('RtnCode') != 1:
            return

        processed = ui_record.process_return_info(result)

        # Parse dates (same logic as uniform_invoice.get_ecpay_invoice_info)
        invoice_create = _dt.datetime.strptime(processed['IIS_Create_Date'], '%Y-%m-%d+%H:%M:%S')
        processed['IIS_Create_Date'] = invoice_create - _dt.timedelta(hours=8)
        processed['IIS_Upload_Date'] = (
            _dt.datetime.strptime(processed['IIS_Upload_Date'], '%Y-%m-%d+%H:%M:%S')
            - _dt.timedelta(hours=8)
        )
        processed['IIS_Customer_Addr'] = processed.get('IIS_Customer_Addr', '').replace('\n', ' ').replace('+', ' ')

        # Calculate ROC invoice month (same logic as uniform_invoice.py)
        date = invoice_create.date()
        month_int = int(invoice_create.strftime("%m"))
        roc_year = date.year - 1911
        if month_int in (11, 12):
            ui_record.invoice_month = f'{roc_year}年11-12月'
        elif month_int % 2 == 0:
            ui_record.invoice_month = f'{roc_year}年{month_int - 1:02d}-{month_int:02d}月'
        else:
            ui_record.invoice_month = f'{roc_year}年{month_int:02d}-{month_int + 1:02d}月'

        ui_record.write(processed)

    def action_void_einvoice(self, reason=''):
        """Void a previously issued e-invoice via ECPay SDK."""
        self.ensure_one()
        if self.tw_invoice_status != 'issued' or not self.ecpay_invoice_id:
            return {'success': False, 'error': 'No issued invoice to void'}

        from odoo.addons.ecpay_invoice_tw.sdk.ecpay_main import EcpayInvoice

        inv = EcpayInvoice()
        self.env['account.move'].ecpay_invoice_init(
            inv, 'B2CInvoice/Invalid', 'Invalid',
            company_id=self.env.company
        )

        inv.Send['InvoiceNo'] = self.tw_invoice_number
        inv.Send['InvoiceDate'] = (
            self.ecpay_invoice_id.IIS_Create_Date.strftime('%Y/%m/%d')
            if self.ecpay_invoice_id.IIS_Create_Date
            else self.date_order.strftime('%Y/%m/%d')
        )
        inv.Send['Reason'] = (reason or 'POS order voided')[:200]

        try:
            result = inv.Check_Out()
        except Exception as e:
            return {'success': False, 'error': str(e)}

        if result.get('RtnCode') == 1:
            self.write({'tw_invoice_status': 'voided'})
            # Refresh uniform.invoice status
            try:
                self._pos_query_invoice_info(self.ecpay_invoice_id)
            except Exception:
                pass
            return {'success': True}
        return {'success': False, 'error': result.get('RtnMsg', 'Unknown error')}

    def get_einvoice_print_html(self):
        """Render the ecpay_invoice_tw invoice report as HTML for ESC/POS printing.

        Reuses the official ecpay_invoice_tw.invoice QWeb template to ensure
        the printed receipt matches the government-compliant format exactly.
        """
        self.ensure_one()
        if not self.ecpay_invoice_id:
            return {'html': ''}

        try:
            html = self.env['ir.qweb']._render('ecpay_invoice_tw.invoice', {
                'docs': self.ecpay_invoice_id,
                'doc': self.ecpay_invoice_id,
                'user': self.env.user,
                'company': self.env.company,
            })
            if isinstance(html, bytes):
                html = html.decode('utf-8')
            from markupsafe import Markup
            css = Markup("""<style>
.invoiceContainer { font-family: monospace; }
.invoiceContainer .invoice_inner { width: 5.7cm; font-size: 14px; background: white; display: inline-block; }
.invoiceContainer .invoice_inner .invoice { width: 5.7cm; text-align: center; }
.invoice h1 { font-size: 19px; line-height: 1.2; max-height: 68px; overflow: hidden; font-weight: bold; margin: 0; }
.invoice h2 { font-size: 21px; font-weight: bold; line-height: 1; margin: 5px 0 4px; }
.invoice h3 { font-size: 24px; margin: 0 0 2px 0; line-height: 1; font-weight: bold; }
.invoice ul, .invoice_details ul { margin: 0; overflow: hidden; padding: 0; }
.invoice ul li, .invoice_details ul li { color: #333; margin: 0 0 3px 0; line-height: 18px; font-size: 14px; overflow: hidden; list-style: none; width: 100%; text-align: left; }
.invoice li span.left { float: left; }
.invoice li span.right { float: right; text-align: right; }
.invoiceContainer .invoice_inner .invoice_details { width: 5.7cm; padding: 5px; text-align: center; background: white; }
.invoice_details h2 { margin: 5px 0 10px 0; font-size: 22px; font-weight: bold; }
.invoice_details ul { border-bottom: 1px dashed #333; margin-bottom: 10px; }
.invoice_details h4 { text-align: left; margin: 0; font-size: 14px; font-weight: bold; }
</style>""")
            return {'html': str(css + html)}
        except Exception as e:
            _logger.warning("Failed to render einvoice HTML: %s", e)
            return {'html': ''}
