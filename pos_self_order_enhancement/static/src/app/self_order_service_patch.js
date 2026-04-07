/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SelfOrder } from "@pos_self_order/app/self_order_service";

patch(SelfOrder.prototype, {
    initData() {
        // Build set of product IDs that exist only as combo choices.
        // The backend (_load_pos_self_data) injects every combo_item product
        // alongside combo products so the configurator can render them. We
        // want them loaded in the model but hidden from category browsing.
        const comboChoiceIds = new Set();
        for (const product of this.models["product.product"].getAll()) {
            if (product.type !== "combo") {
                continue;
            }
            for (const combo of product.combo_ids || []) {
                for (const item of combo.combo_item_ids || []) {
                    if (item.product_id) {
                        comboChoiceIds.add(item.product_id.id);
                    }
                }
            }
        }

        super.initData(...arguments);

        // Strip combo-choice products out of every category list (and the
        // synthetic "0" / Uncategorised bucket) populated by the base impl.
        for (const categId in this.productByCategIds) {
            this.productByCategIds[categId] = this.productByCategIds[categId].filter(
                (p) => !comboChoiceIds.has(p.id)
            );
        }

        // Drop categories that became empty after filtering (e.g. the
        // "Uncategorised" tab created solely by combo-choice products which
        // carry no pos_categ_ids).
        const emptyCategIds = new Set();
        for (const categId in this.productByCategIds) {
            if (this.productByCategIds[categId].length === 0) {
                emptyCategIds.add(Number(categId));
                delete this.productByCategIds[categId];
            }
        }
        if (emptyCategIds.size) {
            this.productCategories = this.productCategories.filter(
                (c) => !emptyCategIds.has(Number(c.id))
            );
        }
    },
});
