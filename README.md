# POS Self Order Enhancement for Odoo 18

![Odoo Version](https://img.shields.io/badge/Odoo-18.0-blue)
![License](https://img.shields.io/badge/License-LGPL--3-green)

增強 Odoo POS 自助點餐系統功能，為餐廳提供更完善的顧客自助點餐體驗。

Enhanced Odoo POS self-ordering system for restaurants, providing a better customer self-service ordering experience.

## 功能特色 | Features

### 1. 移除取消按鈕 | Remove Cancel Button
- 訂單送出後，顧客無法自行取消訂單
- 員工仍可從 POS 後台取消訂單
- After order submission, customers cannot cancel orders themselves
- Staff can still cancel orders from POS backend

### 2. 繼續點餐功能 | Continue Ordering
- 首頁新增「繼續點餐」按鈕
- 顧客可在現有訂單上繼續添加餐點
- Added "Continue Ordering" button on landing page
- Customers can add items to existing orders

### 3. 整單結帳模式 | Pay Per Order Mode
- 啟用 Enterprise 版的「整單結帳」功能於 Community 版
- 顧客可多次點餐，最後統一結帳
- 從「我的訂單」頁面進行結帳
- Enable Enterprise "Pay per Order" feature for Community version
- Customers can submit multiple orders and pay at the end
- Checkout from "My Orders" page

### 4. 友善付款頁面 | Friendly Payment Page
- 以點餐次序分組顯示訂單明細（第1次點餐、第2次點餐...）
- 顯示本次加點金額
- 親切的感謝提示語與圖示
- 「回到主頁」導航按鈕
- Order items grouped by ordering session
- Shows current session added amount
- Friendly thank-you messages with icons
- "Back to Home" navigation button

### 5. 隱藏稅金顯示 | Hide Tax Display
- 購物車頁面移除稅金資訊顯示
- 僅顯示總計金額，簡化顧客介面
- Removed tax information from cart page
- Shows only total amount for simplified customer interface

## 安裝說明 | Installation

### 前置需求 | Prerequisites
- Odoo 18.0
- `pos_self_order` 模組（Odoo 內建）

### 安裝步驟 | Installation Steps

1. **下載模組 | Download Module**
   ```bash
   git clone https://github.com/WOOWTECH/Odoo_pos_self_checkout_enhance.git
   ```

2. **複製到 Odoo addons 目錄 | Copy to Odoo addons directory**
   ```bash
   cp -r Odoo_pos_self_checkout_enhance/addons/pos_self_order_enhancement /path/to/odoo/addons/
   ```

3. **重啟 Odoo 服務 | Restart Odoo service**
   ```bash
   sudo systemctl restart odoo
   # 或 Docker 環境 | or Docker environment
   docker restart odoo
   ```

4. **更新應用程式列表 | Update Apps List**
   - 前往 設定 > 開發者模式 > 更新應用程式列表
   - Go to Settings > Developer Mode > Update Apps List

5. **安裝模組 | Install Module**
   - 搜尋 "POS Self Order Enhancement"
   - 點擊安裝
   - Search for "POS Self Order Enhancement"
   - Click Install

### Docker 安裝 | Docker Installation

```bash
# 複製模組到容器 | Copy module to container
docker cp pos_self_order_enhancement odoo:/mnt/extra-addons/

# 升級模組 | Upgrade module
docker exec odoo odoo -d <database> -u pos_self_order_enhancement --stop-after-init

# 重啟容器 | Restart container
docker restart odoo
```

## 使用說明 | Usage

### 存取自助點餐頁面 | Access Self-Order Page

```
http://your-odoo-server/pos-self/<config_id>/products?access_token=<token>
```

- `config_id`: POS 設定 ID
- `access_token`: 從 POS 設定取得的存取金鑰

### 取得 Access Token | Get Access Token

```sql
SELECT id, name, access_token FROM pos_config;
```

## 模組結構 | Module Structure

```
pos_self_order_enhancement/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── debug_controller.py
├── i18n/
│   ├── pos_self_order_enhancement.pot
│   └── zh_TW.po
├── models/
│   ├── __init__.py
│   └── pos_config.py
└── static/
    └── src/
        ├── app/
        │   ├── self_order_index.js
        │   ├── self_order_index.xml
        │   └── pages/
        │       ├── cart_page/
        │       │   ├── cart_page.js
        │       │   └── cart_page.xml
        │       ├── confirmation_page/
        │       │   ├── confirmation_page.js
        │       │   └── confirmation_page.xml
        │       ├── landing_page/
        │       │   ├── landing_page.js
        │       │   └── landing_page.xml
        │       ├── order_history_page/
        │       │   ├── order_history_page.js
        │       │   └── order_history_page.xml
        │       ├── payment_page/
        │       │   ├── payment_page.js
        │       │   └── payment_page.xml
        │       └── payment_success_page/
        │           ├── payment_success_page.js
        │           └── payment_success_page.xml
        └── fields/
            └── upgrade_selection_field.js
```

## 技術細節 | Technical Details

### 使用技術 | Technologies Used
- **OWL (Odoo Web Library)**: Odoo 18 前端框架
- **JavaScript ES6+**: 模組擴展與功能增強
- **XML Template Inheritance**: Odoo 模板繼承系統
- **Python 3.10+**: 後端模型與控制器

### 擴展方式 | Extension Methods
- 使用 `@web/core/utils/patch` 擴展原有組件
- XML `t-inherit` 模板繼承
- 路由擴展添加自訂頁面

## 授權 | License

此模組採用 [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.html) 授權。

This module is licensed under [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.html).

## 作者 | Author

**WoowTech**
- Website: https://www.woowtech.com
- Email: woowtech@designsmart.com.tw

## 更新日誌 | Changelog

詳見 [CHANGELOG.md](CHANGELOG.md)

See [CHANGELOG.md](CHANGELOG.md) for details.
