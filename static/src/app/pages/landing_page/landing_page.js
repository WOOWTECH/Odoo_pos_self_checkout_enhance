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
     * Override hideBtn to also hide "立即訂購" button in "meal" mode
     * when there are unpaid orders (order already submitted, waiting for payment).
     *
     * Original logic: hide products link when pay_after="each" and has draft orders
     * New logic: ALSO hide products link when pay_after="meal" and has unpaid orders
     */
    hideBtn(link) {
        const arrayLink = link.url.split("/");
        const routeName = arrayLink[arrayLink.length - 1];

        // Only apply to "products" route (立即訂購 button)
        if (routeName !== "products") {
            return false;
        }

        const payAfter = this.selfOrder?.config?.self_ordering_pay_after;

        // Original behavior: hide in "each" mode when has draft orders
        if (payAfter === "each" && this.draftOrder.length > 0) {
            return true;
        }

        // New behavior: hide in "meal" mode when has unpaid orders
        // (order submitted but not yet paid - user should pay first before ordering again)
        if (payAfter === "meal" && this.draftOrder.length > 0) {
            // Check if any draft order has been submitted (has tracking_number or pos_reference)
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
