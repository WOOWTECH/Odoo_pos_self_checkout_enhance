/** @odoo-module */

import { OrdersHistoryPage } from "@pos_self_order/app/pages/order_history_page/order_history_page";
import { patch } from "@web/core/utils/patch";

patch(OrdersHistoryPage.prototype, {
    get isPayPerOrder() {
        return this.selfOrder?.config?.self_ordering_pay_after === 'each';
    },

    get isPayPerMeal() {
        return this.selfOrder?.config?.self_ordering_pay_after === 'meal';
    },

    get unpaidOrders() {
        return this.orders.filter(order => order.state !== 'paid');
    },

    get paidOrders() {
        return this.orders.filter(order => order.state === 'paid');
    },

    /**
     * Check if there are unpaid orders, respecting view-only mode.
     */
    get hasUnpaidOrders() {
        if (this._isViewHistoryMode()) {
            return false;
        }
        return this.unpaidOrders.length > 0;
    },

    /**
     * Show checkout section only when:
     * - Pay per order mode
     * - Has submitted unpaid orders
     * - Not in view-history mode
     */
    get showCheckoutSection() {
        if (!this.isPayPerOrder) {
            return false;
        }

        if (this.unpaidOrders.length === 0) {
            return false;
        }

        const hasSubmittedUnpaidOrder = this.unpaidOrders.some(order =>
            order.id && (order.tracking_number || order.pos_reference)
        );

        if (!hasSubmittedUnpaidOrder) {
            return false;
        }

        if (this._isViewHistoryMode()) {
            return false;
        }

        return true;
    },

    get totalUnpaidAmount() {
        return this.unpaidOrders.reduce((sum, order) => {
            return sum + (order.amount_total || 0);
        }, 0);
    },

    /**
     * Format currency using POS currency configuration.
     */
    formatCurrency(amount) {
        const currency = this.selfOrder?.currency;
        if (currency) {
            return currency.symbol + ' ' + amount.toFixed(currency.decimal_places || 0);
        }
        return String(amount);
    },

    async checkout() {
        if (this.unpaidOrders.length === 1) {
            const order = this.unpaidOrders[0];
            if (order.uuid) {
                this.selfOrder.selectedOrderUuid = order.uuid;
            }
        }
        this.router.navigate("payment");
    },

    continueOrdering() {
        // Clean up viewHistory param (M7)
        this._clearViewHistoryParam();

        if (this.unpaidOrders.length > 0) {
            const order = this.unpaidOrders[0];
            if (order.uuid) {
                this.selfOrder.selectedOrderUuid = order.uuid;
            }
        }
        this.router.navigate("product_list");
    },

    /**
     * Edit a line item - navigate to product page with editedLine set (L6).
     */
    editLineItem(ev, order, line) {
        ev.stopPropagation();

        if (order.uuid) {
            this.selfOrder.selectedOrderUuid = order.uuid;
        }

        // Set editedLine so product page treats this as edit, not new item (L6)
        this.selfOrder.editedLine = line;

        const productId = line.product_id?.id || line.product_id;
        if (productId) {
            this.router.navigate("product", { id: productId });
        } else {
            this.router.navigate("product_list");
        }
    },

    // ── Private helpers ──

    _isViewHistoryMode() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('viewHistory') === 'true';
    },

    /**
     * Clear viewHistory URL parameter (M7).
     */
    _clearViewHistoryParam() {
        const currentUrl = new URL(window.location.href);
        if (currentUrl.searchParams.has('viewHistory')) {
            currentUrl.searchParams.delete('viewHistory');
            window.history.replaceState({}, '', currentUrl.toString());
        }
    },
});
