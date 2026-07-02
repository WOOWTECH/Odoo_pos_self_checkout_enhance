/** @odoo-module */

import { selfOrderIndex } from "@pos_self_order/app/self_order_index";
import { PaymentPage } from "./pages/payment_page/payment_page";
import { PaymentSuccessPage } from "./pages/payment_success_page/payment_success_page";
import { DeliveryOptionPage } from "./pages/delivery_option_page/delivery_option_page";
import { DeliveryAddressPage } from "./pages/delivery_address_page/delivery_address_page";
import { DeliveryQuotePage } from "./pages/delivery_quote_page/delivery_quote_page";

// Import patches (side-effect only imports)
import "@pos_self_order_enhancement/app/self_order_service";
import "@pos_self_order_enhancement/app/components/order_widget/order_widget";

/**
 * Override selfOrderIndex components to register custom page components.
 * This makes PaymentPage, PaymentSuccessPage, and the delivery flow pages
 * available in the router.
 *
 * Note: We override the existing PaymentPage with our custom implementation
 * that supports both online payment and counter payment for mobile mode.
 */

// Directly override the static components property
selfOrderIndex.components = {
    ...selfOrderIndex.components,
    PaymentPage,
    PaymentSuccessPage,
    DeliveryOptionPage,
    DeliveryAddressPage,
    DeliveryQuotePage,
};
