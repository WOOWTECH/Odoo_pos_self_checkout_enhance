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
        this.router = useService("router");
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
     */
    get hasOnlinePayment() {
        try {
            // Check for configured online payment method
            const onlinePaymentMethodId = this.selfOrder.config.self_ordering_online_payment_method_id;
            return onlinePaymentMethodId && onlinePaymentMethodId.length > 0;
        } catch (e) {
            return false;
        }
    }

    /**
     * Get available online payment methods
     */
    get onlinePaymentMethods() {
        try {
            const allMethods = this.selfOrder.models["pos.payment.method"].getAll();
            // Filter to only online payment capable methods
            return allMethods.filter(method => {
                return method.is_online_payment ||
                       ["adyen", "stripe"].includes(method.use_payment_terminal);
            });
        } catch (e) {
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
     * Handle online payment selection
     */
    async selectOnlinePayment(paymentMethodId) {
        this.state.loading = true;
        this.state.error = null;

        try {
            // Process online payment through Odoo's payment flow
            await this.selfOrder.processOnlinePayment(paymentMethodId);
            // Navigation will be handled by the payment service
        } catch (error) {
            console.error("Online payment error:", error);
            this.state.error = "付款處理失敗，請重試";
            this.state.loading = false;
        }
    }

    /**
     * Navigate back to home/landing page (整單結 - full bill settlement)
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
