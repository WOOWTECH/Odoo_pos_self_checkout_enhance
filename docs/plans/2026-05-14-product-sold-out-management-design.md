# 產品售完管理功能設計

**日期**: 2026-05-14
**狀態**: Draft

## 需求

仿照 UberEats 商家後台，在 POS Actions 彈窗中新增「產品售完管理」按鈕，讓營業點操作者可以快速切換產品的售完狀態。

### 核心行為

- 沿用現有 `is_sold_out` Boolean 欄位（不改資料模型）
- 售完的產品在 **POS 收銀員端** 和 **自助點餐前端** 都不可點選（反灰）
- POS Session 關閉時自動重置所有售完狀態
- 狀態切換後即時透過 bus 通知自助點餐前端

## 架構

### 1. Actions 彈窗新增按鈕

**檔案**: `static/src/pos/control_buttons_sold_out.js` + `.xml`

- Patch `ControlButtons` component，新增 `onClickSoldOutManagement()` 方法
- XML 繼承 `point_of_sale.ControlButtons`，在 `showRemainingButtons` 區塊的 Cancel Order 按鈕**前面**插入新按鈕
- 按鈕文字：「產品售完管理」，icon: `fa-ban`

### 2. SoldOutManagementPopup（新 OWL Component）

**檔案**: `static/src/pos/sold_out_popup.js` + `.xml`

**UI 結構**:
- Dialog 標題：「產品售完管理」
- 搜尋框：依產品名稱篩選
- 分頁 Tab：所有品項 / 已售完(N)
- 產品列表：每行 = 圖片 + 名稱 + toggle 開關
- 依 POS category 分組（可選）

**Toggle 操作**:
- 點擊 toggle 即時呼叫 `pos.data.write("product.product", [id], { is_sold_out: value })`
- 現有 `product_product.py` 的 `write()` override 已處理 bus 通知

### 3. POS 收銀員端 — 產品卡片反灰

**檔案**: `static/src/pos/product_card.xml`

- 現在：售完產品底部顯示紅色 banner
- 改為：整張卡片加灰色遮罩 + `pointer-events: none` + 中央「售完」文字
- 移除舊的 "available for staff order" 文字

### 4. POS 收銀員端 — addProductToOrder guard

**檔案**: `static/src/pos/pos_store.js`

- 在 `addProductToOrder` patch 中加入 `is_sold_out` 檢查
- 若 `product.is_sold_out === true`，顯示 notification 並 return

### 5. 自助點餐前端 — 產品卡片反灰

**檔案**: `static/src/app/product_card.js` + `static/src/app/product_card.xml`

- `selectProduct()` 已有 return early guard（不改）
- XML：售完產品整張卡片加 `opacity: 0.5; pointer-events: none`
- 保留紅色「售完」badge

### 6. Session 關閉時重置

**檔案**: `models/pos_session.py`

- Override `_post_close_session()` 或 `action_pos_session_closing_control()`
- 找出該 config 可售產品中 `is_sold_out=True` 的，全部重置為 `False`
- 重置後透過 bus 通知前端

## 檔案清單

| 檔案 | 動作 |
|------|------|
| `static/src/pos/control_buttons_sold_out.js` | 新增 |
| `static/src/pos/control_buttons_sold_out.xml` | 新增 |
| `static/src/pos/sold_out_popup.js` | 新增 |
| `static/src/pos/sold_out_popup.xml` | 新增 |
| `static/src/pos/product_card.xml` | 修改 |
| `static/src/pos/pos_store.js` | 修改 |
| `static/src/app/product_card.xml` | 修改 |
| `static/src/app/product_card.js` | 確認（已有 guard） |
| `models/pos_session.py` | 修改 |
| `__manifest__.py` | 修改（新增 assets） |
