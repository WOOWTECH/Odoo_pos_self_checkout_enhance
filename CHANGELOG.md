# Changelog | 更新日誌

All notable changes to this project will be documented in this file.

此專案的所有重要變更都將記錄在此檔案中。

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [18.0.1.0.0] - 2026-01-28

### Added | 新增
- **Continue Ordering Button | 繼續點餐按鈕**
  - Added "繼續點餐" button on landing page
  - Allows customers to add items to existing unpaid orders
  - 首頁新增「繼續點餐」按鈕，允許顧客在現有未付款訂單上繼續添加餐點

- **Pay Per Order Mode | 整單結帳模式**
  - Enabled Enterprise "Pay per Order" feature for Community version
  - Customers can submit multiple orders and pay at the end
  - Checkout from "My Orders" page with accumulated total
  - 啟用 Enterprise 版的「整單結帳」功能於 Community 版
  - 顧客可多次點餐，最後統一從「我的訂單」頁面結帳

- **Friendly Payment Page | 友善付款頁面**
  - Order items grouped by ordering session (第1次點餐, 第2次點餐...)
  - Shows current session added amount (本次加點)
  - Friendly thank-you messages: "感謝您的點餐！餐點準備中，請稍候～"
  - FontAwesome icons for visual enhancement
  - "回到主頁" (Back to Home) button for navigation
  - 訂單明細以點餐次序分組顯示
  - 顯示本次加點金額
  - 親切的感謝提示語與圖示
  - 新增「回到主頁」導航按鈕

- **Payment Success Page | 付款成功頁面**
  - New payment success confirmation page
  - Shows order reference and payment amount
  - "再點一份" (Order Again) button
  - 新增付款成功確認頁面
  - 顯示訂單編號與付款金額
  - 「再點一份」按鈕

- **Chinese Translation | 中文翻譯**
  - Full Traditional Chinese (zh_TW) translation
  - 完整繁體中文翻譯支援

### Changed | 變更
- **Confirmation Page | 確認頁面**
  - Modified confirmation page for different payment modes
  - Pay per Order: Shows "返回首頁" and "我的訂單" buttons
  - Pay per Meal: Shows "前往付款" button
  - 根據不同付款模式修改確認頁面
  - 整單結帳：顯示「返回首頁」和「我的訂單」按鈕
  - 單餐結帳：顯示「前往付款」按鈕

### Removed | 移除
- **Cancel Button | 取消按鈕**
  - Removed cancel button from cart page after order submission
  - Prevents customers from canceling orders themselves
  - Staff can still cancel from POS backend
  - 訂單送出後移除購物車頁面的取消按鈕
  - 防止顧客自行取消訂單
  - 員工仍可從 POS 後台取消

- **Tax Display | 稅金顯示**
  - Removed tax information from cart page
  - Shows only total amount for simplified interface
  - 移除購物車頁面的稅金資訊
  - 僅顯示總計金額，簡化顧客介面

### Fixed | 修復
- **Payment Success Page Routing | 付款成功頁面路由**
  - Fixed routing error: changed route name from "landing" to "default"
  - 修復路由錯誤：將路由名稱從 "landing" 改為 "default"

## Technical Notes | 技術備註

### Dependencies | 相依模組
- `pos_self_order` (Odoo built-in)

### Compatibility | 相容性
- Odoo 18.0 Community Edition
- Odoo 18.0 Enterprise Edition

### File Changes | 檔案變更
```
pos_self_order_enhancement/
├── __manifest__.py                    # Module manifest
├── models/pos_config.py               # POS config extension
├── controllers/debug_controller.py    # Debug endpoints
├── i18n/zh_TW.po                      # Chinese translation
└── static/src/app/
    ├── self_order_index.js            # Router extension
    ├── self_order_index.xml           # Router template
    └── pages/
        ├── cart_page/                 # Cart page (tax removal)
        ├── confirmation_page/         # Confirmation page mods
        ├── landing_page/              # Landing page (continue ordering)
        ├── order_history_page/        # Order history (checkout)
        ├── payment_page/              # Payment page (grouped orders)
        └── payment_success_page/      # Payment success page
```
