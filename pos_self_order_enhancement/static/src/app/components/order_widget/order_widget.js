/** @odoo-module */

import { OrderWidget } from "@pos_self_order/app/components/order_widget/order_widget";
import { patch } from "@web/core/utils/patch";
import { onPatched, onMounted } from "@odoo/owl";

patch(OrderWidget.prototype, {
    setup() {
        super.setup(...arguments);

        // Update body class on mount and patch (M4: lifecycle hooks, not getter)
        const updateBackButtonVisibility = () => {
            const shouldHide = this._shouldHideBackButton();
            document.body.classList.toggle('hide-self-order-back-button', shouldHide);
        };

        onMounted(updateBackButtonVisibility);
        onPatched(updateBackButtonVisibility);
    },

    /**
     * Check if we should hide the left (back/cancel) button.
     */
    _shouldHideBackButton() {
        const isMealMode = this.selfOrder.config.self_ordering_pay_after === "meal";
        const isCartPage = this.router.activeSlot === "cart";
        return isMealMode && isCartPage;
    },

    // Back button visibility is handled by CSS via body class (set in lifecycle hooks above).
    // No need to override leftButton - super.leftButton provides correct button config.
});
