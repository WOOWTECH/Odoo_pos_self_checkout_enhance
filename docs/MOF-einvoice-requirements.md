# Taiwan Electronic Invoice (電子發票證明聯) Format Requirements
# 台灣電子發票證明聯格式規範

Reference: 財政部「電子發票實施作業要點」/ MOF "Electronic Invoice Implementation Guidelines"

---

## 1. Paper Specifications / 紙張規格

| Item / 項目 | Requirement / 規範 |
|---|---|
| Paper type / 紙張類型 | Thermal paper (感熱紙) |
| Paper width / 紙張寬度 | **57mm** (standard for POS) or 80mm |
| Pixel width at 203 DPI | 57mm → **455px**, 80mm → 640px |
| Print resolution / 列印解析度 | 203 DPI (standard ESC/POS) |

---

## 2. Required Fields & Layout / 必要欄位與排版

Top-to-bottom order as required by MOF:

### Section A: Header / 表頭

| # | Field / 欄位 | Format / 格式 | Example / 範例 |
|---|---|---|---|
| 1 | **Title / 標題** | `電子發票證明聯` centered, large bold | 電子發票證明聯 |
| 2 | **Invoice Period / 發票期別** | ROC year + bimonthly period | 115年03-04月 |
| 3 | **Invoice Number / 發票號碼** | 2 letters + 8 digits, formatted `XX-XXXXXXXX` | ZF-91471261 |
| 4 | **Date & Time / 日期時間** | ROC calendar: `YYY/MM/DD HH:MM:SS` | 115/04/13 16:56:00 |
| 5 | **Random Code / 隨機碼** | 4-digit random number | 0930 |
| 6 | **Seller Tax ID / 賣方統編** | 8-digit unified business number | 53538851 |
| 7 | **Buyer Tax ID / 買方統編** | 8-digit (B2B only, omit for B2C) | 12345678 |

### Section B: Machine-Readable Codes / 機器可讀條碼

| # | Code Type / 條碼類型 | Specification / 規格 |
|---|---|---|
| 8 | **Left QR Code / 左方QR碼** | Contains: invoice number, date, random code, sales amount, tax amount, buyer ID, seller ID, AES verification code, item count. See Section 4 below. |
| 9 | **Right QR Code / 右方QR碼** | Contains: item details (name, quantity, unit price). Encoded in UTF-8. See Section 4 below. |
| 10 | **Barcode / 一維條碼** | Code 39 format: `{ROC_period}{invoice_number}{random_code}` e.g., `11504ZF914712610930` |

### Section C: Transaction Details / 交易明細

| # | Field / 欄位 | Description / 說明 |
|---|---|---|
| 11 | **Item Name / 品名** | Product name (max 30 chars per MOF spec) |
| 12 | **Quantity / 數量** | Integer quantity |
| 13 | **Unit Price / 單價** | Price per unit (tax-inclusive) |
| 14 | **Amount / 金額** | Line total (qty × unit price) |

### Section D: Tax Summary / 稅額彙總

| # | Field / 欄位 | Calculation / 計算方式 |
|---|---|---|
| 15 | **Sales Amount / 銷售額** | Total excluding tax: `總計 / 1.05` (rounded) |
| 16 | **Tax Amount / 稅額** | 5% VAT: `總計 - 銷售額` |
| 17 | **Total / 總計** | Grand total (tax-inclusive) |

### Section E: Footer / 頁尾

| # | Field / 欄位 | Content / 內容 |
|---|---|---|
| 18 | **Return Notice / 退貨提示** | `退貨時請攜帶本證明聯正本` |

---

## 3. Invoice Period Rules / 發票期別規則

Taiwan invoices use bimonthly periods based on the ROC calendar (民國曆):

| Months / 月份 | Period / 期別 | Example (2026) / 範例 |
|---|---|---|
| January–February | 01-02月 | 115年01-02月 |
| March–April | 03-04月 | 115年03-04月 |
| May–June | 05-06月 | 115年05-06月 |
| July–August | 07-08月 | 115年07-08月 |
| September–October | 09-10月 | 115年09-10月 |
| November–December | 11-12月 | 115年11-12月 |

ROC Year = Western Year - 1911 (e.g., 2026 → 115)

---

## 4. QR Code Data Format / QR碼資料格式

### Left QR Code / 左方QR碼

Fixed 77-character header + AES encrypted verification:

```
Position  Field                    Length  Example
1-10      Invoice Number           10      ZF91471261
11-17     Invoice Date (YYYMMDD)   7       1150413
18-21     Random Code              4       0930
22-29     Sales Amount (hex, 8ch)  8       00000CE4
30-37     Total Amount (hex, 8ch)  8       00000D3A
38-47     Buyer Tax ID             10      0000000000
48-55     Seller Tax ID            8       53538851
56-95     AES Verification         40      (encrypted hash)
96-...    :**********:             varies  :item_count:item_count:...
          Item summary                     :1:1:1:Bacon Burger:1:220:
```

### Right QR Code / 右方QR碼

Contains `**` (placeholder) or detailed item list for invoices with many items.

### Barcode (Code 39) / 一維條碼

Format: `{period_code}{invoice_number}{random_code}`

```
Period code: YYMM (ROC year 2 digits + month 2 digits)
Example: 11504ZF914712610930
         ↑↑↑↑↑ ↑↑↑↑↑↑↑↑↑↑ ↑↑↑↑
         period invoice_no  random
```

---

## 5. Carrier Types / 載具類型

| Type / 類型 | Code | Print Flag | Description / 說明 |
|---|---|---|---|
| **列印 (Print)** | — | Print=1 | Physical paper invoice printed |
| **手機條碼 (Mobile Barcode)** | 3 | Print=0 | Stored on mobile barcode carrier (`/XXXXXXX`) |
| **捐贈 (Donation)** | — | Print=0 | Donated to charity via Love Code |
| **統編 B2B** | — | Print=1 | Business invoice with buyer tax ID |

Only `列印` and `統編` modes require physical printing of the 電子發票證明聯.

---

## 6. Tax Calculation / 稅額計算

Taiwan standard VAT rate: **5%** (營業稅率 5%)

For tax-inclusive pricing (含稅):
- **Total (總計)** = displayed price (what customer pays)
- **Sales Amount (銷售額)** = `round(Total / 1.05)`
- **Tax Amount (稅額)** = `Total - Sales Amount`

Example: Total = $220
- Sales = round(220 / 1.05) = round(209.52) = $210
- Tax = 220 - 210 = $10

---

## 7. Visual Layout Reference / 版面參考

```
┌───────────────────────────────────────┐
│        電 子 發 票 證 明 聯             │
│           115年03-04月                 │
│          ZF-91471261                   │
│                                       │
│  115/04/13 16:56:00                   │
│  隨機碼:0930    賣方:53538851          │
│                                       │
│   ┌─────────┐   ┌─────────┐           │
│   │  QR Left│   │ QR Right│           │
│   │         │   │         │           │
│   └─────────┘   └─────────┘           │
│   ║║║║║║║║║║║║║║║║║║║║║║║║║║          │
│   (Code 39 Barcode)                   │
│───────────────────────────────────────│
│  品名        數量    單價      金額     │
│  Bacon Burger  1     220      220     │
│───────────────────────────────────────│
│  銷售額                    $210       │
│  稅　額                    $ 10       │
│  總　計                    $220       │
│                                       │
│       退貨時請攜帶本證明聯正本          │
└───────────────────────────────────────┘
```
