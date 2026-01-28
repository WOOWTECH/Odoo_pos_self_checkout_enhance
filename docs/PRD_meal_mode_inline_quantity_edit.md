# PRD: 餐點結模式 - 購物車頁面內直接增減數量

## 概述

**功能名稱**: Meal Mode Inline Quantity Edit (餐點結購物車內建數量調整)

**目標**: 讓客戶在餐點結 (pay_after='meal') 模式的購物車頁面直接增減商品數量，無需跳轉到其他頁面。

**優先級**: 高

**預估工時**: 2-4 小時

---

## 問題陳述

### 現況
- 餐點結模式下，客戶在購物車頁面無法直接修改已點餐品的數量
- 之前嘗試實作跳轉到產品頁面編輯，但導航流程複雜且容易出錯
- 客戶體驗不佳，需要多次點擊和頁面跳轉

### 期望
- 客戶可以直接在購物車頁面增減數量
- 操作簡單直覺，類似常見電商購物車
- 數量減到 0 時自動刪除該品項

---

## 功能需求

### FR-1: 顯示 +/- 按鈕
- **條件**: 僅在餐點結模式 (`self_ordering_pay_after === 'meal'`) 顯示
- **位置**: 每個訂單項目的數量旁邊
- **樣式**:
  - 減號 (-) 按鈕在左
  - 數量顯示在中間
  - 加號 (+) 按鈕在右

### FR-2: 增加數量
- 點擊 + 按鈕，數量 +1
- 更新訂單行的數量
- 同步更新小計金額

### FR-3: 減少數量
- 點擊 - 按鈕，數量 -1
- 當數量 > 1 時：正常減少
- 當數量 = 1 時：減少後刪除該品項

### FR-4: 刪除品項
- 當數量減至 0 時，自動從訂單中移除該行
- 顯示視覺反饋（品項消失）

### FR-5: 伺服器同步
- 每次數量變更後，標記行為 dirty
- 系統自動同步到伺服器

---

## UI/UX 設計

### 佈局參考

```
┌─────────────────────────────────────────┐
│  [圖片]  冰茶 選項                       │
│          $100                           │
│          [-]  3  [+]                    │
├─────────────────────────────────────────┤
│  [圖片]  咖啡                            │
│          $80                            │
│          [-]  1  [+]                    │
└─────────────────────────────────────────┘
```

### 按鈕樣式
- 按鈕大小: 適合手指點擊 (min 44x44px)
- 顏色:
  - (+) 按鈕: `btn-outline-success` 或 `btn-success`
  - (-) 按鈕: `btn-outline-danger` 或 `btn-secondary`
- 數量文字: 粗體，居中顯示

### 互動反饋
- 點擊按鈕時有視覺反饋
- 數量變更時平滑更新
- 刪除品項時可考慮淡出動畫

---

## 技術規格

### 修改檔案

1. **cart_page.xml**
   - 在每個訂單行添加 +/- 按鈕
   - 使用條件 `t-if` 控制僅在餐點結模式顯示

2. **cart_page.js**
   - 新增 `increaseQuantity(line)` 方法
   - 新增 `decreaseQuantity(line)` 方法
   - 處理數量為 0 時的刪除邏輯

### 關鍵方法

```javascript
// 增加數量
increaseQuantity(line) {
    line.qty += 1;
    line.setDirty();
}

// 減少數量
decreaseQuantity(line) {
    if (line.qty > 1) {
        line.qty -= 1;
        line.setDirty();
    } else {
        // 數量為 1，刪除品項
        this.selfOrder.removeLine(line);
    }
}
```

### XML 結構參考

```xml
<div t-if="selfOrder.config.self_ordering_pay_after === 'meal'"
     class="d-flex align-items-center">
    <button class="btn btn-sm btn-outline-secondary"
            t-on-click="() => this.decreaseQuantity(line)">
        <i class="fa fa-minus"></i>
    </button>
    <span class="mx-2 fw-bold" t-esc="line.qty"/>
    <button class="btn btn-sm btn-outline-success"
            t-on-click="() => this.increaseQuantity(line)">
        <i class="fa fa-plus"></i>
    </button>
</div>
```

---

## 測試案例

### TC-1: 增加數量
1. 進入餐點結模式購物車
2. 點擊 + 按鈕
3. **預期**: 數量 +1，金額更新

### TC-2: 減少數量 (數量 > 1)
1. 品項數量為 3
2. 點擊 - 按鈕
3. **預期**: 數量變為 2，金額更新

### TC-3: 刪除品項 (數量 = 1)
1. 品項數量為 1
2. 點擊 - 按鈕
3. **預期**: 品項從列表中移除

### TC-4: 僅餐點結模式顯示
1. 切換到整單結模式
2. **預期**: 不顯示 +/- 按鈕

### TC-5: 伺服器同步
1. 修改數量
2. 重新載入頁面
3. **預期**: 數量保持修改後的值

---

## 排除範圍

- 不支援在整單結 (pay_after='each') 模式使用此功能
- 不支援修改產品選項/備註（僅數量）
- 不支援批次修改多個品項

---

## 風險與緩解

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| 同步失敗 | 數量不一致 | 顯示錯誤提示，保留本地狀態 |
| 快速連點 | 數量計算錯誤 | 防抖處理或禁用按鈕直到同步完成 |
| 已出餐品項被刪除 | 廚房混亂 | 考慮添加確認對話框（可選） |

---

## 成功指標

- 客戶可在 2 秒內完成數量調整
- 無頁面跳轉
- 數量變更即時反映在訂單總額

---

## 附錄

### 相關檔案路徑
- `addons/pos_self_order_enhancement/static/src/app/pages/cart_page/cart_page.js`
- `addons/pos_self_order_enhancement/static/src/app/pages/cart_page/cart_page.xml`

### 參考截圖
用戶提供的購物車頁面截圖顯示當前佈局，+/- 按鈕應放置在每個品項的數量位置。
