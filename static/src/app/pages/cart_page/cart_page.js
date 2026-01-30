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
     * Increase quantity of a line item by 1.
     * @param {Object} line - The order line to modify
     */
    increaseQuantity(line) {
        line.qty += 1;
        line.setDirty();
    },

    /**
     * Decrease quantity of a line item by 1.
     * If quantity would become 0, show confirmation dialog before deleting.
     * @param {Object} line - The order line to modify
     */
    async decreaseQuantity(line) {
        if (line.qty > 1) {
            line.qty -= 1;
            line.setDirty();
        } else {
            // Quantity is 1, confirm before deleting
            const confirmed = window.confirm("確定要刪除此品項嗎？");
            if (confirmed) {
                line.qty = 0;
                line.setDirty();
                this.selfOrder.removeLine(line);
            }
        }
    },

    /**
     * Override pay() for meal mode.
     * If there are unsaved quantity changes, sync them first and stay on cart page.
     * Only proceed to table selection when there are no pending changes.
     */
    async pay() {
        const payAfter = this.selfOrder.config.self_ordering_pay_after;
        const order = this.selfOrder.currentOrder;
        const hasChanges = Object.keys(order.changes).length > 0;

        // In meal mode with pending changes: sync changes and stay on cart page
        if (payAfter === "meal" && hasChanges) {
            if (this.selfOrder.rpcLoading) {
                return;
            }

            // Use existing table_id if available
            if (order.table_id) {
                this.selfOrder.currentTable = order.table_id;
            }

            // Sync changes to server
            this.selfOrder.rpcLoading = true;
            await this.selfOrder.sendDraftOrderToServer();
            this.selfOrder.rpcLoading = false;

            // Stay on cart page - changes are now synced
            // User will see updated quantities and can press Order again to proceed
            return;
        }

        // For all other cases, use original pay() logic
        const orderingMode = this.selfOrder.config.self_ordering_service_mode;
        const type = this.selfOrder.config.self_ordering_mode;
        const takeAway = order.takeaway;

        if (
            this.selfOrder.rpcLoading ||
            !this.selfOrder.verifyCart() ||
            !this.selfOrder.verifyPriceLoading()
        ) {
            return;
        }

        // In meal mode without changes, use existing table_id
        if (payAfter === "meal" && order.table_id) {
            this.selfOrder.currentTable = order.table_id;
        }

        if (
            type === "mobile" &&
            orderingMode === "table" &&
            !takeAway &&
            !this.selfOrder.currentTable
        ) {
            this.state.selectTable = true;
            return;
        } else {
            this.selfOrder.currentOrder.update({
                table_id: this.selfOrder.currentTable,
            });
        }

        this.selfOrder.rpcLoading = true;
        await this.selfOrder.confirmOrder();
        this.selfOrder.rpcLoading = false;
    },
});
