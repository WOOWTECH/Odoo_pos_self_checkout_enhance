/** @odoo-module **/

/**
 * Override the LoginScreen "Backend" button behaviour for portal users.
 *
 * When module_pos_hr is enabled, pos_hr patches LoginScreen.clickBack()
 * to require selecting the cashier whose user_id matches the logged-in
 * Odoo user before navigating to the backend. For portal users this
 * makes no sense — the logged-in user is actually a proxy user (e.g.
 * Marc Demo), and the portal user should simply be able to go back to
 * their portal page without having to pick any cashier.
 *
 * This patch:
 * - In portal mode: skips the cashier-selection gate and calls
 *   closePos() directly (which triggers redirectToBackend → /my/pos).
 * - Changes the button label from "Backend" to "返回" (Return).
 */

import { LoginScreen } from "@point_of_sale/app/screens/login_screen/login_screen";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

patch(LoginScreen.prototype, {
    clickBack() {
        if (session.portal_pos_mode) {
            // Portal user — bypass pos_hr's cashier verification and
            // redirect straight to the portal POS picker page.
            // We call redirectToBackend() directly instead of closePos()
            // because closePos() may silently fail (e.g. if order sync
            // returns false) and never redirect.
            this.pos.redirectToBackend();
            return;
        }
        return super.clickBack(...arguments);
    },

    get backBtnName() {
        if (session.portal_pos_mode) {
            return "返回";
        }
        return super.backBtnName;
    },
});
