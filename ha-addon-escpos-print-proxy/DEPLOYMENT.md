# Deployment & Test Runbook / 部署與測試手冊

Bilingual step-by-step runbook for deploying the ESC/POS Print Proxy
add-on and verifying it end-to-end from a cloud Odoo POS order.

英文與繁體中文對照的部署與測試操作手冊。依本手冊逐步執行可完成
「雲端 Odoo 下單 → 本地 ESC/POS 印表機出單」整條鏈路。

For the architecture reference, see `DOCS.md`.
如需架構與完整參考，請參閱 `DOCS.md`。

---

## Legend / 圖例

- 🟢 Safe / low risk — 安全步驟，風險低
- 🟡 Check before proceeding — 執行前請確認
- 🔴 Production-affecting — 影響正式環境，請先取得許可
- ☑️ Verification checkpoint — 驗證檢查點，未通過請停止
- 🧯 Rollback — 回復步驟

---

## Phase 0 — Prerequisites Check / 前置條件檢查

### 0.1 🟡 Confirm target environment / 確認部署目標

**EN**: Before touching anything, decide:
- Which shop / site is being rolled out first?
- What is the Odoo server URL (e.g. `https://pos.mycafe.com`)?
- What is the Home Assistant hostname on that shop's LAN
  (e.g. `homeassistant.local` or `192.168.1.10`)?
- What is the ESC/POS printer's LAN IP (e.g. `192.168.1.50`)?
- Which Cloudflare domain will host the tunnel subdomain
  (e.g. `mycafe.com`)?

Write these down. You will paste them into the add-on config and the
Odoo printer form later — using the wrong value at either end is the
#1 source of setup failures.

**中文**：開始之前先確認：
- 第一個要部署的門市是哪一家？
- 雲端 Odoo 網址（例：`https://pos.mycafe.com`）？
- 該門市 Home Assistant 的主機名稱（例：`homeassistant.local`
  或 `192.168.1.10`）？
- 門市 ESC/POS 印表機的區域網路 IP（例：`192.168.1.50`）？
- 要用哪個 Cloudflare 網域設定 tunnel 子網域（例：`mycafe.com`）？

**把這五個值寫下來**。稍後要貼入 HA add-on 設定與 Odoo 印表機
表單。兩端值填錯是目前為止最常見的失敗原因。

☑️ **Verification / 驗證**: All five values captured in writing.
☑️ **驗證**：以上五項都已寫下。

### 0.2 🟢 Confirm local printing already works / 確認本地印表已可用

**EN**: The feature only adds an alternative path; it does not fix
broken local printing. Before rolling out:
1. Log into Odoo POS at the shop.
2. Place a throwaway order and fire the receipt / kitchen ticket.
3. Confirm paper comes out of the target printer.

If local printing doesn't work, stop here. Fix that first (IP
misconfig, printer offline, etc.) and come back.

**中文**：本功能只是新增一條雲端路徑，**不會修復**本地印表故障。
部署前請先：
1. 在門市登入 Odoo POS。
2. 下一筆測試訂單並觸發出單。
3. 確認目標印表機真的吐紙。

若本地印表不通，請先停止部署，排除（IP 設錯、印表機未開機等）
問題後再繼續。

☑️ **Verification**: A real receipt printed from local POS flow.
☑️ **驗證**：本地 POS 流程已實際印出一張收據。

### 0.3 🟢 Confirm access / 確認必要權限

**EN**: You need:
- [ ] Admin access to the Home Assistant UI (Settings → Add-ons).
- [ ] Admin access to the Cloudflare dashboard for the chosen domain.
- [ ] Admin access to cloud Odoo (to edit pos.printer records and
      run module upgrades).
- [ ] SSH or remote-file access to the cloud Odoo server (to
      `git pull` / rsync the latest `epic/cloud-escpos-printing`
      branch). This may be the Docker host or the container
      directly depending on how the env is set up.
- [ ] A terminal or machine that can run `curl` from **outside**
      the shop's LAN (for tunnel verification). A laptop on
      cellular data works.

**中文**：需要以下權限：
- [ ] Home Assistant 管理介面的管理員權限（設定 → 附加組件）
- [ ] Cloudflare 儀表板對目標網域的管理權限
- [ ] 雲端 Odoo 管理員（可修改 pos.printer 紀錄、執行模組升級）
- [ ] 雲端 Odoo 伺服器的 SSH 或檔案存取權限（用於 `git pull` /
      rsync 最新的 `epic/cloud-escpos-printing` branch）。視環境
      可能是 Docker 宿主機或容器本身。
- [ ] 一台可在**門市 LAN 外部**執行 `curl` 的機器（用來驗證
      tunnel）。用 4G/5G 的筆電即可。

---

## Phase 1 — Build & Install the Add-on / 建置與安裝 Add-on

### 1.1 🟢 Get the code onto the HA host / 將程式碼傳到 HA 主機

**EN**: The add-on sources live in this repo under
`ha-addon-escpos-print-proxy/`. Home Assistant install from a local
add-on repository — the directory needs to be readable by the HA
supervisor.

Option A (recommended): push the whole repo to a private GitHub repo
that HA can pull from as a custom add-on repository.

Option B (air-gapped shop): copy `ha-addon-escpos-print-proxy/` to
`/addons/escpos_print_proxy/` on the HA host via SCP or the
Samba share add-on.

```bash
# Option B example (from your dev machine, assuming SSH to HA):
scp -r ha-addon-escpos-print-proxy root@homeassistant.local:/addons/escpos_print_proxy
```

**中文**：add-on 原始碼位於本 repo 的 `ha-addon-escpos-print-proxy/`
目錄。HA 從本地 add-on repository 安裝——該目錄需可被 HA supervisor
讀取。

方案 A（建議）：把整個 repo 推到 GitHub 私有庫，HA 再把該庫加為
custom add-on repository 安裝。

方案 B（離線門市）：透過 SCP 或 Samba share 附加組件把
`ha-addon-escpos-print-proxy/` 複製到 HA 主機的
`/addons/escpos_print_proxy/`。

☑️ **Verification**: `ls /addons/escpos_print_proxy/` on HA host
shows `config.yaml`, `Dockerfile`, `run.sh`, `print_proxy.py`,
`escpos_min.py`.
☑️ **驗證**：HA 主機上 `ls /addons/escpos_print_proxy/` 可看到
`config.yaml`、`Dockerfile`、`run.sh`、`print_proxy.py`、`escpos_min.py`。

### 1.2 🟢 Install in Home Assistant / 在 Home Assistant 中安裝

**EN**:
1. Home Assistant → **Settings** → **Add-ons** → **Add-on Store**.
2. Top-right **⋮** menu → **Check for updates** (forces a rescan so
   local add-ons appear).
3. Scroll to the "Local add-ons" section → click
   **ESC/POS Print Proxy**.
4. Click **Install**. First install takes ~2 minutes while Docker
   builds the image (Alpine + Python 3.11 + Flask + Pillow).
5. Wait for the button to change to **Uninstall** / **Start**.

**中文**：
1. Home Assistant → **設定** → **附加組件** → **附加組件商店**。
2. 右上角 **⋮** 選單 → **檢查更新**（強制重新掃描本地目錄）。
3. 捲動到「本地附加組件」區塊 → 點選 **ESC/POS Print Proxy**。
4. 點 **安裝**。首次安裝約需 2 分鐘建置 Docker 映像
   （Alpine + Python 3.11 + Flask + Pillow）。
5. 等按鈕變成 **解除安裝** / **啟動** 即完成。

☑️ **Verification**: Add-on appears as **Stopped** in the
Add-ons list, not an error.
☑️ **驗證**：附加組件清單中顯示為 **已停止**，不是錯誤狀態。

### 1.3 🟢 Generate and save the API key / 產生並保存 API key

**EN**: On any machine with `openssl`:
```bash
openssl rand -hex 32
```
That prints a 64-character hex string. **Copy it now**. Save to your
team password manager under a note like:
> Shop: Main branch — ESC/POS Print Proxy API key
> 2026-04-16

Generate a **different** key for each shop. Never reuse a key.

**中文**：在任何有 `openssl` 的機器上執行：
```bash
openssl rand -hex 32
```
會印出一串 64 字元的十六進位金鑰。**立刻複製**，存到團隊密碼管理
工具，命名例如：
> 門市：總店 — ESC/POS Print Proxy API key
> 2026-04-16

**每家門市用不同的金鑰**，絕對不要重複使用。

### 1.4 🟡 Configure the add-on / 設定 add-on

**EN**:
1. Click the add-on → **Configuration** tab.
2. Set:
   - `api_key`: paste the 64-char hex string from step 1.3
   - `port`: `8073` (unless you know you need a different one)
   - `paper_mm`: `80` (for 80mm thermal paper) or `58` (for 58mm)
3. Click **Save**.
4. Go to the **Info** tab → click **Start**.
5. Switch to the **Log** tab. Expect a line like:
   ```
   ESC/POS print proxy 0.1.0 listening on 0.0.0.0:8073
   ```

If you see `api_key is empty. Generate one with: openssl rand -hex 32`
the add-on refused to start — go back to step 1.3.

**中文**：
1. 點選該附加組件 → **組態**頁籤。
2. 填入：
   - `api_key`：貼上 1.3 產生的 64 字元金鑰
   - `port`：`8073`（通常不用改）
   - `paper_mm`：`80`（80mm 熱感紙）或 `58`（58mm）
3. 點 **儲存**。
4. 切換到 **資訊** 頁籤 → 點 **啟動**。
5. 切到 **紀錄** 頁籤。預期看到：
   ```
   ESC/POS print proxy 0.1.0 listening on 0.0.0.0:8073
   ```

若看到 `api_key is empty. Generate one with: openssl rand -hex 32`，
表示 add-on 拒絕啟動——請回到步驟 1.3 重新產生金鑰。

☑️ **Verification**: The **Log** tab shows the "listening on" line
and no Python traceback.
☑️ **驗證**：**紀錄** 頁籤顯示「listening on」那一行，沒有 Python
traceback。

### 1.5 🟢 Local smoke test / 本機煙霧測試

**EN**: From the HA Terminal & SSH add-on (or any shell on the HA
host):
```bash
# unauthenticated — should always return 200
curl http://localhost:8073/status
# expected: {"ok": true, "version": "0.1.0", "uptime_s": ...}

# without auth — must return 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:8073/print -H "Content-Type: application/json" \
  -d '{"image_base64":"x","printer_ip":"1.2.3.4"}'
# expected: 401

# with wrong bearer — must return 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:8073/print \
  -H "Authorization: Bearer wrongkey" \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"x","printer_ip":"1.2.3.4"}'
# expected: 401

# with right bearer but bad image — must return 400
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:8073/print \
  -H "Authorization: Bearer PASTE_YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"notbase64","printer_ip":"1.2.3.4"}'
# expected: 400
```

**中文**：從 HA 的 **Terminal & SSH** 附加組件（或任何 HA 主機的
shell）執行以下四段 curl（與上方相同）。

☑️ **Verification**: All four curls return the expected HTTP codes.
☑️ **驗證**：四段 curl 回傳碼與預期一致（200 / 401 / 401 / 400）。

---

## Phase 2 — Expose via Cloudflare Tunnel / 透過 Cloudflare Tunnel 對外公開

### 2.1 🟡 Pick the public hostname / 選定公開網址

**EN**: Typical choice: `print.<shop>.<yourdomain>` — e.g.
`print.mycafe.com` for one shop, `print.mycafe-downtown.com` for
another. Each shop must have a **unique** hostname.

**中文**：慣例：`print.<shop>.<yourdomain>`，例如
`print.mycafe.com`、`print.mycafe-downtown.com`。**每家門市的網址
必須唯一**。

### 2.2 🔴 Add the tunnel route / 新增 tunnel 路由

**EN**:
1. Home Assistant → **Settings** → **Add-ons** → Cloudflare add-on →
   **Configuration**.
2. Add to `additional_hosts`:
   ```yaml
   additional_hosts:
     - hostname: print.mycafe.com
       service: http://localhost:8073
   ```
3. Save → **Restart** the Cloudflare add-on.
4. Switch to the Cloudflare add-on **Log** tab. Wait for
   `Registered tunnel connection`.

Alternative (Zero Trust dashboard users): Zero Trust →
**Networks** → **Tunnels** → your tunnel → **Public Hostname** →
**Add public hostname**. Subdomain `print`, domain `mycafe.com`,
service `HTTP` → `localhost:8073` → Save.

**中文**：
1. Home Assistant → **設定** → **附加組件** → Cloudflare 附加組件
   → **組態**。
2. 在 `additional_hosts` 區段加入：
   ```yaml
   additional_hosts:
     - hostname: print.mycafe.com
       service: http://localhost:8073
   ```
3. 儲存 → **重新啟動** Cloudflare 附加組件。
4. 切到該附加組件 **紀錄** 頁籤，等看到
   `Registered tunnel connection` 字樣。

若使用 Cloudflare Zero Trust dashboard：Zero Trust →
**Networks** → **Tunnels** → 你的 tunnel → **Public Hostname** →
**Add public hostname**。子網域填 `print`，網域 `mycafe.com`，
服務 `HTTP` → `localhost:8073` → 儲存。

### 2.3 ☑️ Verify external reachability / 外部可達性驗證

**EN**: From a machine **outside** the shop's LAN (laptop on
cellular data is ideal):
```bash
curl https://print.mycafe.com/status
# expected: {"ok": true, "version": "0.1.0", "uptime_s": ...}
```

If instead you get:
- Cloudflare HTML error page → tunnel not connected or hostname
  not configured
- `curl: (6) Could not resolve host` → DNS not propagated yet
  (wait 1–2 min and retry)
- 502 → add-on is stopped; check Phase 1.4 again

**中文**：在**門市網路之外**的機器（用 4G/5G 的筆電最直接）執行：
```bash
curl https://print.mycafe.com/status
```

若看到：
- Cloudflare 的 HTML 錯誤頁面 → tunnel 未連線或子網域未設好
- `curl: (6) Could not resolve host` → DNS 尚未生效（等 1–2 分鐘
  重試）
- 502 → add-on 已停止；請回到 1.4 重新檢查

☑️ **Do NOT proceed to Phase 3 until this step passes.**
☑️ **此步驟未通過前，不要進入 Phase 3。**

---

## Phase 3 — Deploy Odoo-side Code / 部署 Odoo 端程式

### 3.1 🔴 Update code on the cloud Odoo server / 更新雲端 Odoo 程式

**EN**: The Odoo-side changes live on the `epic/cloud-escpos-printing`
branch. Two common patterns in this repo:

Option A (direct rsync):
```bash
rsync -avz --delete \
  /local/path/pos_self_order_enhancement/ \
  user@odoo-host:/opt/odoo/addons/pos_self_order_enhancement/
```

Option B (server-side git pull):
```bash
ssh user@odoo-host
cd /opt/odoo/addons/pos_self_order_enhancement
git fetch origin
git checkout epic/cloud-escpos-printing
# or, after merging to main/dev:
git pull
```

Verify the new files arrived:
```bash
grep -c escpos_proxy_url \
  /opt/odoo/addons/pos_self_order_enhancement/models/pos_printer.py
# expected: >= 3
```

**中文**：Odoo 端變更位於 `epic/cloud-escpos-printing` branch。
本 repo 常用兩種部署方式：

方案 A（直接 rsync）：
```bash
rsync -avz --delete \
  /local/path/pos_self_order_enhancement/ \
  user@odoo-host:/opt/odoo/addons/pos_self_order_enhancement/
```

方案 B（伺服器端 git pull）：
```bash
ssh user@odoo-host
cd /opt/odoo/addons/pos_self_order_enhancement
git fetch origin
git checkout epic/cloud-escpos-printing
```

確認新檔案已到位（同上 grep 指令）。

### 3.2 🔴 Restart Odoo & upgrade module / 重啟 Odoo 並升級模組

**EN**:
```bash
# Docker-based install:
docker restart odoo

# Upgrade via XML-RPC (adapt URL/creds):
python3 -c "
import xmlrpc.client
url='https://pos.mycafe.com'
db='mydb'; user='admin'; pwd='xxx'
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, user, pwd, {})
models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
mid = models.execute_kw(db, uid, pwd, 'ir.module.module', 'search',
    [[['name','=','pos_self_order_enhancement']]])
models.execute_kw(db, uid, pwd, 'ir.module.module',
    'button_immediate_upgrade', [mid])
print('upgraded')
"
```

Alternative: Odoo UI → Apps → search "pos_self_order_enhancement" →
**Upgrade**.

**中文**：與上方指令相同。另可於 Odoo UI → 應用程式 → 搜尋
`pos_self_order_enhancement` → 點 **升級**。

☑️ **Verification**: Open a pos.printer record in Odoo backend; the
two new fields (**Cloud Relay URL**, **Cloud Relay API Key**) appear
when **Printer Type** is "Use a network ESC/POS printer".
☑️ **驗證**：在 Odoo 後台打開任一 pos.printer 紀錄，當印表機類型
為「Use a network ESC/POS printer」時，可看到兩個新欄位：
**Cloud Relay URL**、**Cloud Relay API Key**。

### 3.3 🔴 Configure the printer record / 設定印表機紀錄

**EN**:
1. Odoo → **Point of Sale** → **Configuration** → **Printers**.
2. Open the target printer record.
3. Confirm **Printer Type** = "Use a network ESC/POS printer".
4. Confirm **Printer IP Address** is the LAN IP (e.g.
   `192.168.1.50`). **Do not change this** — it is still used by
   the add-on to reach the physical printer.
5. **Cloud Relay URL** = `https://print.mycafe.com` (from Phase 2).
6. **Cloud Relay API Key** = paste the 64-char hex from step 1.3.
7. **Save**.

**中文**：
1. Odoo → **Point of Sale** → **設定** → **印表機**。
2. 打開目標印表機紀錄。
3. 確認 **Printer Type** = "Use a network ESC/POS printer"。
4. 確認 **Printer IP Address** 為區域網路 IP（例：`192.168.1.50`）。
   **請勿更改**——add-on 仍需此值才能送到實體印表機。
5. **Cloud Relay URL** 填 `https://print.mycafe.com`（Phase 2 的網址）。
6. **Cloud Relay API Key** 貼入步驟 1.3 的 64 字元金鑰。
7. **儲存**。

---

## Phase 4 — Functional Tests / 功能測試

Run these in order. Stop at the first failure and use the
Troubleshooting section.
依下列順序測試。第一個失敗即停止，按 Troubleshooting 排錯。

### 4.1 ☑️ Backend test page / 後台測試頁

**EN**:
1. On the printer record, click **Print test page**.
2. Expected: a small test ticket comes out of the physical printer
   within ~3 seconds.
3. The printed ticket contains the line `Mode: cloud relay` —
   confirm this is printed (not `Mode: local TCP`). If you see
   "local TCP", the Cloud Relay URL field is empty or wasn't saved.
4. Expected notification in Odoo: "Test print sent … via cloud relay".

**中文**：
1. 在印表機紀錄上點 **Print test page**。
2. 預期：實體印表機在 ~3 秒內吐出一張測試收據。
3. 收據上會印出 `Mode: cloud relay` 字樣——請**確認**印出的是
   這行而非 `Mode: local TCP`。若為 "local TCP" 表示 Cloud Relay
   URL 欄位未填或未儲存。
4. Odoo 應彈出通知：「Test print sent … via cloud relay」。

☑️ **Pass criteria**: paper out, correct mode label, no error
notification.
☑️ **通過條件**：有吐紙、模式標籤正確、無錯誤通知。

### 4.2 ☑️ Negative test — wrong key / 反向測試：錯誤金鑰

**EN**:
1. On the printer record, temporarily change **Cloud Relay API Key**
   to something wrong (e.g. append `-BAD`). Save.
2. Click **Print test page**.
3. Expected: Odoo notification "Test print failed: unauthorized".
4. Revert the key (paste the correct one again). Save.

**中文**：
1. 在印表機紀錄上，暫時將 **Cloud Relay API Key** 改為錯誤值
   （例：在尾端加 `-BAD`）。儲存。
2. 點 **Print test page**。
3. 預期：Odoo 顯示「Test print failed: unauthorized」。
4. 把金鑰改回正確值。儲存。

☑️ **Pass criteria**: auth rejection reaches Odoo and is surfaced.
☑️ **通過條件**：驗證失敗訊息能從 add-on 回到 Odoo 並顯示給操作員。

### 4.3 ☑️ Real POS order / 實際 POS 訂單

**EN**:
1. Open cloud Odoo POS in a browser (Point of Sale → open session).
2. Create an order with at least one item that triggers a kitchen
   ticket (or whichever category routes to the test printer).
3. Validate the order / fire the ticket.
4. Expected: the same printer prints a real kitchen ticket within
   ~3 seconds.

**中文**：
1. 在瀏覽器開啟雲端 Odoo POS（Point of Sale → 開啟收銀機）。
2. 建立一筆包含至少一項會觸發廚房單據的商品（或其他會路由到
   測試印表機的分類）的訂單。
3. 結算訂單／觸發出單。
4. 預期：相同印表機在 ~3 秒內印出真正的廚房單據。

☑️ **Pass criteria**: kitchen ticket comes out, content matches the
order, no error in Odoo UI.
☑️ **通過條件**：廚房單據實際吐出、內容與訂單一致、Odoo 介面無錯誤。

### 4.4 ☑️ Rollback drill / 回復演練

**EN**: Before handing off, prove the escape hatch works:
1. On the printer record, **clear** the **Cloud Relay URL** field.
   Save.
2. Fire another order (or click Print test page).
3. Expected: paper still comes out. The printed ticket now says
   `Mode: local TCP`.
4. This proves fallback works if the cloud path ever breaks. Restore
   the Cloud Relay URL afterward.

**中文**：交接前務必驗證緊急回復可用：
1. 在印表機紀錄上，**清空** **Cloud Relay URL** 欄位。儲存。
2. 再下一筆訂單（或再點 Print test page）。
3. 預期：仍會吐紙。收據上印的是 `Mode: local TCP`。
4. 這證明雲端路徑故障時可即時回退。確認後請把 Cloud Relay URL
   填回去。

☑️ **Pass criteria**: local TCP fallback works with zero restart.
☑️ **通過條件**：無須重啟任何服務，本地 TCP fallback 即時生效。

---

## Phase 5 — Handoff / 交接

### 5.1 Record credentials / 登錄認證資訊

**EN**: In the team password manager, under this shop's entry:
- Cloudflare tunnel hostname (e.g. `print.mycafe.com`)
- HA Add-on API key (64-char hex)
- HA Add-on version (check `CHANGELOG.md`)
- Date deployed, person deploying

Do **not** email, chat, or commit any of these.

**中文**：在團隊密碼管理工具中，以該門市為一筆條目，登錄：
- Cloudflare tunnel 網址（例：`print.mycafe.com`）
- HA Add-on API key（64 字元十六進位字串）
- HA Add-on 版本（見 `CHANGELOG.md`）
- 部署日期、部署人

以上資訊**絕對不要**用 email、LINE/Slack 傳送，也不要 commit 到 git。

### 5.2 Operator briefing / 門市人員交接

**EN**: Show the shop operator:
- How to open the HA Add-on log (Settings → Add-ons → ESC/POS Print
  Proxy → Log) — this is the first thing to check if prints stop.
- Who to contact and what info to send (add-on log screenshot,
  approximate time, example order number).
- That clearing **Cloud Relay URL** in Odoo is the emergency
  rollback; it requires no technical steps beyond editing one field.

**中文**：向門市人員交接以下事項：
- 如何查看 HA Add-on 紀錄（設定 → 附加組件 → ESC/POS Print Proxy
  → 紀錄）——這是印表故障時最先要看的地方。
- 發生問題時聯絡誰、要附上什麼資訊（紀錄截圖、大約時間、範例
  訂單編號）。
- 雲端路徑故障時的**緊急回復方法**：到 Odoo 印表機紀錄，把
  **Cloud Relay URL** 清空並儲存即可，無需其他技術操作。

---

## Troubleshooting / 疑難排解

| Symptom / 症狀                               | Likely cause / 可能原因           | Fix / 處理                                     |
|----------------------------------------------|-----------------------------------|-----------------------------------------------|
| `Relay unreachable: ...` in Odoo             | Tunnel down or hostname wrong / tunnel 斷線或網址錯 | Re-check Phase 2.3 external `curl /status`     |
| `unauthorized`                               | API key mismatch / 金鑰不一致      | Regenerate & paste in both HA add-on **and** Odoo / 兩端都重新貼 |
| `printer unreachable: ...`                   | LAN printer off / IP wrong / 印表機關機或 IP 錯 | Verify from HA: `curl telnet://<IP>:9100`      |
| Test page prints `Mode: local TCP`           | Cloud Relay URL empty / Cloud Relay URL 沒填 | Fill URL in Odoo printer form, save            |
| Add-on "refused to start" in log             | `api_key` empty / api_key 空白     | Set in Configuration, Start again              |
| External curl returns Cloudflare 1033        | Tunnel not actually connected / tunnel 未連線 | Restart Cloudflare add-on, check its log       |
| Prints work but very slow (>5s)              | Tunnel routing suboptimal / 線路繞遠 | Check Cloudflare dashboard for tunnel region   |

---

## Appendix A — Log Locations / 附錄 A：紀錄位置

| System / 系統              | Where / 位置                                              |
|----------------------------|-----------------------------------------------------------|
| ESC/POS Print Proxy add-on | HA → Settings → Add-ons → ESC/POS Print Proxy → **Log** |
| Cloudflare Tunnel          | HA → Settings → Add-ons → Cloudflare → **Log**           |
| Odoo server                | Docker container stdout; grep `[escpos]`                  |

## Appendix B — Dispatch mode in Odoo log / 附錄 B：Odoo 端模式判讀

**EN**: The controller logs which path took every print job:
```
INFO [escpos] local TCP -> 192.168.1.50
INFO [escpos] relay -> https://print.mycafe.com/print (printer=192.168.1.50)
WARNING [escpos] relay refused: unauthorized
WARNING [escpos] relay request failed: ConnectTimeout
```

**中文**：Odoo 伺服器紀錄中可依以上關鍵字判斷目前使用哪條路徑，
以及失敗時的具體原因。
