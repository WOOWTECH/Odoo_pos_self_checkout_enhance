/** @odoo-module */

import { ConfirmationPage } from "@pos_self_order/app/pages/confirmation_page/confirmation_page";
import { patch } from "@web/core/utils/patch";

patch(ConfirmationPage.prototype, {
    get isPayPerMeal() {
        return this.selfOrder?.config?.self_ordering_pay_after === 'meal';
    },

    get isPayPerOrder() {
        return this.selfOrder?.config?.self_ordering_pay_after === 'each';
    },

    /**
     * Show pay-per-meal UI: redirect to payment for unpaid mobile orders.
     */
    get showPayPerMealUI() {
        if (!this.isPayPerMeal) {
            return false;
        }
        const order = this.confirmedOrder;
        if (!order?.id) {
            return false;
        }
        const isPaid = order.state === 'paid';
        const isMobile = this.selfOrder?.config?.self_ordering_mode === 'mobile';
        return !isPaid && isMobile;
    },

    /**
     * Show pay-per-order UI: navigation buttons for unpaid mobile orders.
     */
    get showPayPerOrderUI() {
        if (!this.isPayPerOrder) {
            return false;
        }
        const order = this.confirmedOrder;
        if (!order?.id) {
            return false;
        }
        const isPaid = order.state === 'paid';
        const isMobile = this.selfOrder?.config?.self_ordering_mode === 'mobile';
        return !isPaid && isMobile;
    },

    goToPayment() {
        this.router.navigate("payment");
    },

    goToLanding() {
        this.router.navigate("default");
    },

    goToMyOrders() {
        this.router.navigate("orderHistory");
    },

    goToCart() {
        if (this.confirmedOrder?.uuid) {
            this.selfOrder.selectedOrderUuid = this.confirmedOrder.uuid;
        }
        this.router.navigate("cart");
    },
});
