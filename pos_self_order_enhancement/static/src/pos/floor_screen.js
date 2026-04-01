/** @odoo-module */

import { FloorScreen } from "@pos_restaurant/app/floor_screen/floor_screen";
import { patch } from "@web/core/utils/patch";

patch(FloorScreen.prototype, {
    getKdsReadyCount(table) {
        return this.pos.models["pos.order"].filter(
            (o) => o.table_id?.id === table.id && o.kds_state === "done" && !o.finalized
        ).length;
    },
});
