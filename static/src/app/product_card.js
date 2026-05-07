/** @odoo-module */
import { ProductCard } from "@pos_self_order/app/components/product_card/product_card";
import { patch } from "@web/core/utils/patch";

patch(ProductCard.prototype, {
    async selectProduct(qty) {
        const product = this.props.product;
        if (product.is_sold_out) {
            return;
        }
        if (!product.self_order_available || !this.isAvailable) {
            return;
        }
        // Combos keep their native flow (may need combo selection page).
        if (product.isCombo()) {
            return super.selectProduct(...arguments);
        }
        if (!this.selfOrder.ordering) {
            return;
        }
        // Always route to the product detail page so the customer can read
        // the description and pick a quantity before adding to the order.
        this.router.navigate("product", { id: product.id });
    },
});
