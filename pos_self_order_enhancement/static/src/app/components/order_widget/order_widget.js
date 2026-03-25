/** @odoo-module */

import { OrderWidget } from "@pos_self_order/app/components/order_widget/order_widget";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

/**
 * Patch OrderWidget to hide back button on cart page in meal mode.
 *
 * Business Logic:
 * - In meal mode (餐點結), when on the cart page, hide the back button
 * - This prevents customers from accidentally navigating away from the cart
 * - The Order button will be the main action to submit items
 */
patch(OrderWidget.prototype, {
    /**
     * Check if we should hide the left (back/cancel) button.
     * Returns true if we're on cart page in meal mode.
     */
    shouldHideBackButton() {
        const isMealMode = this.selfOrder.config.self_ordering_pay_after === "meal";
        const isCartPage = this.router.activeSlot === "cart";
        return isMealMode && isCartPage;
    },

    /**
     * Override leftButton getter to update body class and return button config.
     */
    get leftButton() {
        // Update body class based on current state
        const shouldHide = this.shouldHideBackButton();
        document.body.classList.toggle('hide-self-order-back-button', shouldHide);

        // Use original logic for button config
        const order = this.selfOrder.currentOrder;
        const back =
            Object.keys(order.changes).length === 0 ||
            this.router.activeSlot === "cart" ||
            order.lines.length === 0;

        return {
            name: back ? _t("Back") : _t("Cancel"),
            icon: back ? "fa fa-arrow-left btn-back" : "btn-close btn-cancel",
        };
    },
});
