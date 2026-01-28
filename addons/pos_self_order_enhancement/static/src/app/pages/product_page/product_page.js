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
        return this.isPayPerMeal && (this.selfOrder.editedLine || this._editingLine);
    },

    /**
     * Override initState to capture the edited line reference
     */
    initState() {
        const editedLine = this.selfOrder.editedLine;
        if (editedLine && this.isPayPerMeal) {
            // Store a reference to the line we're editing
            this._editingLine = editedLine;
        }
        // Call the original initState
        if (editedLine) {
            this.state.customer_note = editedLine.customer_note;
            this.state.qty = editedLine.qty;
        }
        return 0;
    },

    /**
     * Discard changes and go back.
     * In meal mode editing, go directly to cart instead of product list.
     */
    discardEdit() {
        // Clear editing references
        this.selfOrder.editedLine = null;
        this._editingLine = null;

        // In meal mode, go to cart; otherwise use back navigation
        if (this.isPayPerMeal) {
            this.router.navigate("cart");
        } else {
            this.router.back();
        }
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
        // Check if we're editing BEFORE any navigation
        // Use _editingLine which was stored in initState
        const editingLine = this._editingLine;
        const isEditing = this.isPayPerMeal && editingLine;

        if (isEditing) {
            if (this.state.qty === 0) {
                // Delete: set qty to 0 and remove the line
                editingLine.qty = 0;
                editingLine.setDirty();
                this.selfOrder.removeLine(editingLine);
            } else {
                // Update: set the new quantity directly (not add to it)
                editingLine.qty = this.state.qty;
                editingLine.customer_note = this.state.customer_note;
                editingLine.setDirty();
            }
            // Clear the editedLine references BEFORE navigation
            this.selfOrder.editedLine = null;
            this._editingLine = null;
            // Navigate directly to cart page instead of going back to product list
            this.router.navigate("cart");
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

        // In meal mode, go directly to cart page; otherwise use back navigation
        if (this.isPayPerMeal) {
            this.router.navigate("cart");
        } else {
            this.router.back();
        }
    },
});
