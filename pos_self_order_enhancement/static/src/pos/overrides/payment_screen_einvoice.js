/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { useState, useRef } from "@odoo/owl";
import { loadAllImages } from "@point_of_sale/utils";
import { _t } from "@web/core/l10n/translation";
import { EscPosPrinter } from "@pos_self_order_enhancement/printer/escpos_network_printer";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.einvState = useState({
            einvCarrierType: "print",
            einvCarrierNum: "",
            einvLoveCode: "",
            einvBuyerTaxId: "",
            einvB2bPrint: true,
        });
        this.einvCarrierInput = useRef("einvCarrierInput");
    },

    setEinvCarrierType(type) {
        this.einvState.einvCarrierType = type;
        this.einvState.einvB2bPrint = true;
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
            b2b_print: this.einvState?.einvB2bPrint ?? true,
        };
    },

    async _finalizeValidation() {
        const result = await super._finalizeValidation(...arguments);

        // Issue e-invoice after order is synced to server
        // State can be "paid" (no invoice toggle) or "invoiced" (invoice toggle ON)
        if (
            this.pos.config.ecpay_einvoice_enabled &&
            ["paid", "invoiced", "done"].includes(this.currentOrder.state)
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
                    _t("Invoice issued: %s", res.invoice_no),
                    { type: "success" }
                );

                // Print Taiwan invoice receipt if paper print is requested
                const shouldPrint = carrierData.carrier_type === "print" ||
                    (carrierData.carrier_type === "b2b" && carrierData.b2b_print);
                if (shouldPrint) {
                    await this._printTwInvoiceReceipt();
                }
            } else {
                this.notification.add(
                    _t("Invoice error: %s", res?.error || "Unknown"),
                    { type: "danger" }
                );
            }
        } catch (e) {
            this.notification.add(
                _t("Invoice error: %s", e.message || e),
                { type: "danger" }
            );
        }
    },

    async _printTwInvoiceReceipt() {
        // Print Taiwan invoice receipt to ESC/POS preparation printer.
        // Uses the ecpay_invoice_tw QWeb report template (server-side rendered)
        // to ensure the format matches the official government-compliant format.
        const escposPrinter = this.pos?.unwatched?.printers?.find(
            (p) => p instanceof EscPosPrinter
        );
        if (!escposPrinter) {
            console.warn("No ESC/POS printer found for invoice printing");
            return;
        }

        try {
            const orderId = this.currentOrder.id;
            const res = await this.pos.data.call(
                "pos.order",
                "get_einvoice_print_html",
                [[orderId]]
            );
            if (!res?.html) return;

            // Create DOM element from server-rendered HTML
            const container = document.createElement("div");
            container.innerHTML = res.html;
            container.style.position = "fixed";
            container.style.left = "-9999px";
            document.body.appendChild(container);

            const el = container.querySelector(".invoiceContainer") || container.firstElementChild;
            await loadAllImages(el);

            const result = await escposPrinter.printReceipt(el);
            container.remove();

            if (!result?.successful) {
                this.notification.add(
                    _t("Invoice print error: %s", result?.message?.body || "Unknown"),
                    { type: "warning" }
                );
            }
        } catch (e) {
            // Non-blocking: e-invoice is already issued via ECPay
            console.warn("Taiwan invoice print failed:", e);
        }
    },
});
