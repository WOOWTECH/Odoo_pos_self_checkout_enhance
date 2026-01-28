/** @odoo-module */

import { ProductPage } from "@pos_self_order/app/pages/product_page/product_page";
import { patch } from "@web/core/utils/patch";

/**
 * Patch ProductPage to support editing in meal mode (餐點結).
 *
 * In meal mode, orders are already posted but customers should still be able to:
 * - Increase quantity (add more of the same item)
 * - Decrease quantity (reduce the amount)
 * - Delete item (set quantity to 0)
 */
patch(ProductPage.prototype, {
    /**
     * Check if we're in meal mode (餐點結)
     * @returns {boolean}
     */
    get isPayPerMeal() {
        return this.selfOrder?.config?.self_ordering_pay_after === 'meal';
    },

    /**
     * Check if we're editing an existing line in meal mode
     * @returns {boolean}
     */
    get isEditingInMealMode() {
        return this.isPayPerMeal && this.selfOrder.editedLine;
    },

    /**
     * Override changeQuantity to allow quantity to go to 0 in meal mode.
     * When quantity is 0, the item will be removed when saving.
     * @param {boolean} increase - Whether to increase or decrease
     */
    changeQuantity(increase) {
        const currentQty = this.state.qty;

        // In meal mode editing, allow quantity to go down to 0 (for deletion)
        if (!increase && currentQty === 0) {
            return;
        }

        // Allow decrease to 0 in meal mode, otherwise minimum is 1
        if (!increase && currentQty === 1) {
            if (this.isEditingInMealMode) {
                this.state.qty = 0;
                return;
            }
            return;
        }

        return increase ? this.state.qty++ : this.state.qty--;
    },

    /**
     * Override addToCart to handle meal mode editing.
     * In meal mode editing:
     * - If quantity is 0, remove the line
     * - Otherwise, UPDATE the existing line's quantity (not add new)
     */
    addToCart() {
        // If editing in meal mode, we need to UPDATE the existing line
        if (this.isEditingInMealMode) {
            const editedLine = this.selfOrder.editedLine;
            if (editedLine) {
                if (this.state.qty === 0) {
                    // Delete: set qty to 0 and remove the line
                    editedLine.qty = 0;
                    editedLine.setDirty();
                    this.selfOrder.removeLine(editedLine);
                } else {
                    // Update: set the new quantity directly (not add to it)
                    editedLine.qty = this.state.qty;
                    editedLine.customer_note = this.state.customer_note;
                    editedLine.setDirty();
                }
                // Clear the editedLine reference
                this.selfOrder.editedLine = null;
            }
            this.router.back();
            return;
        }

        // Normal add to cart behavior (not editing)
        this.selfOrder.addToCart(
            this.props.product,
            this.state.qty,
            this.state.customer_note,
            this.env.selectedValues,
            this.env.customValues
        );
        this.router.back();
    },
});
