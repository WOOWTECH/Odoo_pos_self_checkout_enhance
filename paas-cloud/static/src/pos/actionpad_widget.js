/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";

/**
 * Override the Order button disabled logic so that products WITHOUT a POS
 * category are still treated as sendable.  Upstream Odoo disables the button
 * when `displayCategoryCount` is empty, but that getter only counts products
 * whose category is in the printer's preparation categories.  Products with
 * no category at all are silently excluded, making the button permanently
 * disabled — a confusing UX.
 *
 * This patch adds `hasUncategorizedChanges` which checks for ANY new/changed
 * orderlines regardless of category, and uses it as a fallback in
 * `swapButtonClasses`.
 */
patch(ActionpadWidget.prototype, {
    /**
     * Returns true when the current order has new or changed lines that
     * are not reflected in `last_order_preparation_change`, regardless of
     * whether those lines belong to a printer preparation category.
     */
    get hasUncategorizedChanges() {
        const order = this.currentOrder;
        if (!order) return false;
        const lastLines = order.last_order_preparation_change?.lines || {};

        // Check for new or quantity-changed lines
        for (const line of order.get_orderlines()) {
            const oldKey = Object.keys(lastLines).find((k) =>
                k.startsWith(line.uuid)
            );
            const oldQty = oldKey ? lastLines[oldKey].quantity : 0;
            if (line.get_quantity() - oldQty && !line.skip_change) return true;
        }

        // Check for deleted lines
        for (const [, resume] of Object.entries(lastLines)) {
            if (!order.models["pos.order.line"].getBy("uuid", resume.uuid)) {
                return true;
            }
        }
        return false;
    },

    get swapButtonClasses() {
        const hasCatItems = this.displayCategoryCount.length;
        const hasAny = hasCatItems || this.hasUncategorizedChanges;
        return {
            "highlight btn-primary justify-content-between": hasCatItems,
            "highlight btn-primary justify-content-center": !hasCatItems && hasAny,
            "btn-light pe-none disabled justify-content-center": !hasAny,
            altlight: !hasAny && this.currentOrder?.hasSkippedChanges(),
        };
    },
});
