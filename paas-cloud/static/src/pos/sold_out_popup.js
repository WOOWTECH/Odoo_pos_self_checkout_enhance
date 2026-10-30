/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { _t } from "@web/core/l10n/translation";

export class SoldOutManagementPopup extends Component {
    static template = "pos_self_order_enhancement.SoldOutManagementPopup";
    static components = { Dialog };
    static props = {
        close: Function,
    };

    setup() {
        this.pos = usePos();
        this.state = useState({
            searchTerm: "",
            filter: "all", // "all" or "sold_out"
        });
    }

    get products() {
        const allProducts = [];
        for (const product of this.pos.models["product.product"].getAll()) {
            if (!product.available_in_pos) continue;
            if (!product.active) continue;
            allProducts.push(product);
        }
        // Filter by search term
        let filtered = allProducts;
        if (this.state.searchTerm) {
            const term = this.state.searchTerm.toLowerCase();
            filtered = filtered.filter((p) =>
                (p.display_name || p.name || "").toLowerCase().includes(term)
            );
        }
        // Filter by tab
        if (this.state.filter === "sold_out") {
            filtered = filtered.filter((p) => p.is_sold_out);
        }
        // Sort: sold out first, then by name
        filtered.sort((a, b) => {
            if (a.is_sold_out !== b.is_sold_out) return a.is_sold_out ? -1 : 1;
            return (a.display_name || a.name || "").localeCompare(
                b.display_name || b.name || ""
            );
        });
        return filtered;
    }

    get soldOutCount() {
        let count = 0;
        for (const product of this.pos.models["product.product"].getAll()) {
            if (product.available_in_pos && product.active && product.is_sold_out) {
                count++;
            }
        }
        return count;
    }

    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
    }

    setFilter(filter) {
        this.state.filter = filter;
    }

    async toggleSoldOut(product) {
        await this.pos.data.write("product.product", [product.id], {
            is_sold_out: !product.is_sold_out,
        });
    }

    getProductImageUrl(product) {
        return `/web/image/product.product/${product.id}/image_128`;
    }
}
