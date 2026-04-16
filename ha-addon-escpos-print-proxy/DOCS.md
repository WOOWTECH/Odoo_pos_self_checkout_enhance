# ESC/POS Print Proxy — Setup Guide

This guide walks an operator through installing the add-on and wiring it up
so a cloud-hosted Odoo POS can print kitchen tickets on a local ESC/POS
printer at each shop.

End-to-end flow:

```
  Cloud Odoo (POS browser)
        │  POST /pos-escpos/print  (same as before)
        ▼
  Cloud Odoo server  ── controllers/print_proxy.py
        │  HTTPS POST /print  (Bearer <api_key>)
        ▼
  Cloudflare Tunnel          (public -> your LAN, no open ports)
        │
        ▼
  Home Assistant (this add-on, listens on :8073)
        │  TCP :9100
        ▼
  ESC/POS printer  — paper comes out
```

Plain-English reassurance: the existing local-LAN printing keeps working
exactly as before for any printer whose **Cloud Relay URL** is left empty.
You can roll this out to one shop at a time.

---

## 1. Prerequisites

Before you start, confirm each of the following:

- [ ] **Home Assistant** is running at the shop and you can reach its UI
      (e.g. `http://homeassistant.local:8123`).
- [ ] The ESC/POS **printer is on the same LAN** as Home Assistant and you
      know its IP (e.g. `192.168.1.50`). Printing from the LAN already works
      via the module's existing local TCP path — verify that first.
- [ ] You have a **Cloudflare account** with a domain you control
      (e.g. `mycafe.com`) and the **Cloudflare HA Add-on** installed. The
      free tier is enough.
- [ ] You have **admin access** to the cloud Odoo and can open the
      pos.printer form (Point of Sale → Configuration → Printers).

![HA dashboard](images/01-ha-dashboard.png)

---

## 2. Install the add-on

### 2.1 Add the repository to Home Assistant

1. Open Home Assistant → **Settings** → **Add-ons** → **Add-on Store**.
2. Top-right **⋮** menu → **Repositories**.
3. Paste the repo URL (the folder that contains this add-on's `config.yaml`)
   and click **Add**.
4. Close the dialog; the new add-on appears in the store list as
   **ESC/POS Print Proxy**.

![Add repository](images/02-add-repo.png)

### 2.2 Install and configure

1. Click **ESC/POS Print Proxy** → **Install**.
2. When install completes, switch to the **Configuration** tab.
3. Generate a fresh API key on any machine with `openssl`:
   ```bash
   openssl rand -hex 32
   ```
   This prints a 64-character hex string. **Copy it now** — you won't be
   able to read it back from the add-on UI after you paste it.

4. Fill in the options:

   | Option    | Value                                              |
   |-----------|----------------------------------------------------|
   | api_key   | paste the hex string from `openssl rand -hex 32`   |
   | port      | `8073` (leave default unless it clashes)           |
   | paper_mm  | `80` for 80 mm paper, `58` for 58 mm               |

5. Click **Save**.
6. Switch to the **Info** tab → **Start**. Wait for the status to turn green
   ("Running"). Check the **Log** tab for a line like:
   ```
   ESC/POS print proxy 0.1.0 listening on 0.0.0.0:8073
   ```

![Add-on configured](images/03-addon-config.png)

### 2.3 Local sanity check (still inside Home Assistant)

From the HA Terminal & SSH add-on (or any shell on the HA host):

```bash
curl http://localhost:8073/status
# {"ok": true, "version": "0.1.0", "uptime_s": 2.3}
```

If that returns `{"ok": true, ...}`, the add-on itself is healthy.

---

## 3. Expose via Cloudflare Tunnel

The Cloudflare HA Add-on does all the heavy lifting — you just add a route.

### 3.1 Pick a hostname

Choose a subdomain under the domain you manage in Cloudflare. Example:

> `print.mycafe.com`

You'll use it both in Cloudflare and in Odoo, so **write it down** alongside
the API key.

### 3.2 Add the tunnel route

1. Open the **Cloudflare** add-on → **Configuration** tab.
2. Under `additional_hosts` (or the equivalent section for your version),
   add a route:

   ```yaml
   additional_hosts:
     - hostname: print.mycafe.com
       service: http://localhost:8073
   ```

   If you prefer the Cloudflare Zero Trust dashboard, create a Public
   Hostname with:
   - **Subdomain**: `print`
   - **Domain**: `mycafe.com`
   - **Service**: `HTTP`
   - **URL**: `localhost:8073`

3. Save and restart the Cloudflare add-on. Wait for the log to show the
   tunnel is connected.

![Cloudflare tunnel route](images/04-cf-route.png)

### 3.3 Verify the tunnel

From **anywhere outside the shop's LAN** (your laptop on cellular, for
instance):

```bash
curl https://print.mycafe.com/status
# {"ok": true, "version": "0.1.0", "uptime_s": 123.4}
```

If that returns `{"ok": true, ...}`, Cloudflare is correctly routing to the
add-on. If you get an HTML error page or 502, see **Troubleshooting**
below.

---

## 4. Configure the cloud Odoo

1. In cloud Odoo, go to **Point of Sale → Configuration → Printers**.
2. Open (or create) the printer record for this shop.
3. Make sure **Printer Type** is "Use a network ESC/POS printer".
4. Fill in the cloud relay fields:

   | Field                 | Value                         |
   |-----------------------|-------------------------------|
   | Printer IP Address    | `192.168.1.50` (LAN IP)       |
   | Cloud Relay URL       | `https://print.mycafe.com`    |
   | Cloud Relay API Key   | paste the key from §2.2       |

5. **Save**.
6. Click **Print test page**. A test ticket should come out of the physical
   printer within a few seconds. The printed ticket itself says
   `Mode: cloud relay` so you know the relay path was exercised.

![Odoo printer form](images/05-odoo-printer.png)

If the test page fails, Odoo shows a notification with the error — jump to
**Troubleshooting**.

---

## 5. Multi-location rollout

Each shop runs its own HA + Cloudflare Tunnel + add-on. For each additional
shop:

1. Install the add-on on that shop's HA.
2. Generate a **fresh** API key — do **not** reuse the first shop's key.
3. Add a Cloudflare route with a different subdomain (e.g.
   `print.mycafe-downtown.com`).
4. Create (or edit) that shop's `pos.printer` record in cloud Odoo with the
   new URL + key.

The same cloud Odoo serves all shops; the per-printer `escpos_proxy_url`
field is what directs each job to the correct LAN.

---

## 6. Troubleshooting

### Test page fails with "Relay unreachable: ..."

The HTTP POST from Odoo didn't get a response. In order, check:

1. **Cloudflare tunnel status** — in the Cloudflare add-on log, look for
   "connection registered". No line = tunnel isn't running.
2. **Add-on status** — in HA, the add-on must be **Running** (green). If
   red/stopped, start it and check the Log tab.
3. **Hostname typo** — `curl https://print.mycafe.com/status` from a laptop.
   HTML error = DNS / route issue; `404` = wrong subdomain; connection
   refused = tunnel down.

### Test page fails with `unauthorized`

The API key stored in Odoo doesn't match the one in the add-on.

1. Open the add-on **Configuration** tab. You cannot read the old key back —
   generate a fresh one (`openssl rand -hex 32`), save it.
2. Paste the **same** new key into the Odoo printer's **Cloud Relay API
   Key** field. Save.
3. Retry the test page.

### Test page fails with `printer unreachable: ...`

The tunnel delivered the job; the add-on tried to reach the LAN printer and
couldn't. This is a purely local-network issue:

- Is the printer powered on and on the same subnet as Home Assistant?
- From HA terminal: `curl telnet://192.168.1.50:9100` — should connect
  briefly. Connection refused = wrong IP or printer off. Timeout = network
  issue.
- Does the printer's IP match what's in Odoo's **Printer IP Address**
  field?

### It used to work and suddenly stopped

- Check that no one cleared the `Cloud Relay URL` field in Odoo — an empty
  field reverts that printer to local TCP, which won't reach the LAN from
  cloud Odoo.
- Cloudflare tunnel credentials can expire if a token is rotated; check
  the Cloudflare add-on log for auth errors.
- The add-on auto-restarts but doesn't auto-update — after a module
  upgrade that changes the contract, the add-on may need a version bump
  too (check `CHANGELOG.md` in this add-on).

### Log locations

- **Add-on log**: HA → Settings → Add-ons → ESC/POS Print Proxy → **Log**
  tab. Look for lines tagged `escpos_proxy:`.
- **Cloudflare tunnel log**: HA → Cloudflare add-on → **Log** tab.
- **Odoo server log**: the cloud Odoo container's stdout. Search for
  `[escpos]` for dispatch decisions (`local TCP` vs `relay`).

### 繁體中文註記

- 設定時請使用**無痕視窗或不同瀏覽器**貼上 API key，避免被自動填密碼工具覆蓋。
- `openssl rand -hex 32` 產生的金鑰請存在密碼管理器 (1Password, Bitwarden…)，
  不要寄 email 或貼到 LINE 群組。
- 若店內網路更換路由器，印表機 IP 會改變；修改 Odoo 的 **Printer IP
  Address** 欄位即可，不用重開 HA add-on。

---

## 7. Rollback

To take a printer out of cloud-relay mode:

1. Open the printer record in cloud Odoo.
2. **Clear** the **Cloud Relay URL** field (leave API key alone — harmless).
3. **Save**.

The printer immediately falls back to the local TCP path. No restart needed.
This is the escape hatch — use it if anything about the tunnel / add-on
misbehaves during rollout.
