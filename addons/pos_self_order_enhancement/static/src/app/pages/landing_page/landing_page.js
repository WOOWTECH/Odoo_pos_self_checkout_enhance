/** @odoo-module */

import { LandingPage } from "@pos_self_order/app/pages/landing_page/landing_page";
import { patch } from "@web/core/utils/patch";

/**
 * Patch LandingPage to add "Continue Ordering" button and "View Order History" button.
 *
 * Business Logic:
 * - When customer has an existing unpaid order, show "Continue Ordering" button
 * - Button appears below "My Order" button with the same style
 * - Clicking navigates directly to product list to add more items
 * - Only shown in mobile mode with pay_after="each" configuration
 * - "我的銷售訂單" button navigates to order history in view-only mode
 */
patch(LandingPage.prototype, {
    /**
     * Navigate to product list to continue adding items to existing order.
     */
    continueOrdering() {
        // Get the current draft order
        const orders = this.draftOrder;
        if (orders && orders.length > 0) {
            // Set the selected order UUID to the first draft order
            const order = orders[0];
            if (order.uuid) {
                this.selfOrder.selectedOrderUuid = order.uuid;
            }
        }
        // Navigate to product list page
        this.router.navigate("product_list");
    },

    /**
     * Navigate to order history page in view-only mode.
     * This is for the "我的銷售訂單" button on landing page.
     * Shows order history without checkout section.
     */
    viewOrderHistory() {
        // Add viewHistory parameter to URL before navigating
        const currentUrl = new URL(window.location.href);
        currentUrl.searchParams.set('viewHistory', 'true');
        window.history.replaceState({}, '', currentUrl.toString());

        // Navigate to order history page
        this.router.navigate("orderHistory");
    },

    /**
     * Enhanced version of clickMyOrder that:
     * - Goes to cart if there are draft orders with items in cart
     * - Goes to order history (view-only mode) if showing "My Orders" (no draft orders)
     */
    clickMyOrderEnhanced() {
        if (this.draftOrder.length > 0) {
            // Has draft orders - go to cart
            this.router.navigate("cart");
        } else {
            // No draft orders - go to order history in view-only mode
            this.viewOrderHistory();
        }
    },

    /**
     * Check if the "Continue Ordering" button should be displayed.
     * Only show when:
     * - Customer has existing unpaid/draft orders
     * - In mobile mode (not kiosk)
     * - pay_after is set to "each"
     */
    get showContinueOrderingBtn() {
        try {
            // Safety check for selfOrder and config
            if (!this.selfOrder || !this.selfOrder.config) {
                return false;
            }

            // Check configuration: mobile mode with pay_after="each"
            const isMobile = this.selfOrder.config.self_ordering_mode === "mobile";
            const payAfterEach = this.selfOrder.config.self_ordering_pay_after === "each";

            if (!isMobile || !payAfterEach) {
                return false;
            }

            // Check if there are draft orders
            const orders = this.draftOrder;
            if (!orders || orders.length === 0) {
                return false;
            }

            // Check if any order has been submitted to server (has tracking_number or pos_reference)
            const hasSubmittedOrder = orders.some(order =>
                order.id && (order.tracking_number || order.pos_reference)
            );

            return hasSubmittedOrder;
        } catch (e) {
            console.error("showContinueOrderingBtn error:", e);
            return false;
        }
    },
});
