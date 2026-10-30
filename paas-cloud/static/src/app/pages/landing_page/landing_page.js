/** @odoo-module */

import { LandingPage } from "@pos_self_order/app/pages/landing_page/landing_page";
import { patch } from "@web/core/utils/patch";

patch(LandingPage.prototype, {
    /**
     * Navigate to product list to continue adding items to existing order.
     */
    continueOrdering() {
        const orders = this.draftOrder;
        if (orders && orders.length > 0) {
            const order = orders[0];
            if (order.uuid) {
                this.selfOrder.selectedOrderUuid = order.uuid;
            }
        }
        this.router.navigate("product_list");
    },

    /**
     * Navigate to order history page in view-only mode.
     */
    viewOrderHistory() {
        const currentUrl = new URL(window.location.href);
        currentUrl.searchParams.set('viewHistory', 'true');
        window.history.replaceState({}, '', currentUrl.toString());
        this.router.navigate("orderHistory");
    },

    /**
     * Enhanced clickMyOrder: cart if draft orders, else order history.
     */
    clickMyOrderEnhanced() {
        if (this.draftOrder.length > 0) {
            this.router.navigate("cart");
        } else {
            this.viewOrderHistory();
        }
    },

    /**
     * Override hideBtn - call super first, then add meal-mode logic.
     */
    hideBtn(link) {
        // Call parent logic first
        const parentResult = super.hideBtn(link);
        if (parentResult) {
            return true;
        }

        const arrayLink = link.url.split("/");
        const routeName = arrayLink[arrayLink.length - 1];

        if (routeName !== "products") {
            return false;
        }

        const payAfter = this.selfOrder?.config?.self_ordering_pay_after;

        // In meal mode: hide products button when submitted orders exist
        if (payAfter === "meal" && this.draftOrder.length > 0) {
            const hasSubmittedOrder = this.draftOrder.some(order =>
                order.id && (order.tracking_number || order.pos_reference)
            );
            if (hasSubmittedOrder) {
                return true;
            }
        }

        return false;
    },

    /**
     * Show "Continue Ordering" button when customer has submitted unpaid orders.
     * Only in mobile mode with pay_after="each".
     */
    get showContinueOrderingBtn() {
        if (!this.selfOrder?.config) {
            return false;
        }

        const isMobile = this.selfOrder.config.self_ordering_mode === "mobile";
        const payAfter = this.selfOrder.config.self_ordering_pay_after;

        // Only support "each" mode — meal mode goes straight to payment
        if (!isMobile || payAfter !== "each") {
            return false;
        }

        const orders = this.draftOrder;
        if (!orders || orders.length === 0) {
            return false;
        }

        return orders.some(order =>
            order.id && (order.tracking_number || order.pos_reference)
        );
    },
});
