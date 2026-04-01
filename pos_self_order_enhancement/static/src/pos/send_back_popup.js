/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class SendBackPopup extends Component {
    static template = "pos_self_order_enhancement.SendBackPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        lines: Array,
        getPayload: Function,
        close: Function,
    };

    setup() {
        this.reasons = [
            { id: "remake", label: "Remake / 重做" },
            { id: "wrong_item", label: "Wrong Item / 出錯" },
            { id: "undercooked", label: "Undercooked / 未熟" },
            { id: "changed_mind", label: "Customer Changed Mind / 客人改變主意" },
        ];
        this.state = useState({
            selectedLines: Object.fromEntries(
                this.props.lines.map((l) => [l.id, false])
            ),
            reason: "remake",
        });
    }

    get hasSelection() {
        return Object.values(this.state.selectedLines).some(Boolean);
    }

    toggleLine(lineId) {
        this.state.selectedLines[lineId] = !this.state.selectedLines[lineId];
    }

    confirm() {
        const selectedIds = Object.entries(this.state.selectedLines)
            .filter(([, v]) => v)
            .map(([k]) => parseInt(k));
        if (selectedIds.length === 0) return;
        this.props.getPayload({
            lineIds: selectedIds,
            reason: this.state.reason,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
