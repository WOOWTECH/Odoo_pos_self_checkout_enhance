/** @odoo-module **/

/**
 * When a portal user launches the POS UI (see controllers/pos_portal.py),
 * the backend injects `portal_pos_mode: true` into session_info. In that
 * case, the "close POS" / "Backend" button must not redirect to the
 * backend action (portal users can't access it); it should return the
 * user to their portal POS shop picker page instead.
 */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

patch(PosStore.prototype, {
    redirectToBackend() {
        if (session.portal_pos_mode) {
            window.location = "/my/pos";
            return;
        }
        return super.redirectToBackend(...arguments);
    },
});
