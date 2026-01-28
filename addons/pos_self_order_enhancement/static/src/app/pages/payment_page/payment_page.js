/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/self_order_service";
import { useService } from "@web/core/utils/hooks";

/**
 * Custom Payment Page for Pay-per-Meal mode (整單結)
 * Displays order summary grouped by ordering session and handles payment
 */
export class PaymentPage extends Component {
    static template = "pos_self_order_enhancement.PaymentPage";
    static props = {};

    setup() {
        this.selfOrder = useSelfOrder();
        // Get router from selfOrder service (not useService)
        this.router = this.selfOrder.router;
        this.state = useState({
            loading: false,
            error: null,
        });
    }

    /**
     * Get the current order
     */
    get currentOrder() {
        return this.selfOrder.currentOrder;
    }

    /**
     * Get order lines for display
     */
    get orderLines() {
        try {
            return this.currentOrder?.lines || [];
        } catch (e) {
            return [];
        }
    }

    /**
     * Get order lines grouped by ordering session (batch)
     * Groups items by their order_time or sequential batches
     */
    get groupedOrderLines() {
        try {
            const lines = this.currentOrder?.lines || [];
            if (lines.length === 0) return [];

            // Group lines by their batch/session
            // Use line.uuid prefix or create_date to identify batches
            const groups = [];
            let currentGroup = null;
            let groupIndex = 1;

            // Sort lines by create time if available
            const sortedLines = [...lines].sort((a, b) => {
                const timeA = a.create_date || a.write_date || 0;
                const timeB = b.create_date || b.write_date || 0;
                return timeA - timeB;
            });

            // Group lines - detect batch changes by time gaps or explicit markers
            let lastTime = null;
            for (const line of sortedLines) {
                const lineTime = line.create_date || line.write_date;

                // Start new group if: first line, or significant time gap (> 60 seconds)
                const isNewBatch = !currentGroup ||
                    (lastTime && lineTime && (lineTime - lastTime) > 60000);

                if (isNewBatch) {
                    currentGroup = {
                        index: groupIndex++,
                        lines: [],
                        subtotal: 0
                    };
                    groups.push(currentGroup);
                }

                currentGroup.lines.push(line);
                currentGroup.subtotal += line.price_subtotal_incl || 0;
                lastTime = lineTime;
            }

            // If only one group, don't show grouping
            if (groups.length === 1) {
                return [{ index: 0, lines: sortedLines, subtotal: this.totalAmount, single: true }];
            }

            return groups;
        } catch (e) {
            console.error("Error grouping order lines:", e);
            return [{ index: 0, lines: this.orderLines, subtotal: this.totalAmount, single: true }];
        }
    }

    /**
     * Get the current session's added amount (本次加點金額)
     */
    get currentSessionAmount() {
        try {
            const groups = this.groupedOrderLines;
            if (groups.length <= 1) return 0;
            // Return the last group's subtotal as "this order" amount
            return groups[groups.length - 1]?.subtotal || 0;
        } catch (e) {
            return 0;
        }
    }

    /**
     * Check if there are multiple ordering sessions
     */
    get hasMultipleSessions() {
        return this.groupedOrderLines.length > 1;
    }

    /**
     * Get order total amount
     */
    get totalAmount() {
        try {
            return this.currentOrder?.amount_total || 0;
        } catch (e) {
            return 0;
        }
    }

    /**
     * Get order reference/number
     */
    get orderReference() {
        try {
            return this.currentOrder?.pos_reference ||
                   this.currentOrder?.tracking_number ||
                   this.currentOrder?.name ||
                   '';
        } catch (e) {
            return '';
        }
    }

    /**
     * Check if online payment methods are available
     * Check multiple conditions:
     * 1. self_ordering_online_payment_method_id is configured
     * 2. OR there are payment methods with is_online_payment flag
     */
    get hasOnlinePayment() {
        try {
            // First check for specifically configured online payment method
            const config = this.selfOrder.config;
            const onlinePaymentMethodId = config?.self_ordering_online_payment_method_id;

            // Check if configured payment method ID exists
            if (onlinePaymentMethodId) {
                // Could be an array [id, name] or just an ID
                const methodId = Array.isArray(onlinePaymentMethodId)
                    ? onlinePaymentMethodId[0]
                    : onlinePaymentMethodId;
                if (methodId) {
                    return true;
                }
            }

            // Also check if any payment methods are marked as online payment
            const methods = this.onlinePaymentMethods;
            return methods && methods.length > 0;
        } catch (e) {
            console.error("hasOnlinePayment error:", e);
            return false;
        }
    }

    /**
     * Get available online payment methods
     * Returns payment methods that are:
     * 1. The configured self_ordering_online_payment_method_id
     * 2. OR have is_online_payment flag set to true
     * 3. OR use supported payment terminals (adyen, stripe, etc.)
     */
    get onlinePaymentMethods() {
        try {
            const allMethods = this.selfOrder.models["pos.payment.method"]?.getAll() || [];
            const config = this.selfOrder.config;
            const configuredMethodId = config?.self_ordering_online_payment_method_id;

            // Get the configured method ID (could be array or number)
            const targetMethodId = Array.isArray(configuredMethodId)
                ? configuredMethodId[0]
                : configuredMethodId;

            // Filter to online payment capable methods
            const methods = allMethods.filter(method => {
                // Include if it's the configured online payment method
                if (targetMethodId && method.id === targetMethodId) {
                    return true;
                }
                // Include if marked as online payment
                if (method.is_online_payment) {
                    return true;
                }
                // Include if using supported payment terminal
                if (["adyen", "stripe"].includes(method.use_payment_terminal)) {
                    return true;
                }
                return false;
            });

            return methods;
        } catch (e) {
            console.error("onlinePaymentMethods error:", e);
            return [];
        }
    }

    /**
     * Format currency for display
     */
    formatCurrency(amount) {
        try {
            const currency = this.selfOrder.currency;
            if (!currency) {
                return `NT$ ${amount.toFixed(0)}`;
            }
            return currency.symbol + ' ' + amount.toFixed(currency.decimal_places || 0);
        } catch (e) {
            return `NT$ ${amount}`;
        }
    }

    /**
     * Go back to previous page
     */
    goBack() {
        this.router.navigate("cart");
    }

    /**
     * Handle counter payment selection (現場結帳)
     * User chooses to pay at the counter - go back to landing page
     */
    selectCounterPayment() {
        this.state.loading = true;

        try {
            // For counter payment, just go back to landing page
            // The order is submitted and will be paid at counter
            // Reset order state and navigate to home
            this.selfOrder.selectedOrderUuid = null;
            this.router.navigate("default");
        } catch (error) {
            console.error("Counter payment error:", error);
            this.state.error = "處理失敗，請重試";
            this.state.loading = false;
        }
    }

    /**
     * Handle online payment selection (線上支付)
     * Uses Odoo's payment portal flow
     */
    async selectOnlinePayment(paymentMethodId) {
        this.state.loading = true;
        this.state.error = null;

        try {
            // Get the current order
            const order = this.currentOrder;
            const configId = this.selfOrder.config?.id || 1;

            // Get order details (with fallbacks)
            const orderId = order?.id || '';
            const orderAmount = order?.amount_total || this.totalAmount || 0;
            const orderRef = order?.pos_reference || order?.name || order?.tracking_number || '';
            const accessToken = order?.access_token ||
                               this.selfOrder.access_token ||
                               this.selfOrder.config?.access_token || '';
            const currencyId = this.selfOrder.currency?.id || 136; // TWD default
            const partnerId = order?.partner_id || '';

            // Debug logging
            console.log("Order details for payment:", {
                orderId,
                orderAmount,
                orderRef,
                accessToken: accessToken ? "present" : "missing",
                configId,
                currencyId
            });

            // Build the payment URL
            let paymentUrl;

            if (orderAmount <= 0) {
                // No amount to pay
                this.state.error = "目前沒有待付款金額";
                this.state.loading = false;
                return;
            }

            // Use Odoo's payment portal
            paymentUrl = `/payment/pay?amount=${orderAmount}&currency_id=${currencyId}&partner_id=${partnerId}&reference=${encodeURIComponent(orderRef)}&payment_method_id=${paymentMethodId}`;

            console.log("Redirecting to payment URL:", paymentUrl);

            // Redirect to payment page
            window.location.href = paymentUrl;

        } catch (error) {
            console.error("Online payment error:", error);
            this.state.error = "付款處理失敗，請重試或選擇現場結帳";
            this.state.loading = false;
        }
    }

    /**
     * Navigate back to home/landing page
     */
    goToHome() {
        try {
            // Reset order state for new session
            this.selfOrder.selectedOrderUuid = null;
            // Navigate to landing page
            this.router.navigate("default");
        } catch (e) {
            console.error("Error navigating to home:", e);
            this.router.navigate("default");
        }
    }
}
