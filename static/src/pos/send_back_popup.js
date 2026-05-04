/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

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
            { id: "remake", label: _t("Remake") },
            { id: "wrong_item", label: _t("Wrong Item") },
            { id: "undercooked", label: _t("Undercooked") },
            { id: "changed_mind", label: _t("Customer Changed Mind") },
        ];
        this.state = useState({
            selectedLines: Object.fromEntries(
                this.props.lines.map((l) => [l.id, false])
            ),
            reason: "remake",
        });
    }

    get dialogTitle() {
        return this.props.title || _t("Send Back to Kitchen");
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
