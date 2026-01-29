# POS Self Order Enhancement

Odoo 18 module that enhances the POS self-ordering experience for restaurants and retail.

## Features

- **Remove Cancel Button** - Prevents customers from cancelling orders after submission (staff can still cancel from POS backend)
- **Continue Ordering** - Allows customers to add items to existing orders from the landing page
- **Pay per Order Mode** - Enables Enterprise-only "Pay per Order" feature for Community version
  - Customers can submit multiple orders
  - Pay all orders at once from "My Orders" page

## Requirements

- Odoo 18.0
- `pos_self_order` module (included in Odoo)

## Installation

1. Clone this repository to your Odoo addons directory:
   ```bash
   git clone https://github.com/WOOWTECH/Odoo_pos_self_checkout_enhance.git pos_self_order_enhancement
   ```

2. Update the apps list in Odoo:
   - Go to Apps menu
   - Click "Update Apps List"

3. Install the module:
   - Search for "POS Self Order Enhancement"
   - Click Install

## Configuration

No additional configuration required. The module automatically:
- Removes the cancel button from customer-facing self-order screens
- Adds "Continue Ordering" option on the landing page
- Enables "Pay per Order" payment mode selection

## License

LGPL-3

## Author

[WoowTech](https://www.woowtech.com)
