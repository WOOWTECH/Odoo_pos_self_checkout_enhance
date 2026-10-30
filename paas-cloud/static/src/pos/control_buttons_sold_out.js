/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { SoldOutManagementPopup } from "@pos_self_order_enhancement/pos/sold_out_popup";

patch(ControlButtons.prototype, {
    onClickSoldOutManagement() {
        this.dialog.add(SoldOutManagementPopup, {});
        if (this.props.close) {
            this.props.close();
        }
    },
});
