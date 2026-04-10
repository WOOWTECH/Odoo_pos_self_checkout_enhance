{
    "name": "POS Self Order Enhancement",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Enhanced POS self-ordering with continue ordering, pay per order mode, and friendly UI",
    "description": """
POS Self Order Enhancement | POS 自助點餐增強模組
=================================================

增強 Odoo POS 自助點餐系統功能，為餐廳提供更完善的顧客自助點餐體驗。

Enhanced Odoo POS self-ordering system for restaurants.

Features | 功能特色
--------------------

1. **Remove Cancel Button | 移除取消按鈕**
   - Prevents customer cancellation after order submission
   - Staff can still cancel from POS backend
   - 訂單送出後顧客無法自行取消，員工仍可從後台取消

2. **Continue Ordering | 繼續點餐**
   - "Continue Ordering" button on landing page
   - Add items to existing unpaid orders
   - 首頁「繼續點餐」按鈕，可在現有訂單上繼續添加餐點

3. **Pay Per Order Mode | 整單結帳模式**
   - Enterprise feature enabled for Community
   - Multiple orders, pay at the end
   - 啟用 Enterprise 版功能，多次點餐最後統一結帳

4. **Friendly Payment Page | 友善付款頁面**
   - Orders grouped by session (第1次點餐, 第2次點餐...)
   - Shows current session amount (本次加點)
   - Friendly messages and icons
   - 訂單依點餐次序分組，顯示本次加點金額

5. **Hide Tax Display | 隱藏稅金顯示**
   - Removed tax from cart page
   - Simplified customer interface
   - 移除稅金資訊，簡化介面

6. **Kitchen Display Screen (KDS) | 廚房顯示螢幕**
   - Real-time kitchen order display on any browser
   - Item-level strikethrough, bump, recall, all-day view
   - Audio chime on new orders, timer color escalation
   - Token-based auth, no login required
   - 即時廚房訂單顯示，支援任何瀏覽器
   - 品項劃線、完成出餐、召回、總覽功能

7. **ESC/POS Network Printer | 網路出單機支援**
   - Use any generic ESC/POS network printer as preparation printer
   - No IoT Box or Epson printer required
   - Lightweight print proxy server included
   - 支援任何 ESC/POS 網路出單機作為備餐印表機
   - 不需要 IoT Box 或 Epson 印表機

Technical Details | 技術細節
----------------------------
- OWL (Odoo Web Library) components
- JavaScript ES6+ with patch system
- XML template inheritance
- Full zh_TW translation

GitHub: https://github.com/WOOWTECH/Odoo_pos_self_checkout_enhance
    """,
    "author": "WoowTech",
    "website": "https://aiot.woowtech.io/",
    "license": "LGPL-3",
    "depends": ["pos_self_order", "payment"],
    "data": [
        "views/payment_templates.xml",
        "views/kds_templates.xml",
        "views/pos_config_view.xml",
        "views/pos_dashboard_kds.xml",
        "views/pos_printer_views.xml",
        "views/pos_category_view.xml",
        "views/pos_config_einvoice_view.xml",
    ],
    "assets": {
        "pos_self_order.assets": [
            "pos_self_order_enhancement/static/src/app/**/*",
            "pos_self_order_enhancement/static/src/css/**/*",
        ],
        "point_of_sale._assets_pos": [
            "pos_self_order_enhancement/static/src/printer/**/*",
            "pos_self_order_enhancement/static/src/pos/**/*",
        ],
        "web.assets_backend": [
            "pos_self_order_enhancement/static/src/fields/**/*",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
