/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { useState, useRef } from "@odoo/owl";
import { EscPosPrinter } from "@pos_self_order_enhancement/printer/escpos_network_printer";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.einvState = useState({
            einvCarrierType: "print",
            einvCarrierNum: "",
            einvLoveCode: "",
            einvBuyerTaxId: "",
        });
        this.einvCarrierInput = useRef("einvCarrierInput");
    },

    setEinvCarrierType(type) {
        this.einvState.einvCarrierType = type;
        if (type === "mobile") {
            setTimeout(() => this.einvCarrierInput?.el?.focus(), 50);
        }
    },

    _getEinvCarrierData() {
        return {
            carrier_type: this.einvState?.einvCarrierType || "print",
            carrier_num: this.einvState?.einvCarrierNum || "",
            love_code: this.einvState?.einvLoveCode || "",
            buyer_tax_id: this.einvState?.einvBuyerTaxId || "",
        };
    },

    async _finalizeValidation() {
        const result = await super._finalizeValidation(...arguments);

        // Issue e-invoice after order is synced to server
        if (
            this.pos.config.ecpay_einvoice_enabled &&
            this.currentOrder.state === "paid"
        ) {
            await this._issueEinvoice();
        }

        return result;
    },

    async _issueEinvoice() {
        const carrierData = this._getEinvCarrierData();
        const orderId = this.currentOrder.id;

        try {
            const res = await this.pos.data.call(
                "pos.order",
                "action_issue_einvoice",
                [[orderId], carrierData]
            );

            if (res?.success) {
                this.currentOrder.tw_invoice_number = res.invoice_no;
                this.currentOrder.tw_invoice_random_code = res.random_code;
                this.currentOrder.tw_qrcode_left = res.qrcode_left;
                this.currentOrder.tw_qrcode_right = res.qrcode_right;
                this.currentOrder.tw_pos_barcode = res.pos_barcode;

                this.notification.add(
                    `發票開立成功 Invoice issued: ${res.invoice_no}`,
                    { type: "success" }
                );

                // Phase B: print Taiwan invoice receipt if carrier_type is 'print'
                if (carrierData.carrier_type === "print") {
                    await this._printTwInvoiceReceipt(res);
                }
            } else {
                this.notification.add(
                    `發票開立失敗 Invoice error: ${res?.error || "Unknown"}`,
                    { type: "danger" }
                );
            }
        } catch (e) {
            this.notification.add(
                `發票開立錯誤 Invoice error: ${e.message || e}`,
                { type: "danger" }
            );
        }
    },

    async _printTwInvoiceReceipt(invoiceResult) {
        // Find first ESC/POS network printer
        const escposPrinter = this.pos?.unwatched?.printers?.find(
            (p) => p instanceof EscPosPrinter
        );
        if (!escposPrinter) {
            this.notification.add(
                "No ESC/POS printer found for invoice printing",
                { type: "warning" }
            );
            return;
        }

        // Use the TwInvoiceReceipt component (Phase B)
        try {
            const { TwInvoiceReceipt } = await import(
                "@pos_self_order_enhancement/pos/overrides/tw_invoice_receipt"
            );
            await this.printer.print(TwInvoiceReceipt, {
                order: this.currentOrder,
                invoiceData: invoiceResult,
                sellerTaxId: this.pos.config.ecpay_seller_tax_id || "",
            });
        } catch (e) {
            this.notification.add(
                `發票列印失敗 Print error: ${e.message || e}`,
                { type: "warning" }
            );
        }
    },
});
