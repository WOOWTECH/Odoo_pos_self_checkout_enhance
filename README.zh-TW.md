# POS 自助點餐增強模組

Odoo 18 模組，強化並延伸內建的 POS 自助點餐 (`pos_self_order`)，以應對餐廳真實營運場景。

> English version: see [`README.md`](README.md).

## 功能特色

### 點餐體驗
- **顧客無法取消訂單** — 客人送單後，前台介面隱藏「取消」按鈕；員工仍可從 POS 後台取消。
- **繼續點餐** — 首頁提供「Continue Ordering」按鈕，客人可在既有未結帳訂單上繼續加點，不必重新開單。
- **整單付款（Community 版）** — 啟用企業版專屬的「Pay per Order」功能。客人多次送單後，從「我的訂單」一次結清全部。
- **外帶現場結帳（選用）** — 新增 `pos.config` 設定，允許自助點餐外帶客人選擇現場結帳；內用客人一律同時看到兩種選項。

### 付款閘門
- 所有自助點餐流程（meal / each）套用**付款閘門**：訂單以 `draft` 狀態建立且 `self_order_payment_status='pending_online'`，付款確認前不會送到 KDS 或印表機。
- Meal 模式：付款完成後自動 fire 廚房單。
- Each 模式：付款完成後由員工手動 fire（透過 Hold & Fire 機制）。

### 廚房出單（Network ESC/POS）
- 新增 **`network_escpos`** 印表機類型：直接以 raw-TCP 送資料到網路型 ESC/POS 熱感印表機，不需要 IoT Box。
- 選用 **Cloud Relay**（本 repo 內附 Home Assistant add-on `ha-addon-escpos-print-proxy/`）：讓遠端 Odoo 可以印到店內印表機。設定 Cloudflare tunnel URL 與 API key，add-on 處理 LAN 內部連線。
- **伺服器端 Pillow 渲染**：Cloud Relay 印表機的廚房單直接在 Odoo 後端渲染成 JPEG。避開瀏覽器 `html-to-image` 在中日韓字型嵌入與背景 tab throttling 下產生空白收據的問題。
- **不會重複列印**：伺服器端路徑與前端 fallback（瀏覽器 `sendOrderInPreparation`）透過 `skip_printer_ids` 交接，Cloud Relay 印表機不會收到重複工單；Local-TCP 印表機仍走前端路徑保持相容。
- 廚房單內容：訂單編號、出單時間（`YYYY-MM-DD HH:MM:SS`）、桌位（樓層 + 桌號）、外帶／Uber 外送標籤 + 地址 + 騎手、每一品項 + 客人備註（`customer_note`，自 kiosk）+ 員工備註（`note`）、訂單一般備註。
- Per-printer 設定：`escpos_printer_ip`、`escpos_paper_width`（80mm / 58mm）、`escpos_print_copies`（1–10）、`escpos_proxy_url`、`escpos_proxy_api_key`、`escpos_printer_label`。
- 後台「列印測試頁」按鈕：端對端測試連線與份數設定。

### 廚房顯示螢幕（KDS）
- 瀏覽器版 KDS，公開分享 URL + 可重生 access token（Configuration → Point of Sale → 「Kitchen Display Screen (KDS)」）。
- WebSocket 即時更新，支援按分類的 Hold & Fire，讓出餐順序可以在出餐口排序。
- 重做 / SEND-BACK 流程：品項被要求重做時，重印廚房單會以 `SEND BACK · <原因>` 標題取代 `New`。

### 付款整合
- 相容 `pos_online_payment` 及 Odoo Payment 模組。
- 付款頁面版型優化：付款方式標籤不斷行、金流商 icon 固定 48x48、Cancel 按鈕與 Pay 按鈕同尺寸；在 kiosk / 手機寬度下都有清晰的網格。
- 付款確認頁提供「Return to Ordering」快速回點餐頁。

### Uber Direct 外送（每個 config 可獨立啟用）
- OAuth 2.0 對接 Uber Direct API，token 自動更新。
- 付款完成且訂單有配送地址時，自動叫車。
- 廚房單顯示 `*** 外送 ***`、送餐地址（自動兩行截斷）、騎手姓名（配對後）。

## 系統需求

- Odoo 18.0（Community 或 Enterprise）
- `pos_self_order`、`pos_restaurant`（Odoo 內建）
- 選用：`pos_online_payment` 以啟用線上付款
- 選用：Home Assistant Supervisor + Cloudflare tunnel（Cloud Relay 用，`ha-addon-escpos-print-proxy/`）

## 安裝方式

1. 複製到 Odoo `addons` 目錄：
   ```bash
   git clone https://github.com/WOOWTECH/Odoo_pos_self_checkout_enhance.git \
       pos_self_order_enhancement
   ```
2. 在 Odoo：**應用程式 → 更新應用程式清單** → 搜尋「POS Self Order Enhancement」→ **安裝**。

## 設定

大部分功能安裝後即用。以下是可能會想調整的位置：

| 位置 | 項目 | 預設 |
|------|------|------|
| **設定 → 銷售點 → 您的 POS** | 「Kitchen Display Screen (KDS)」 | 關閉 |
| **設定 → 銷售點 → 您的 POS** | 「Takeaway Counter Payment」（外帶允許現場結帳） | 關閉（外帶僅限線上付款） |
| **設定 → 印表機 → 您的印表機** | `printer_type = "Use a network ESC/POS printer"` | — |
| **設定 → 印表機 → 您的印表機** | `Print Copies`（份數）、`Paper Width`、`Cloud Relay URL`、`API Key`、`Printer Label` | 1 份、80mm |

## 授權條款

LGPL-3

## 作者

[WOOWTECH](https://www.woowtech.io)
