# POS 自助點餐增強模組

Odoo 18 模組，提升餐廳及零售業的 POS 自助點餐體驗。

## 功能特色

- **移除取消按鈕** - 防止顧客在送單後取消訂單（員工仍可從 POS 後台取消）
- **繼續點餐** - 允許顧客從首頁將商品加入現有訂單
- **整單付款模式** - 在社群版啟用企業版專屬的「整單付款」功能
  - 顧客可提交多筆訂單
  - 從「我的訂單」頁面一次結帳所有訂單

## 系統需求

- Odoo 18.0
- `pos_self_order` 模組（Odoo 內建）

## 安裝方式

1. 將此儲存庫複製到您的 Odoo addons 目錄：
   ```bash
   git clone https://github.com/WOOWTECH/Odoo_pos_self_checkout_enhance.git pos_self_order_enhancement
   ```

2. 在 Odoo 中更新應用程式清單：
   - 前往「應用程式」選單
   - 點擊「更新應用程式清單」

3. 安裝模組：
   - 搜尋「POS Self Order Enhancement」
   - 點擊安裝

## 設定

無需額外設定。模組將自動：
- 從顧客自助點餐畫面移除取消按鈕
- 在首頁新增「繼續點餐」選項
- 啟用「整單付款」付款模式選項

## 授權條款

LGPL-3

## 作者

[WoowTech](https://www.woowtech.com)
