/** @odoo-module */

import { CartPage } from "@pos_self_order/app/pages/cart_page/cart_page";
import { patch } from "@web/core/utils/patch";

/**
 * Patch CartPage to hide the cancel button after order is submitted.
 *
 * Business Logic:
 * - Draft orders (not yet submitted) can still be cancelled by customers
 * - Once an order is submitted (synced to server), customers cannot cancel
 * - Staff can still cancel orders from the POS backend
 * - This prevents confusion when kitchen has already started preparing
 */
patch(CartPage.prototype, {
    /**
     * Override showCancelButton to hide it only for submitted orders.
     *
     * Original Odoo 18 conditions:
     * - mobile mode enabled
     * - pay_after === "each"
     * - order has numeric ID
     *
     * Our modification:
     * - Keep original behavior for draft orders (allow cancel)
     * - Hide cancel button once order has been submitted/synced to server
     */
    get showCancelButton() {
        const order = this.selfOrder.currentOrder;
        const hasServerId = typeof order.id === "number";

        // Check if order has been submitted to server
        // In cash payment mode, order stays "draft" until paid at counter
        // We use tracking_number or pos_reference to detect if order was sent to kitchen
        const isSubmitted = hasServerId && (order.tracking_number || order.pos_reference);

        // If order is submitted to kitchen, don't show cancel button
        if (isSubmitted) {
            return false;
        }

        // For orders not yet submitted, use original Odoo logic
        return (
            this.selfOrder.config.self_ordering_mode === "mobile" &&
            this.selfOrder.config.self_ordering_pay_after === "each" &&
            hasServerId
        );
    },

    /**
     * Edit line item in meal mode (餐點結).
     * For posted orders, we add new lines rather than editing existing ones.
     * User can add more quantity via the product page.
     * To "delete", user needs to add negative adjustment or contact staff.
     * @param {Object} line - The order line to edit
     */
    editLineInMealMode(line) {
        try {
            // Get product ID from line
            const productId = line.product_id?.id || line.product_id;

            if (productId) {
                // Set the edited line so product page knows we're editing
                this.selfOrder.editedLine = line;
                // Navigate to product page to modify quantity
                this.router.navigate("product", { id: productId });
            } else {
                // Fallback to product list
                this.router.navigate("product_list");
            }
        } catch (e) {
            console.error("Edit line error:", e);
            this.router.navigate("product_list");
        }
    },

    /**
     * Check if we're in meal mode (餐點結)
     * @returns {boolean}
     */
    get isPayPerMeal() {
        return this.selfOrder?.config?.self_ordering_pay_after === 'meal';
    },
});
