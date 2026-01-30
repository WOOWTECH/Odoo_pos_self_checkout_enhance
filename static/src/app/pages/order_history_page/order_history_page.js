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
 * - Hide checkout section if user just completed payment (view history mode)
 * - In "Pay per Meal" mode, add edit button to modify order items
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
     * Check if the POS is configured for "Pay per Meal" mode (餐點結).
     * @returns {boolean}
     */
    get isPayPerMeal() {
        try {
            return this.selfOrder?.config?.self_ordering_pay_after === 'meal';
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
     * Get all paid orders (for history view).
     * @returns {Array}
     */
    get paidOrders() {
        try {
            return this.orders.filter(order => order.state === 'paid');
        } catch (e) {
            return [];
        }
    },

    /**
     * Check if there are unpaid orders that can be checked out.
     * Only returns true if:
     * 1. There are unpaid orders
     * 2. Not in "view history only" mode (when coming from payment success or landing page "我的銷售訂單")
     * @returns {boolean}
     */
    get hasUnpaidOrders() {
        // If URL has viewHistory parameter or came from payment success, hide checkout section
        const urlParams = new URLSearchParams(window.location.search);
        const viewHistoryOnly = urlParams.get('viewHistory') === 'true';

        if (viewHistoryOnly) {
            return false;
        }

        return this.unpaidOrders.length > 0;
    },

    /**
     * Check if we should show the checkout section.
     * Show checkout section only when:
     * 1. In pay per order mode
     * 2. There are unpaid orders
     * 3. The unpaid orders have been submitted (have tracking_number or pos_reference)
     * 4. Not all orders are paid (don't show checkout after payment success)
     * @returns {boolean}
     */
    get showCheckoutSection() {
        // Not in pay per order mode
        if (!this.isPayPerOrder) {
            return false;
        }

        // No unpaid orders
        if (this.unpaidOrders.length === 0) {
            return false;
        }

        // Check if unpaid orders have been submitted to server
        // (have tracking_number or pos_reference, meaning they went through confirmation)
        const hasSubmittedUnpaidOrder = this.unpaidOrders.some(order =>
            order.id && (order.tracking_number || order.pos_reference)
        );

        if (!hasSubmittedUnpaidOrder) {
            return false;
        }

        // Check if URL indicates view history mode (from landing page "我的銷售訂單" button)
        const urlParams = new URLSearchParams(window.location.search);
        const viewHistoryOnly = urlParams.get('viewHistory') === 'true';

        if (viewHistoryOnly) {
            return false;
        }

        return true;
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

    /**
     * Edit a line item in the order (for meal mode).
     * This navigates to the product page where user can modify quantity.
     * @param {Event} ev - Click event
     * @param {Object} order - The order containing the line
     * @param {Object} line - The line item to edit
     */
    editLineItem(ev, order, line) {
        ev.stopPropagation(); // Prevent order header click

        try {
            // Select the order
            if (order.uuid) {
                this.selfOrder.selectedOrderUuid = order.uuid;
            }

            // Navigate to product page with the line's product
            const productId = line.product_id?.id || line.product_id;
            if (productId) {
                this.router.navigate("product", { id: productId });
            } else {
                // Fallback to product list
                this.router.navigate("product_list");
            }
        } catch (e) {
            console.error("Edit line item error:", e);
            this.router.navigate("product_list");
        }
    },
});
