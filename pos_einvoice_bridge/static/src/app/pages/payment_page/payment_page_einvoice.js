/** @odoo-module **/

/**
 * OWL patch that injects e-invoice carrier form logic into the self-order
 * PaymentPage component.  When pos_einvoice_bridge is installed, this adds:
 * - invoiceState (reactive carrier type/number state)
 * - showEinvoiceForm getter
 * - carrier type selection, validation, tax ID lookup
 * - saveInvoiceData() called before payment
 */

import { PaymentPage } from "@pos_self_order/app/pages/payment_page/payment_page";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

patch(PaymentPage.prototype, {
    setup() {
        super.setup(...arguments);
        this.invoiceState = useState({
            carrierType: "print",
            carrierNum: "",
            loveCode: "",
            buyerTaxId: "",
            buyerName: "",
            lookingUp: false,
            validationError: "",
        });
    },

    get showEinvoiceForm() {
        if (this.selfOrder?.config?.module_pos_restaurant) {
            // Kiosk mode — no einvoice form
            if (this.selfOrder?.config?.self_ordering_mode === "kiosk") return false;
        }
        return !!this.selfOrder?.config?.ecpay_einvoice_enabled;
    },

    setCarrierType(type) {
        this.invoiceState.carrierType = type;
        this.invoiceState.validationError = "";
    },

    validateInvoiceData() {
        const { carrierType, carrierNum, loveCode, buyerTaxId } = this.invoiceState;
        this.invoiceState.validationError = "";

        if (carrierType === "mobile") {
            if (!carrierNum) {
                this.invoiceState.validationError = "請輸入手機條碼";
                return false;
            }
            if (!/^\/[0-9A-Z+\-.]{7}$/.test(carrierNum)) {
                this.invoiceState.validationError = "手機條碼格式錯誤 (格式: / + 7碼英數字)";
                return false;
            }
        } else if (carrierType === "donation") {
            if (!loveCode) {
                this.invoiceState.validationError = "請輸入愛心碼";
                return false;
            }
            if (!/^([xX][0-9]{2,6}|[0-9]{3,7})$/.test(loveCode)) {
                this.invoiceState.validationError = "愛心碼格式錯誤 (3~7碼數字)";
                return false;
            }
        } else if (carrierType === "b2b") {
            if (!buyerTaxId) {
                this.invoiceState.validationError = "請輸入統一編號";
                return false;
            }
            if (!/^[0-9]{8}$/.test(buyerTaxId)) {
                this.invoiceState.validationError = "統一編號格式錯誤 (8碼數字)";
                return false;
            }
        }
        return true;
    },

    async onTaxIdInput(ev) {
        const val = ev.target.value.replace(/\D/g, "");
        this.invoiceState.buyerTaxId = val;
        if (val.length === 8) {
            this.invoiceState.lookingUp = true;
            try {
                const res = await rpc("/pos-self-order/lookup-tax-id", {
                    access_token: this.selfOrder.access_token,
                    tax_id: val,
                });
                if (res?.success && res.name) {
                    this.invoiceState.buyerName = res.name;
                }
            } catch (e) {
                console.warn("Tax ID lookup failed:", e);
            }
            this.invoiceState.lookingUp = false;
        }
    },

    async saveInvoiceData() {
        const order = this.selfOrder?.currentOrder;
        if (!order) return false;
        try {
            const res = await rpc("/pos-self-order/save-einvoice-data", {
                access_token: this.selfOrder.access_token,
                order_id: order.id,
                order_access_token: order.access_token,
                carrier_type: this.invoiceState.carrierType,
                carrier_num: this.invoiceState.carrierNum,
                love_code: this.invoiceState.loveCode,
                buyer_tax_id: this.invoiceState.buyerTaxId,
                buyer_name: this.invoiceState.buyerName,
            });
            if (!res?.success) {
                this.invoiceState.validationError = res?.error || "Save failed";
                return false;
            }
            return true;
        } catch (e) {
            this.invoiceState.validationError = "Network error";
            return false;
        }
    },

    async selectCounterPayment() {
        // Inject e-invoice validation and save before proceeding
        if (this.showEinvoiceForm) {
            if (!this.validateInvoiceData()) return;
            const saved = await this.saveInvoiceData();
            if (saved === false) return;
        }
        return super.selectCounterPayment(...arguments);
    },

    async selectOnlinePayment() {
        // Inject e-invoice validation and save before proceeding
        if (this.showEinvoiceForm) {
            if (!this.validateInvoiceData()) return;
            const saved = await this.saveInvoiceData();
            if (saved === false) return;
        }
        return super.selectOnlinePayment(...arguments);
    },
});
