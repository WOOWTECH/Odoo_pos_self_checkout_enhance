/** @odoo-module */

import { CartPage } from "@pos_self_order/app/pages/cart_page/cart_page";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { CancelPopup } from "@pos_self_order/app/components/cancel_popup/cancel_popup";

patch(CartPage.prototype, {
    // ── Meal mode section getters ──

    get isMealMode() {
        return this.selfOrder.config.self_ordering_pay_after === "meal";
    },

    get sentLines() {
        const order = this.selfOrder.currentOrder;
        const lineChanges = order.uiState.lineChanges;
        return order.lines.filter(
            (l) =>
                !l.combo_parent_id &&
                lineChanges[l.uuid] &&
                lineChanges[l.uuid].qty === l.qty
        );
    },

    get newLines() {
        const order = this.selfOrder.currentOrder;
        return order.unsentLines.filter((l) => !l.combo_parent_id);
    },

    get hasSentLines() {
        return this.sentLines.length > 0;
    },

    get hasNewLines() {
        return this.newLines.length > 0;
    },

    get sentLinesSubtotal() {
        return this.sentLines.reduce((sum, line) => sum + this.getPrice(line), 0);
    },

    get newLinesSubtotal() {
        return this.newLines.reduce((sum, line) => sum + this.getPrice(line), 0);
    },

    get linesToDisplay() {
        if (this.isMealMode) {
            // In meal mode, the original foreach only renders new/unsent items.
            // Sent items are rendered separately in the "Sent to Kitchen" section.
            return this.selfOrder.currentOrder.unsentLines;
        }
        return super.linesToDisplay;
    },

    /**
     * Hide cancel button for submitted orders.
     * Submitted = has tracking_number or pos_reference (sent to kitchen).
     */
    get showCancelButton() {
        const order = this.selfOrder.currentOrder;
        const hasServerId = typeof order.id === "number";
        const isSubmitted = hasServerId && (order.tracking_number || order.pos_reference);

        if (isSubmitted) {
            return false;
        }

        return (
            this.selfOrder.config.self_ordering_mode === "mobile" &&
            this.selfOrder.config.self_ordering_pay_after === "each" &&
            hasServerId
        );
    },

    /**
     * Increase quantity using the existing _changeQuantity method
     * which properly handles combo child lines.
     */
    async increaseQuantity(line) {
        await this._changeQuantity(line, true);
    },

    /**
     * Decrease quantity using the existing _changeQuantity method.
     * If quantity is 1, show confirmation dialog before removing.
     */
    async decreaseQuantity(line) {
        if (line.qty > 1) {
            await this._changeQuantity(line, false);
        } else {
            this.dialog.add(CancelPopup, {
                title: _t("Remove item"),
                confirm: () => {
                    this.selfOrder.removeLine(line);
                },
            });
        }
    },

    /**
     * Override pay() for meal mode with pending changes.
     * For all other cases, delegate to super.pay().
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

            // Show table selector if table mode but no table set (same as base pay())
            const serviceMode = this.selfOrder.config.self_ordering_service_mode;
            const orderingType = this.selfOrder.config.self_ordering_mode;
            if (
                orderingType === "mobile" &&
                serviceMode === "table" &&
                !order.takeaway &&
                !this.selfOrder.currentTable
            ) {
                this.state.selectTable = true;
                return;
            }

            // Set table from QR scan if not already set on order
            if (!order.table_id && this.selfOrder.currentTable) {
                this.selfOrder.currentOrder.update({
                    table_id: this.selfOrder.currentTable,
                });
            } else if (order.table_id) {
                this.selfOrder.currentTable = order.table_id;
            }

            this.selfOrder.rpcLoading = true;
            try {
                const result = await this.selfOrder.sendDraftOrderToServer();
                if (result) {
                    const device = this.selfOrder.config.self_ordering_mode;
                    this.selfOrder.confirmationPage("order", device, result.access_token);
                }
            } catch (error) {
                console.error("Failed to send order:", error);
            } finally {
                this.selfOrder.rpcLoading = false;
            }
            return;
        }

        // In meal mode without changes, preserve table_id
        if (payAfter === "meal" && order.table_id) {
            this.selfOrder.currentTable = order.table_id;
        }

        // Delegate to original pay() for all other cases
        return super.pay();
    },
});
