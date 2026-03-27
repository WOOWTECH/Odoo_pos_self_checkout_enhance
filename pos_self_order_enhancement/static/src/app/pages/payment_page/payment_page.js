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
            // Kiosk mode state
            kioskSelection: true,
            kioskPaymentMethodId: null,
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

    goBack() {
        this.router.navigate("cart");
    }

    /**
     * Counter payment - display only, no action needed.
     */
    selectCounterPayment() {
        // No action - customer pays at counter
    }

    /**
     * Handle online payment via Odoo's payment portal.
     */
    async selectOnlinePayment(paymentMethodId) {
        this.state.loading = true;
        this.state.error = null;

        try {
            const order = this.currentOrder;
            const orderAmount = order?.amount_total || this.totalAmount || 0;
            const orderRef = order?.pos_reference || order?.name || order?.tracking_number || '';
            const partnerId = order?.partner_id || '';

            const currencyId = this.selfOrder.currency?.id;
            if (!currencyId) {
                this.state.error = _t("Currency not configured");
                this.state.loading = false;
                return;
            }

            if (orderAmount <= 0) {
                this.state.error = _t("No amount to pay");
                this.state.loading = false;
                return;
            }

            const paymentUrl = `/payment/pay?amount=${orderAmount}&currency_id=${currencyId}&partner_id=${partnerId}&reference=${encodeURIComponent(orderRef)}&payment_method_id=${paymentMethodId}`;
            window.location.href = paymentUrl;
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
