/** @odoo-module */
import { ProductInfoPopup } from "@point_of_sale/app/screens/product_screen/product_info_popup/product_info_popup";
import { patch } from "@web/core/utils/patch";

patch(ProductInfoPopup.prototype, {
    async toggleSoldOut() {
        await this.pos.data.write("product.product", [this.props.product.id], {
            is_sold_out: !this.props.product.is_sold_out,
        });
    },
});
