/** @odoo-module */
import { ProductCard } from "@pos_self_order/app/components/product_card/product_card";
import { patch } from "@web/core/utils/patch";

patch(ProductCard.prototype, {
    async selectProduct(qty) {
        if (this.props.product.is_sold_out) {
            return;
        }
        return super.selectProduct(...arguments);
    },
});
