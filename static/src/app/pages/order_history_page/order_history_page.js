/** @odoo-module */

import { OrdersHistoryPage } from "@pos_self_order/app/pages/order_history_page/order_history_page";
import { patch } from "@web/core/utils/patch";

/**
 * Patch OrdersHistoryPage to support "Pay per Order" checkout.
 *
 * Business Logic:
 * - In "Pay per Order" mode, show total of all unpaid orders
 * - Add "Checkout" button to proceed to payment
 * - Add "Continue Ordering" button to go back to product list
 */
patch(OrdersHistoryPage.prototype, {
    /**
     * Check if the POS is configured for "Pay per Order" mode.
     * @returns {boolean}
     */
    get isPayPerOrder() {
        try {
            return this.selfOrder?.config?.self_ordering_pay_after === 'each';
        } catch (e) {
            return false;
        }
    },

    /**
     * Get all unpaid orders.
     * @returns {Array}
     */
    get unpaidOrders() {
        try {
            return this.orders.filter(order => order.state !== 'paid');
        } catch (e) {
            return [];
        }
    },

    /**
     * Check if there are unpaid orders that can be checked out.
     * @returns {boolean}
     */
    get hasUnpaidOrders() {
        return this.unpaidOrders.length > 0;
    },

    /**
     * Calculate the total amount of all unpaid orders.
     * @returns {number}
     */
    get totalUnpaidAmount() {
        try {
            return this.unpaidOrders.reduce((sum, order) => {
                const amount = order.amount_total || 0;
                return sum + amount;
            }, 0);
        } catch (e) {
            return 0;
        }
    },

    /**
     * Format currency for display.
     * @param {number} amount
     * @returns {string}
     */
    formatCurrency(amount) {
        try {
            const currency = this.selfOrder?.currency;
            if (currency) {
                return currency.symbol + ' ' + amount.toFixed(currency.decimal_places || 0);
            }
            return 'NT$ ' + amount.toFixed(0);
        } catch (e) {
            return 'NT$ ' + (amount || 0).toFixed(0);
        }
    },

    /**
     * Navigate to payment page for checkout.
     * In "Pay per Order" mode, this processes all unpaid orders.
     */
    async checkout() {
        try {
            // If there's only one unpaid order, select it and go to payment
            if (this.unpaidOrders.length === 1) {
                const order = this.unpaidOrders[0];
                if (order.uuid) {
                    this.selfOrder.selectedOrderUuid = order.uuid;
                }
            }
            // Navigate to payment page
            this.router.navigate("payment");
        } catch (e) {
            console.error("Checkout error:", e);
        }
    },

    /**
     * Navigate to product list to continue ordering.
     */
    continueOrdering() {
        try {
            // Select the first unpaid order if exists
            if (this.unpaidOrders.length > 0) {
                const order = this.unpaidOrders[0];
                if (order.uuid) {
                    this.selfOrder.selectedOrderUuid = order.uuid;
                }
            }
            this.router.navigate("product_list");
        } catch (e) {
            console.error("Continue ordering error:", e);
            this.router.navigate("product_list");
        }
    },
});
