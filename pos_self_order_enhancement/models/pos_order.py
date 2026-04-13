import json

from odoo import models, fields, api
from odoo.osv.expression import AND, OR


class PosOrder(models.Model):
    _inherit = 'pos.order'

    kds_state = fields.Selection([
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('served', 'Served'),
    ], string='Kitchen Status', default='new', index=True)

    kds_done_items = fields.Text(
        string='KDS Done Items',
        default='{}',
        help='JSON dict of line UUIDs marked as done on the KDS',
    )

    kds_sent_to_kitchen = fields.Boolean(
        string='Sent to Kitchen by Staff',
        default=False,
        help='Set to True when FOH staff clicks the Order button to send to kitchen',
    )

    kds_remake_data = fields.Text(
        string='KDS Remake Data',
        default='{}',
        help='JSON: {"<line_id>": {"count": N, "reason": "..."}}',
    )

    kds_fired_courses = fields.Text(
        string='KDS Fired Courses',
        default='{}',
        help='JSON dict: {"<category_id>": true/false}. Tracks which category groups are fired.',
    )

    kds_served_items = fields.Text(
        string='KDS Served Items',
        default='{}',
        help='JSON dict: {"<line_id>": true}. Tracks which items have been served to the table.',
    )

    # ── Payment Gate (pay-per-order) ──────────────────────────
    self_order_payment_status = fields.Selection([
        ('none', 'No Payment Gate'),
        ('pending_online', 'Pending Online Payment'),
        ('pending_counter', 'Pending Counter Payment'),
        ('paid', 'Payment Confirmed'),
    ], string='Self-Order Payment Status', default='none',
       help='Controls when POS/KDS is notified about self-order orders in pay-per-order mode.')

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
    tw_invoice_status = fields.Selection([
        ('none', 'None'),
        ('issued', 'Issued (已開立)'),
        ('voided', 'Voided (已作廢)'),
    ], string='Invoice Status', default='none')
    tw_qrcode_left = fields.Text('QR Code Left')
    tw_qrcode_right = fields.Text('QR Code Right')
    tw_pos_barcode = fields.Text('POS Barcode')

    # ── helpers ──────────────────────────────────────────────

    def _get_line_hold_fire_category(self, line):
        """Return (category_id, category_name) for the line's effective Hold & Fire category.

        Checks the line's own product category first; falls back to the combo
        parent only if the child has no H&F category of its own.  This lets
        combo choices declare their own Hold & Fire course (e.g. a dessert
        choice inside a non-H&F lunch set combo).

        Returns (0, '') if no H&F category found (always fired).
        """
        candidates = [line]
        if line.combo_parent_id:
            candidates.append(line.combo_parent_id)
        for candidate in candidates:
            categs = candidate.product_id.pos_categ_ids
            if categs and categs[0].kds_hold_fire:
                return categs[0].id, categs[0].name
        return 0, ''

    def _compute_fired_courses(self):
        """Build the kds_fired_courses JSON for this order.

        All hold-fire categories start held — staff must manually fire each
        category from the POS.
        """
        self.ensure_one()
        categories = set()
        for line in self.lines:
            if line.qty <= 0:
                continue
            categ_id, _ = self._get_line_hold_fire_category(line)
            if categ_id > 0:
                categories.add(categ_id)

        if not categories:
            return '{}'

        fired = {str(cid): False for cid in categories}
        return json.dumps(fired)

    # ── course actions ───────────────────────────────────────

    def fire_course(self, category_id):
        """Fire a specific category group for kitchen preparation."""
        for order in self:
            try:
                fired = json.loads(order.kds_fired_courses or '{}')
            except (json.JSONDecodeError, TypeError):
                fired = {}

            key = str(category_id)
            if key not in fired:
                continue

            fired[key] = True
            vals = {'kds_fired_courses': json.dumps(fired)}

            # If order was done (all previous courses complete), reset to in_progress
            if order.kds_state == 'done':
                vals['kds_state'] = 'in_progress'

            # Un-done combo parents that have a child in the just-fired
            # category, so the KDS card reverts to active state and the
            # newly-fired child appears at normal brightness.
            try:
                done_items = json.loads(order.kds_done_items or '{}')
            except (json.JSONDecodeError, TypeError):
                done_items = {}

            changed_done = False
            for line in order.lines:
                if line.combo_parent_id:
                    continue
                has_fired_child = False
                for child in line.combo_line_ids:
                    child_categ_id, _ = order._get_line_hold_fire_category(child)
                    if child_categ_id == category_id:
                        has_fired_child = True
                        if done_items.get(str(child.id), False):
                            done_items[str(child.id)] = False
                            changed_done = True
                if has_fired_child and done_items.get(str(line.id), False):
                    done_items[str(line.id)] = False
                    changed_done = True

            if changed_done:
                vals['kds_done_items'] = json.dumps(done_items)
                if order.kds_state != 'done' and 'kds_state' not in vals:
                    vals['kds_state'] = 'in_progress'

            order.write(vals)
            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': vals.get('kds_state', order.kds_state),
                        'course_fired': category_id,
                    })
        return True

    # ── existing methods (modified) ──────────────────────────

    def mark_sent_to_kitchen(self):
        """Called by POS frontend when staff clicks Order button."""
        vals = {'kds_sent_to_kitchen': True}
        for order in self:
            if not order.kds_state:
                vals['kds_state'] = 'new'
                break
        self.write(vals)

        # Initialize / merge course fire state for each order.
        # Preserve any categories already fired by staff — only add newly
        # introduced categories as held.
        for order in self:
            try:
                existing = json.loads(order.kds_fired_courses or '{}')
            except (json.JSONDecodeError, TypeError):
                existing = {}

            current_categories = set()
            for line in order.lines:
                if line.qty <= 0:
                    continue
                categ_id, _ = order._get_line_hold_fire_category(line)
                if categ_id > 0:
                    current_categories.add(str(categ_id))

            merged = dict(existing)
            for key in current_categories:
                if key not in merged:
                    merged[key] = False

            if merged:
                order.write({'kds_fired_courses': json.dumps(merged)})

        for order in self:
            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': order.kds_state,
                    })
        return True

    def mark_served(self):
        """Mark done items as served. Only sets kds_state='served' when ALL items are served."""
        for order in self:
            try:
                done_items = json.loads(order.kds_done_items or '{}')
            except (json.JSONDecodeError, TypeError):
                done_items = {}
            try:
                served_items = json.loads(order.kds_served_items or '{}')
            except (json.JSONDecodeError, TypeError):
                served_items = {}

            # Mark all done-but-not-served items as served
            for key, is_done in done_items.items():
                if is_done and not served_items.get(key, False):
                    served_items[key] = True

            vals = {'kds_served_items': json.dumps(served_items)}

            # Check if ALL items are now served
            all_served = True
            for line in order.lines:
                if line.qty > 0 and not served_items.get(str(line.id), False):
                    all_served = False
                    break

            if all_served:
                vals['kds_state'] = 'served'

            order.write(vals)
            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': vals.get('kds_state', order.kds_state),
                        'kds_served_items': json.dumps(served_items),
                    })
        return True

    def mark_remake(self, line_ids, reason='remake'):
        """Called by POS frontend to send items back to kitchen for remake."""
        for order in self:
            try:
                remake_data = json.loads(order.kds_remake_data or '{}')
            except (json.JSONDecodeError, TypeError):
                remake_data = {}

            done_items = {}
            if order.kds_state in ('done', 'served'):
                for line in order.lines:
                    if line.qty > 0:
                        done_items[str(line.id)] = True
            else:
                try:
                    done_items = json.loads(order.kds_done_items or '{}')
                except (json.JSONDecodeError, TypeError):
                    done_items = {}

            try:
                served_items = json.loads(order.kds_served_items or '{}')
            except (json.JSONDecodeError, TypeError):
                served_items = {}

            for lid in line_ids:
                key = str(lid)
                if key not in remake_data:
                    remake_data[key] = {'count': 0, 'reason': ''}
                remake_data[key]['count'] += 1
                remake_data[key]['reason'] = reason
                done_items[key] = False
                served_items.pop(key, None)  # clear served status

            order.write({
                'kds_state': 'in_progress',
                'kds_done_items': json.dumps(done_items),
                'kds_remake_data': json.dumps(remake_data),
                'kds_served_items': json.dumps(served_items),
            })

            for config in order.config_id:
                if config.kds_enabled:
                    config._notify('KDS_ORDER_UPDATE', {
                        'order_id': order.id,
                        'kds_state': 'new',
                        'is_remake': True,
                        'kds_done_items': json.dumps(done_items),
                        'kds_remake_data': json.dumps(remake_data),
                        'kds_served_items': json.dumps(served_items),
                    })
        return True

    def _send_notification(self, order_ids):
        """Extend to also notify KDS screens (only for kitchen-confirmed orders).

        In pay-per-order mode, notifications are suppressed entirely via context
        flag during order creation. The controller handles notification later
        (after payment is confirmed or customer selects counter payment).
        """
        if self.env.context.get('suppress_self_order_notification'):
            return

        notifiable = order_ids.filtered(
            lambda o: o.self_order_payment_status != 'pending_online'
        )
        if notifiable:
            super()._send_notification(notifiable)

        config_ids = order_ids.config_id
        for config in config_ids:
            if config.kds_enabled:
                kitchen_orders = order_ids.filtered(lambda o: o.kds_sent_to_kitchen)
                if kitchen_orders:
                    config._notify('KDS_ORDER_UPDATE', {})

    _KDS_PROTECTED_FIELDS = (
        'kds_state', 'kds_sent_to_kitchen', 'kds_done_items',
        'kds_remake_data', 'kds_fired_courses', 'kds_served_items',
        'self_order_payment_status',
    )

    _EINVOICE_PROTECTED_FIELDS = (
        'ecpay_invoice_id',
        'tw_invoice_number', 'tw_invoice_random_code', 'tw_invoice_status',
        'tw_qrcode_left', 'tw_qrcode_right', 'tw_pos_barcode',
    )

    @api.model
    def _load_pos_data_domain(self, data):
        """Hide pending_online orders but include paid payment-gated orders."""
        domain = super()._load_pos_data_domain(data)
        draft_domain = AND([domain, [('self_order_payment_status', '!=', 'pending_online')]])
        session_id = data['pos.session']['data'][0]['id']
        paid_gated = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('self_order_payment_status', '=', 'paid'),
            ('session_id', '=', session_id),
        ]
        return OR([draft_domain, paid_gated])

    @api.model
    def sync_from_ui(self, orders):
        """Protect KDS and e-invoice fields from frontend overwrite."""
        for order in orders:
            for field in self._KDS_PROTECTED_FIELDS:
                order.pop(field, None)
            for field in self._EINVOICE_PROTECTED_FIELDS:
                order.pop(field, None)

        existing_order_ids = []
        for order in orders:
            if order.get('id') and isinstance(order['id'], int):
                existing_order_ids.append(order['id'])

        old_line_ids = {}
        if existing_order_ids:
            for order in self.browse(existing_order_ids).exists():
                old_line_ids[order.id] = set(order.lines.ids)

        result = super().sync_from_ui(orders)

        # When new lines are added to an already-sent order, only merge any
        # newly introduced Hold & Fire categories into kds_fired_courses.
        # Do NOT touch kds_done_items / kds_served_items / kds_state — those
        # are owned by the kitchen workflow and adding new lines must never
        # un-mark previously done or served items (that would resurrect them
        # in KDS and confuse staff).
        if existing_order_ids:
            updated_orders = self.browse(existing_order_ids).exists()
            for order in updated_orders:
                if not order.kds_sent_to_kitchen:
                    continue
                prev_ids = old_line_ids.get(order.id, set())
                curr_ids = set(order.lines.ids)
                new_lines = curr_ids - prev_ids
                if not new_lines:
                    continue

                try:
                    fired = json.loads(order.kds_fired_courses or '{}')
                except (json.JSONDecodeError, TypeError):
                    fired = {}

                new_line_records = self.env['pos.order.line'].browse(list(new_lines))
                changed = False
                for line in new_line_records:
                    categ_id, _ = order._get_line_hold_fire_category(line)
                    if categ_id > 0 and str(categ_id) not in fired:
                        fired[str(categ_id)] = False
                        changed = True

                if changed:
                    order.write({'kds_fired_courses': json.dumps(fired)})

        return result

    # ── Payment Gate: detect payment completion ───────────

    def _process_saved_order(self, draft):
        """Sync payment-gated orders to POS BEFORE state changes to 'paid'.

        POS can only load 'draft' orders (JS-hardcoded domain in sync).
        We sync while still draft, then super() changes state to 'paid'.
        read_config_open_orders override ensures paid gated orders are
        also found during the async POS sync that follows.
        """
        gated = self.filtered(
            lambda o: o.self_order_payment_status in ('pending_online', 'pending_counter')
        )
        if gated:
            super(PosOrder, gated).write({'self_order_payment_status': 'paid'})
            for config in gated.config_id:
                config.notify_synchronisation(
                    config.current_session_id.id,
                    self.env.context.get('login_number', 0)
                )
                config._notify('ORDER_STATE_CHANGED', {})
            tables = gated.mapped('table_id')
            if tables:
                gated.send_table_count_notification(tables)
        return super()._process_saved_order(draft)

    def write(self, vals):
        """Update payment status when payment-gated orders become paid.

        Notifications are handled by _process_saved_order() (before state
        transition).  This override just ensures the status field is updated
        for any remaining code paths (e.g. counter payment via POS cashier).
        """
        completing = self.env['pos.order']
        if vals.get('state') in ('paid', 'done', 'invoiced'):
            completing = self.filtered(
                lambda o: o.self_order_payment_status in ('pending_online', 'pending_counter')
            )

        res = super().write(vals)

        if completing:
            # Update payment status for orders not already handled by _process_saved_order
            still_pending = completing.filtered(
                lambda o: o.self_order_payment_status != 'paid'
            )
            if still_pending:
                super(PosOrder, still_pending).write({'self_order_payment_status': 'paid'})
                for config in still_pending.config_id:
                    config.notify_synchronisation(
                        config.current_session_id.id,
                        self.env.context.get('login_number', 0)
                    )
                    config._notify('ORDER_STATE_CHANGED', {})
                tables = still_pending.mapped('table_id')
                if tables:
                    still_pending.send_table_count_notification(tables)

        return res

    # ── E-Invoice RPC methods ─────────────────────────────

    def action_issue_einvoice(self, carrier_data):
        """Issue e-invoice via ECPay SDK (ecpay_invoice_tw).

        Creates a uniform.invoice record so the invoice appears in the
        統一發票 admin page.  Called from POS frontend after payment.
        """
        import datetime as _dt
        import logging
        _logger = logging.getLogger(__name__)

        self.ensure_one()
        config = self.config_id
        if not config.ecpay_einvoice_enabled:
            return {'success': False, 'error': 'E-Invoice not enabled'}

        company = self.env.company
        if not company.ecpay_MerchantID or not company.ecpay_HashKey or not company.ecpay_HashIV:
            return {'success': False, 'error': '綠界電子發票連線設定不完整 ECPay credentials not configured'}

        carrier_type = carrier_data.get('carrier_type', 'print')
        carrier_num = carrier_data.get('carrier_num', '')
        love_code = carrier_data.get('love_code', '')
        buyer_tax_id = carrier_data.get('buyer_tax_id', '')

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
        # ECPay validates SalesAmount == sum(ItemAmount) and SalesAmount is int.
        # We round each ItemAmount to int and compute ItemPrice = ItemAmount / qty
        # to ensure perfect consistency.
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
        invoice_sdk.Send['RelateNumber'] = ui_record.related_number
        invoice_sdk.Send['CustomerIdentifier'] = buyer_tax_id[:8] if is_b2b else ''
        invoice_sdk.Send['CustomerName'] = (partner.name if partner else '顧客')[:60]
        invoice_sdk.Send['CustomerAddr'] = (partner.contact_address_complete if partner else 'N/A')[:200]
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
