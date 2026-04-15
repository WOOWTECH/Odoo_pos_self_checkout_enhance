/** @odoo-module */

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class ServedPopup extends Component {
    static template = "pos_self_order_enhancement.ServedPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        tableName: String,
        items: Array,
        onServed: Function,
        close: Function,
    };

    onClickServed() {
        this.props.onServed();
        this.props.close();
    }
}
