/** @odoo-module */

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

/**
 * Custom Payment Page that handles both kiosk and mobile modes.
 *
 * - Kiosk mode: delegates to original kiosk payment flow (terminal RPC)
 * - Mobile mode: displays order summary grouped by session with counter/online payment
 */
export class PaymentPage extends Component {
    static template = "pos_self_order_enhancement.PaymentPage";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = this.selfOrder.router;
        this.state = useState({
            loading: false,
            error: null,
            counterPaymentConfirmed: false,
            // Kiosk mode state
            kioskSelection: true,
            kioskPaymentMethodId: null,
        });

        // E-Invoice carrier preferences
        this.invoiceState = useState({
            carrierType: "print",
            carrierNum: "",
            loveCode: "",
            buyerTaxId: "",
            buyerName: "",
            lookingUp: false,
            validationError: null,
        });

        onMounted(() => {
            this.state.loading = false;
            this.state.error = null;

            // Kiosk mode: auto-select if only one payment method
            if (this.isKioskMode) {
                this.selfOrder.isOrder();
                const methods = this.selfOrder.models["pos.payment.method"].getAll();
                if (methods.length === 1) {
                    this.selectKioskMethod(methods[0].id);
                }
            }
        });

        onWillUnmount(() => {
            if (this.isKioskMode) {
                this.selfOrder.paymentError = false;
            }
        });
    }

    // ── Mode Detection ──

    get isKioskMode() {
        return this.selfOrder.config.self_ordering_mode === "kiosk";
    }

    // ── Kiosk Mode ──

    get kioskPaymentMethods() {
        return this.selfOrder.models["pos.payment.method"].getAll();
    }

    get showKioskFooterBtn() {
        return this.selfOrder.paymentError || this.state.kioskSelection;
    }

    get selectedKioskPaymentMethod() {
        return this.selfOrder.models["pos.payment.method"].find(
            (p) => p.id === this.state.kioskPaymentMethodId
        );
    }

    selectKioskMethod(methodId) {
        this.state.kioskSelection = false;
        this.state.kioskPaymentMethodId = methodId;
        this.startKioskPayment();
    }

    async startKioskPayment() {
        this.selfOrder.paymentError = false;
        try {
            await rpc(`/kiosk/payment/${this.selfOrder.config.id}/kiosk`, {
                order: this.selfOrder.currentOrder.serialize({ orm: true }),
                access_token: this.selfOrder.access_token,
                payment_method_id: this.state.kioskPaymentMethodId,
            });
        } catch (error) {
            this.selfOrder.handleErrorNotification(error);
            this.selfOrder.paymentError = true;
        }
    }

    // ── Mobile Mode - Common ──

    get currentOrder() {
        return this.selfOrder.currentOrder;
    }

    get orderLines() {
        return this.currentOrder?.lines || [];
    }

    /**
     * Group order lines by ordering session (60-second time gaps).
     */
    get groupedOrderLines() {
        const lines = this.currentOrder?.lines || [];
        if (lines.length === 0) {
            return [];
        }

        const groups = [];
        let currentGroup = null;
        let groupIndex = 1;

        const parseTime = (val) => {
            if (!val) return 0;
            if (typeof val === 'number') return val;
            // Handle Odoo datetime strings or luxon DateTime objects
            if (val.ts) return val.ts; // luxon DateTime
            const d = new Date(val);
            return isNaN(d.getTime()) ? 0 : d.getTime();
        };

        const sortedLines = [...lines].sort((a, b) => {
            const timeA = parseTime(a.create_date || a.write_date);
            const timeB = parseTime(b.create_date || b.write_date);
            return timeA - timeB;
        });

        let lastTime = null;
        for (const line of sortedLines) {
            const lineTime = parseTime(line.create_date || line.write_date);
            const isNewBatch = !currentGroup ||
                (lastTime && lineTime && (lineTime - lastTime) > 60000);

            if (isNewBatch) {
                currentGroup = {
                    index: groupIndex++,
                    lines: [],
                    subtotal: 0,
                };
                groups.push(currentGroup);
            }

            currentGroup.lines.push(line);
            currentGroup.subtotal += line.price_subtotal_incl || 0;
            lastTime = lineTime;
        }

        if (groups.length === 1) {
            return [{ index: 0, lines: sortedLines, subtotal: this.totalAmount, single: true }];
        }

        return groups;
    }

    get currentSessionAmount() {
        const groups = this.groupedOrderLines;
        if (groups.length <= 1) {
            return 0;
        }
        return groups[groups.length - 1]?.subtotal || 0;
    }

    get hasMultipleSessions() {
        return this.groupedOrderLines.length > 1;
    }

    get totalAmount() {
        return this.currentOrder?.amount_total || 0;
    }

    get orderReference() {
        return this.currentOrder?.pos_reference ||
               this.currentOrder?.tracking_number ||
               this.currentOrder?.name ||
               '';
    }

    /**
     * Check if online payment methods are available.
     */
    get hasOnlinePayment() {
        const config = this.selfOrder.config;
        const onlinePaymentMethodId = config?.self_ordering_online_payment_method_id;

        if (onlinePaymentMethodId) {
            const methodId = Array.isArray(onlinePaymentMethodId)
                ? onlinePaymentMethodId[0]
                : onlinePaymentMethodId;
            if (methodId) {
                return true;
            }
        }

        const methods = this.onlinePaymentMethods;
        return methods && methods.length > 0;
    }

    get onlinePaymentMethods() {
        const allMethods = this.selfOrder.models["pos.payment.method"]?.getAll() || [];
        const config = this.selfOrder.config;
        const configuredMethodId = config?.self_ordering_online_payment_method_id;

        const targetMethodId = Array.isArray(configuredMethodId)
            ? configuredMethodId[0]
            : configuredMethodId;

        return allMethods.filter(method => {
            if (targetMethodId && method.id === targetMethodId) {
                return true;
            }
            if (method.is_online_payment) {
                return true;
            }
            if (["adyen", "stripe"].includes(method.use_payment_terminal)) {
                return true;
            }
            return false;
        });
    }

    /**
     * Format currency using the POS currency configuration.
     */
    formatCurrency(amount) {
        const currency = this.selfOrder.currency;
        if (!currency) {
            return String(amount);
        }
        return currency.symbol + ' ' + amount.toFixed(currency.decimal_places || 0);
    }

    // ── E-Invoice ──

    get showEinvoiceForm() {
        return (
            !this.isKioskMode &&
            this.selfOrder.config.ecpay_einvoice_enabled
        );
    }

    setCarrierType(type) {
        this.invoiceState.carrierType = type;
        this.invoiceState.carrierNum = "";
        this.invoiceState.loveCode = "";
        this.invoiceState.buyerTaxId = "";
        this.invoiceState.buyerName = "";
        this.invoiceState.validationError = null;
    }

    validateInvoiceData() {
        const { carrierType, carrierNum, loveCode, buyerTaxId } = this.invoiceState;
        this.invoiceState.validationError = null;

        if (carrierType === "mobile") {
            if (!carrierNum) {
                this.invoiceState.validationError = _t("Please enter mobile barcode");
                return false;
            }
            if (!/^\/[0-9A-Z+\-.]{7}$/.test(carrierNum)) {
                this.invoiceState.validationError = _t("Invalid mobile barcode format (e.g. /ABC+123)");
                return false;
            }
        }
        if (carrierType === "donation") {
            if (!loveCode) {
                this.invoiceState.validationError = _t("Please enter love code");
                return false;
            }
            if (!/^([xX][0-9]{2,6}|[0-9]{3,7})$/.test(loveCode)) {
                this.invoiceState.validationError = _t("Invalid love code format (3-7 digits)");
                return false;
            }
        }
        if (carrierType === "b2b") {
            if (!buyerTaxId) {
                this.invoiceState.validationError = _t("Please enter tax ID");
                return false;
            }
            if (!/^[0-9]{8}$/.test(buyerTaxId)) {
                this.invoiceState.validationError = _t("Invalid tax ID format (8 digits)");
                return false;
            }
        }
        return true;
    }

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
    }

    async saveInvoiceData() {
        const order = this.currentOrder;
        if (!order?.id || !order.access_token) {
            return;
        }
        try {
            const result = await rpc("/pos-self-order/save-einvoice-data", {
                access_token: this.selfOrder.access_token,
                order_id: order.id,
                order_access_token: order.access_token,
                carrier_type: this.invoiceState.carrierType,
                carrier_num: this.invoiceState.carrierNum,
                love_code: this.invoiceState.loveCode,
                buyer_tax_id: this.invoiceState.buyerTaxId,
                buyer_name: this.invoiceState.buyerName,
            });
            if (result && !result.success) {
                this.invoiceState.validationError = result.error;
                return false;
            }
        } catch (error) {
            console.error("Save invoice data error:", error);
            this.invoiceState.validationError = _t("Failed to save invoice data. Please try again.");
            return false;
        }
        return true;
    }

    goBack() {
        this.router.navigate("cart");
    }

    /**
     * Counter payment - notify POS so cashier can see and process the order.
     * In pay-per-order mode, this makes the order visible to the cashier.
     */
    async selectCounterPayment() {
        const order = this.currentOrder;
        if (!order?.id) {
            return;
        }

        // Validate e-invoice data before proceeding
        if (this.showEinvoiceForm && !this.validateInvoiceData()) {
            return;
        }

        this.state.loading = true;
        this.state.error = null;

        try {
            // Ensure order is on the server
            if (!order.access_token) {
                await this.selfOrder.sendDraftOrderToServer();
            }

            // Save e-invoice preferences
            if (this.showEinvoiceForm) {
                const saved = await this.saveInvoiceData();
                if (saved === false) {
                    this.state.loading = false;
                    return;
                }
            }

            // Notify POS that customer will pay at counter
            await rpc('/pos-self-order/select-counter-payment', {
                access_token: this.selfOrder.access_token,
                order_id: order.id,
                order_access_token: order.access_token,
            });

            // Show success screen on payment page (don't navigate away —
            // in "each" mode the selectedOrderUuid is already null so
            // confirmation page can't find the order and redirects to landing)
            this.state.loading = false;
            this.state.counterPaymentConfirmed = true;
        } catch (error) {
            console.error("Counter payment error:", error);
            this.state.error = _t("Failed to process. Please try again.");
            this.state.loading = false;
        }
    }

    /**
     * Handle online payment via Odoo's POS payment portal.
     * Uses /pos/pay/{order_id} endpoint which supports public (anonymous) access.
     */
    async selectOnlinePayment(paymentMethodId) {
        // Validate e-invoice data before proceeding
        if (this.showEinvoiceForm && !this.validateInvoiceData()) {
            return;
        }

        this.state.loading = true;
        this.state.error = null;

        try {
            let order = this.currentOrder;

            if (!order?.id) {
                this.state.error = _t("No order to pay");
                this.state.loading = false;
                return;
            }

            if ((order.amount_total || 0) <= 0) {
                this.state.error = _t("No amount to pay");
                this.state.loading = false;
                return;
            }

            // Ensure order is sent to server and has access_token
            if (!order.access_token) {
                order = await this.selfOrder.sendDraftOrderToServer();
            }

            // Save e-invoice preferences before redirecting to payment
            if (this.showEinvoiceForm) {
                const saved = await this.saveInvoiceData();
                if (saved === false) {
                    this.state.loading = false;
                    return;
                }
            }

            if (order.state === "draft") {
                // Build payment URL using window.location.origin instead of session.base_url
                // to avoid reverse proxy issues (session.base_url returns internal Docker IP)
                const baseUrl = window.location.origin;
                const configId = this.selfOrder.config.id;
                const payAfter = this.selfOrder.config.self_ordering_pay_after;

                let exitRouteUrl = `${baseUrl}/pos-self/${configId}`;
                if (payAfter === "each") {
                    exitRouteUrl += `/confirmation/${order.access_token}/order`;
                }

                let table = "";
                if (this.selfOrder.currentTable) {
                    table = `&table_identifier=${this.selfOrder.currentTable.identifier}`;
                }
                exitRouteUrl += `?access_token=${this.selfOrder.access_token}${table}`;

                const exitRoute = encodeURIComponent(exitRouteUrl);
                const paymentUrl = `${baseUrl}/pos/pay/${order.id}?access_token=${order.access_token}&exit_route=${exitRoute}`;
                window.open(paymentUrl, "_self");
            } else {
                this.state.error = _t("The current order cannot be paid (maybe it is already paid).");
                this.state.loading = false;
            }
        } catch (error) {
            console.error("Online payment error:", error);
            this.state.error = _t("Payment processing failed. Please try again or pay at counter.");
            this.state.loading = false;
        }
    }

    goToHome() {
        this.selfOrder.selectedOrderUuid = null;

        if (this.router && typeof this.router.navigate === 'function') {
            this.router.navigate("default");
        } else {
            const configId = this.selfOrder.config?.id;
            if (configId) {
                window.location.href = `/pos-self/${configId}`;
            }
        }
    }
}
