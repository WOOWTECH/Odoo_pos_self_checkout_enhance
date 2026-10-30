/** @odoo-module */
import { ComboPage } from "@pos_self_order/app/pages/combo_page/combo_page";
import { patch } from "@web/core/utils/patch";

patch(ComboPage.prototype, {
    setup() {
        super.setup(...arguments);

        // Defensive: only enable the new flat layout when every combo line is
        // a simple non-variant product. If anything is variant-laden we fall
        // back to the stock wizard so we never silently drop attribute values.
        const allSimple = this.props.product.combo_ids.every((combo) =>
            combo.combo_item_ids.every(
                (line) =>
                    line.product_id &&
                    (!line.product_id.attribute_line_ids ||
                        line.product_id.attribute_line_ids.length === 0)
            )
        );
        this.state.useFlatLayout = allSimple;
        if (!allSimple) {
            console.warn(
                "[pos_self_order_enhancement] Combo product has variant-laden choices; falling back to stock wizard."
            );
            return;
        }

        // Flat layout state: one selected combo_item id per pickable combo step.
        this.state.selectionByComboId = {};
        for (const combo of this.comboIds) {
            this.state.selectionByComboId[combo.id] = null;
        }

        // Pre-populate from editedLine (cart edit) so previous picks survive.
        const edited = this.selfOrder.editedLine;
        if (edited && edited.combo_line_ids && edited.combo_line_ids.length) {
            for (const child of edited.combo_line_ids) {
                const itemId = child.combo_item_id?.id;
                const comboId = child.combo_item_id?.combo_id?.id;
                if (itemId && comboId && comboId in this.state.selectionByComboId) {
                    this.state.selectionByComboId[comboId] = itemId;
                }
            }
            this.state.qty = edited.qty || 1;
        }
    },

    selectChoice(comboId, line) {
        if (!line.product_id || !line.product_id.self_order_available) return;
        this.state.selectionByComboId[comboId] = line.id;
    },

    isLineSelected(comboId, lineId) {
        return this.state.selectionByComboId[comboId] === lineId;
    },

    get isAllSelected() {
        if (!this.state.useFlatLayout) return false;
        return this.comboIds.every(
            (c) => !!this.state.selectionByComboId[c.id]
        );
    },

    async addToCart() {
        if (!this.state.useFlatLayout) {
            return super.addToCart(...arguments);
        }
        if (!this.isAllSelected) return;
        if (this.selfOrder.editedLine) {
            this.selfOrder.editedLine.delete();
        }

        // Walk every combo_ids on the parent product (not just the user-pickable
        // ones), so single-choice combo steps that stock would otherwise drop
        // are still attached to the order line.
        const selectedCombos = [];
        for (const combo of this.props.product.combo_ids) {
            const pickedId = this.state.selectionByComboId[combo.id];
            const itemId =
                pickedId ??
                (combo.combo_item_ids.length === 1
                    ? combo.combo_item_ids[0].id
                    : null);
            if (!itemId) continue; // shouldn't happen — guarded by isAllSelected
            const comboItem = this.selfOrder.models["product.combo.item"].get(
                itemId
            );
            selectedCombos.push({
                combo_item_id: comboItem,
                configuration: {
                    attribute_custom_values: [],
                    attribute_value_ids: [],
                    price_extra: 0,
                },
            });
        }

        this.selfOrder.addToCart(
            this.props.product,
            this.state.qty,
            "",
            {},
            {},
            selectedCombos
        );
        this.router.back();
    },
});
