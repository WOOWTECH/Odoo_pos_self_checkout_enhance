/**
 * Kitchen Display Screen (KDS) for POS Self-Order Enhancement
 *
 * Standalone web page — no OWL framework dependency.
 * Uses interval polling for real-time order updates.
 */
(function () {
    "use strict";

    const INFO = window.__kds_session_info__;
    const CONFIG_ID = INFO.config_id;
    const TOKEN = INFO.access_token;
    // Always use relative URLs — the KDS page is served from the same origin.
    // INFO.base_url may omit the port (e.g. proxy on 80 vs Odoo on 8069) causing CORS.
    const BASE_URL = "";

    // ── i18n ──────────────────────────────────────────────
    const TRANSLATIONS = {
        en: {
            kitchen_display: "Kitchen Display",
            orders: "Orders",
            items: "Items",
            history: "History",
            bump: "Done",
            recall: "Recall",
            takeaway: "Takeaway",
            table: "Table",
            active_orders: "Active Orders",
            no_active_orders: "No active orders",
            no_completed_orders: "No completed orders",
            items_overview: "Items Overview",
            completed_orders: "Completed Orders",
            done_progress: "done",
            remake: "REMAKE",
            tap_to_enable_sound: "Tap anywhere to enable sound notifications",
        },
        zh_TW: {
            kitchen_display: "\u5EDA\u623F\u986F\u793A",
            orders: "\u8A02\u55AE",
            items: "\u54C1\u9805",
            history: "\u6B77\u53F2",
            bump: "\u5B8C\u6210\u51FA\u9910",
            recall: "\u53EC\u56DE",
            takeaway: "\u5916\u5E36",
            table: "\u684C",
            active_orders: "\u9032\u884C\u4E2D\u8A02\u55AE",
            no_active_orders: "\u76EE\u524D\u6C92\u6709\u8A02\u55AE",
            no_completed_orders: "\u6C92\u6709\u5DF2\u5B8C\u6210\u7684\u8A02\u55AE",
            items_overview: "\u54C1\u9805\u7E3D\u89BD",
            completed_orders: "\u5DF2\u5B8C\u6210\u8A02\u55AE",
            done_progress: "\u5B8C\u6210",
            remake: "\u91CD\u505A",
            tap_to_enable_sound: "\u9EDE\u64CA\u4EFB\u610F\u4F4D\u7F6E\u4EE5\u555F\u7528\u8072\u97F3\u901A\u77E5",
        },
    };

    let currentLang = localStorage.getItem("kds_lang") || "en";

    function t(key) {
        return (TRANSLATIONS[currentLang] || TRANSLATIONS.en)[key] || TRANSLATIONS.en[key] || key;
    }

    // ── State ───────────────────────────────────────────────
    let orders = [];
    let completedOrders = [];
    let pollingActive = false;
    let timerInterval = null;
    let currentView = "orders"; // "orders" | "items" | "history"
    let chimeAudio = null;

    // ── JSON-RPC helper ─────────────────────────────────────
    async function rpc(url, params = {}) {
        params.token = TOKEN;
        const resp = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                id: Date.now(),
                params: params,
            }),
        });
        const data = await resp.json();
        if (data.error) {
            console.error("RPC error:", data.error);
            return null;
        }
        return data.result;
    }

    // ── Audio ───────────────────────────────────────────────
    // Shared AudioContext — created once, resumed on user gesture
    let audioCtx = null;
    function initAudio() {
        try {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        } catch (e) {
            console.warn("KDS: AudioContext not available", e);
        }
    }

    function resumeAudio() {
        if (!audioCtx) initAudio();
        if (audioCtx && audioCtx.state === "suspended") {
            audioCtx.resume();
        }
    }

    // Full-screen overlay — shown when AudioContext is suspended
    function showSoundOverlay() {
        if (!audioCtx || audioCtx.state !== "suspended") return;
        const overlay = document.createElement("div");
        overlay.className = "kds-sound-overlay";
        overlay.innerHTML = `
            <div class="kds-sound-overlay-content">
                <div class="kds-sound-overlay-icon">\uD83D\uDD14</div>
                <div class="kds-sound-overlay-text">${escapeHtml(t("tap_to_enable_sound"))}</div>
            </div>`;
        overlay.addEventListener("click", () => {
            resumeAudio();
            overlay.classList.add("kds-sound-overlay-dismiss");
            setTimeout(() => overlay.remove(), 300);
        });
        document.body.appendChild(overlay);
    }

    function playChime() {
        if (!audioCtx || audioCtx.state !== "running") {
            console.warn("KDS: Sound skipped — AudioContext not running");
            return;
        }
        try {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.frequency.value = 880;
            osc.type = "sine";
            gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.5);
            osc.start(audioCtx.currentTime);
            osc.stop(audioCtx.currentTime + 0.5);
        } catch (e) {
            console.warn("KDS: playChime failed", e);
        }
    }

    function playRemakeChime() {
        if (!audioCtx || audioCtx.state !== "running") {
            console.warn("KDS: Sound skipped — AudioContext not running");
            return;
        }
        try {
            for (let i = 0; i < 2; i++) {
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.frequency.value = 660;
                osc.type = "square";
                const start = audioCtx.currentTime + i * 0.3;
                gain.gain.setValueAtTime(0.3, start);
                gain.gain.exponentialRampToValueAtTime(0.01, start + 0.2);
                osc.start(start);
                osc.stop(start + 0.2);
            }
        } catch (e) {
            console.warn("KDS: playRemakeChime failed", e);
        }
    }

    // ── Data fetching ───────────────────────────────────────
    async function fetchOrders() {
        const result = await rpc(`${BASE_URL}/pos-kds/orders/${CONFIG_ID}`);
        if (!result) return;

        const oldIds = new Set(orders.map((o) => o.id));
        const oldRemakeIds = new Set(orders.filter((o) => o.is_remake).map((o) => o.id));
        orders = result.orders || [];

        // Check for new orders or new remake orders
        const newRemake = orders.some((o) => o.is_remake && !oldRemakeIds.has(o.id));
        const hasNew = orders.some((o) => !oldIds.has(o.id));
        if (newRemake && oldIds.size > 0) {
            playRemakeChime();
        } else if (hasNew && oldIds.size > 0) {
            playChime();
        }

        if (!result.has_session) {
            orders = [];
        }

        render();
    }

    async function fetchCompleted() {
        const result = await rpc(`${BASE_URL}/pos-kds/completed/${CONFIG_ID}`);
        if (!result) return;
        completedOrders = result.orders || [];
        render();
    }

    // ── Actions ─────────────────────────────────────────────
    async function bumpOrder(orderId) {
        await rpc(`${BASE_URL}/pos-kds/bump/${CONFIG_ID}`, { order_id: orderId });
        // Remove from local state immediately for responsiveness
        orders = orders.filter((o) => o.id !== orderId);
        render();
    }

    async function toggleItemDone(orderId, lineId) {
        const result = await rpc(`${BASE_URL}/pos-kds/item-done/${CONFIG_ID}`, {
            order_id: orderId,
            line_id: lineId,
        });
        if (result && result.all_done) {
            orders = orders.filter((o) => o.id !== orderId);
            render();
        } else {
            await fetchOrders();
        }
    }

    async function batchMarkDone(productName) {
        const result = await rpc(`${BASE_URL}/pos-kds/batch-item-done/${CONFIG_ID}`, {
            product_name: productName,
        });
        if (result && result.success) {
            await fetchOrders();
        }
    }

    async function recallOrder(orderId) {
        const params = orderId ? { order_id: orderId } : {};
        await rpc(`${BASE_URL}/pos-kds/recall/${CONFIG_ID}`, params);
        currentView = "orders";
        await fetchOrders();
    }

    // ── Polling (interval-based, fetches every 3s) ────────
    function startPolling() {
        if (pollingActive) return;
        pollingActive = true;
        // Poll every 3 seconds for near-real-time updates
        setInterval(fetchOrders, 3000);
    }

    // ── Timer ───────────────────────────────────────────────
    function startTimers() {
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            // Update elapsed times locally
            orders.forEach((o) => {
                o.elapsed_total_seconds = (o.elapsed_total_seconds || 0) + 1;
                o.elapsed_minutes = Math.floor(o.elapsed_total_seconds / 60);
                o.elapsed_seconds = o.elapsed_total_seconds % 60;
            });
            updateTimers();
        }, 1000);
    }

    function updateTimers() {
        document.querySelectorAll(".kds-card").forEach((card) => {
            const orderId = parseInt(card.dataset.orderId);
            const order = orders.find((o) => o.id === orderId);
            if (!order) return;

            const timerEl = card.querySelector(".kds-timer");
            if (timerEl) {
                const mins = order.elapsed_minutes;
                const secs = String(order.elapsed_seconds).padStart(2, "0");
                timerEl.textContent = `${mins}:${secs}`;
                timerEl.className = "kds-timer " + getTimerClass(mins);
            }
        });
    }

    function getTimerClass(minutes) {
        if (minutes >= 10) return "timer-red";
        if (minutes >= 5) return "timer-yellow";
        return "timer-green";
    }

    // ── Rendering ───────────────────────────────────────────
    function render() {
        const app = document.getElementById("kds-app");
        app.innerHTML = renderHeader() + renderBody();
        bindEvents();
    }

    function renderHeader() {
        const ordersClass = currentView === "orders" ? "active" : "";
        const itemsClass = currentView === "items" ? "active" : "";
        const historyClass = currentView === "history" ? "active" : "";
        const langLabel = currentLang === "en" ? "EN/\u4E2D" : "\u4E2D/EN";

        return `
        <header class="kds-header">
            <div class="kds-header-left">
                <span class="kds-logo">\uD83C\uDF73</span>
                <span class="kds-title">${escapeHtml(t("kitchen_display"))} - ${escapeHtml(INFO.config_name)}</span>
                <button class="kds-btn kds-btn-lang" data-action="toggle-lang">${langLabel}</button>
            </div>
            <div class="kds-header-right">
                <button class="kds-btn kds-btn-header ${ordersClass}" data-action="orders">
                    ${escapeHtml(t("orders"))}
                </button>
                <button class="kds-btn kds-btn-header ${itemsClass}" data-action="items">
                    ${escapeHtml(t("items"))}
                </button>
                <button class="kds-btn kds-btn-header ${historyClass}" data-action="history">
                    ${escapeHtml(t("history"))}
                </button>
            </div>
        </header>`;
    }

    function renderBody() {
        if (currentView === "items") {
            return renderItemsView();
        }
        if (currentView === "history") {
            return renderHistoryView();
        }
        return renderOrdersView();
    }

    function renderOrdersView() {
        let html = `
        <div class="kds-view">
            <div class="kds-view-header">
                <h2>${escapeHtml(t("active_orders"))}</h2>
            </div>`;

        if (orders.length === 0) {
            html += `
            <div class="kds-empty">
                <div class="kds-empty-icon">\uD83D\uDC68\u200D\uD83C\uDF73</div>
                <div class="kds-empty-text">${escapeHtml(t("no_active_orders"))}</div>
            </div>`;
        } else {
            // Sort remake orders first
            const sorted = [...orders].sort((a, b) => {
                if (a.is_remake && !b.is_remake) return -1;
                if (!a.is_remake && b.is_remake) return 1;
                return 0;
            });
            html += '<div class="kds-grid">';
            for (const order of sorted) {
                html += renderOrderCard(order, false);
            }
            html += "</div>";
        }

        html += "</div>";
        return html;
    }

    function renderOrderCard(order, isCompleted) {
        const mins = order.elapsed_minutes || 0;
        const secs = String(order.elapsed_seconds || 0).padStart(2, "0");
        const timerClass = getTimerClass(mins);
        const stateClass = order.kds_state === "in_progress" ? "state-progress" : "state-new";
        const remakeClass = order.is_remake ? "remake" : "";

        // Table or takeaway label
        let locationLabel = "";
        if (order.is_takeaway) {
            locationLabel = `<span class="kds-takeaway">${escapeHtml(t("takeaway"))}</span>`;
        } else if (order.table_name) {
            locationLabel = `${escapeHtml(t("table"))} ${escapeHtml(order.table_name)}`;
        } else {
            locationLabel = order.name;
        }

        let linesHtml = "";
        for (const line of order.lines) {
            const doneClass = line.is_done ? "line-done" : "";
            const noteHtml = line.customer_note
                ? `<div class="kds-line-note">${escapeHtml(line.customer_note)}</div>`
                : "";
            const remakeReasonHtml = line.remake_reason && !line.is_done
                ? `<div class="kds-line-remake-reason">${escapeHtml(t("remake"))}: ${escapeHtml(line.remake_reason)}${line.remake_count > 1 ? ` (x${line.remake_count})` : ""}</div>`
                : "";
            linesHtml += `
            <div class="kds-line ${doneClass}" data-order-id="${order.id}" data-line-id="${line.id}">
                <span class="kds-line-check">${line.is_done ? '\u2611' : '\u2610'}</span>
                <span class="kds-line-qty">${line.qty}x</span>
                <span class="kds-line-name">${escapeHtml(line.product_name)}</span>
                ${noteHtml}
                ${remakeReasonHtml}
            </div>`;
        }

        // General note
        let generalNoteHtml = "";
        if (order.general_note) {
            generalNoteHtml = `<div class="kds-general-note">\uD83D\uDCDD ${escapeHtml(order.general_note)}</div>`;
        }

        const bumpBtn = isCompleted
            ? `<button class="kds-btn kds-btn-recall" data-action="recall-order" data-order-id="${order.id}">\u21A9\uFE0F ${escapeHtml(t("recall"))}</button>`
            : `<button class="kds-btn kds-btn-bump" data-action="bump" data-order-id="${order.id}">${escapeHtml(t("bump"))}</button>`;

        const remakeBadgeHtml = order.is_remake
            ? `<span class="kds-remake-badge">${escapeHtml(t("remake"))}</span>`
            : "";

        return `
        <div class="kds-card ${stateClass} ${remakeClass}" data-order-id="${order.id}">
            <div class="kds-card-header">
                <div class="kds-location">${locationLabel} ${remakeBadgeHtml}</div>
                <div class="kds-timer ${timerClass}">${mins}:${secs}</div>
            </div>
            <div class="kds-card-body">
                ${linesHtml}
                ${generalNoteHtml}
            </div>
            <div class="kds-card-footer">
                ${bumpBtn}
            </div>
        </div>`;
    }

    function renderItemsView() {
        // Aggregate item counts across all active orders
        const items = {};
        for (const order of orders) {
            for (const line of order.lines) {
                const key = line.product_name;
                if (!items[key]) {
                    items[key] = { name: key, qty: 0, done: 0 };
                }
                items[key].qty += line.qty;
                if (line.is_done) items[key].done += line.qty;
            }
        }

        const sorted = Object.values(items).sort((a, b) => b.qty - a.qty);

        let html = `
        <div class="kds-allday">
            <div class="kds-view-header">
                <h2>${escapeHtml(t("items_overview"))}</h2>
            </div>`;

        if (sorted.length === 0) {
            html += `
            <div class="kds-empty">
                <div class="kds-empty-icon">\uD83D\uDCE6</div>
                <div class="kds-empty-text">${escapeHtml(t("no_active_orders"))}</div>
            </div>`;
            html += "</div>";
            return html;
        }

        html += '<div class="kds-allday-grid">';

        for (const item of sorted) {
            const remaining = item.qty - item.done;
            const allDone = remaining === 0;
            const doneClass = allDone ? "allday-done" : "";
            html += `
            <div class="kds-allday-item ${doneClass}" data-action="batch-done" data-product-name="${escapeHtml(item.name)}">
                <span class="kds-allday-check">${allDone ? '\u2611' : '\u2610'}</span>
                <span class="kds-allday-qty">${item.qty}</span>
                <span class="kds-allday-name">${escapeHtml(item.name)}</span>
                ${item.done > 0 ? `<span class="kds-allday-progress">(${item.done}/${item.qty} ${escapeHtml(t("done_progress"))})</span>` : ""}
            </div>`;
        }

        html += "</div></div>";
        return html;
    }

    function renderHistoryView() {
        let html = `
        <div class="kds-completed-view">
            <div class="kds-view-header">
                <h2>${escapeHtml(t("completed_orders"))}</h2>
            </div>`;

        if (completedOrders.length === 0) {
            html += `
            <div class="kds-empty">
                <div class="kds-empty-icon">\u2705</div>
                <div class="kds-empty-text">${escapeHtml(t("no_completed_orders"))}</div>
            </div>`;
        } else {
            html += '<div class="kds-grid">';
            for (const order of completedOrders) {
                html += renderOrderCard(order, true);
            }
            html += "</div>";
        }

        html += "</div>";
        return html;
    }

    // ── Event binding ───────────────────────────────────────
    function bindEvents() {
        // Bump buttons
        document.querySelectorAll('[data-action="bump"]').forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const orderId = parseInt(btn.dataset.orderId);
                bumpOrder(orderId);
            });
        });

        // Item strikethrough
        document.querySelectorAll(".kds-line").forEach((el) => {
            el.addEventListener("click", () => {
                const orderId = parseInt(el.dataset.orderId);
                const lineId = parseInt(el.dataset.lineId);
                if (orderId && lineId) {
                    toggleItemDone(orderId, lineId);
                }
            });
        });

        // Batch mark done in Items view
        document.querySelectorAll('[data-action="batch-done"]').forEach((el) => {
            el.addEventListener("click", () => {
                const productName = el.dataset.productName;
                if (productName && !el.classList.contains("allday-done")) {
                    batchMarkDone(productName);
                }
            });
        });

        // Header view buttons
        document.querySelectorAll('[data-action="orders"]').forEach((btn) => {
            btn.addEventListener("click", () => {
                currentView = "orders";
                render();
            });
        });

        document.querySelectorAll('[data-action="items"]').forEach((btn) => {
            btn.addEventListener("click", () => {
                currentView = currentView === "items" ? "orders" : "items";
                render();
            });
        });

        document.querySelectorAll('[data-action="history"]').forEach((btn) => {
            btn.addEventListener("click", async () => {
                if (currentView === "history") {
                    currentView = "orders";
                    render();
                } else {
                    currentView = "history";
                    await fetchCompleted();
                }
            });
        });

        document.querySelectorAll('[data-action="recall-order"]').forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const orderId = parseInt(btn.dataset.orderId);
                recallOrder(orderId);
            });
        });

        // Language toggle
        document.querySelectorAll('[data-action="toggle-lang"]').forEach((btn) => {
            btn.addEventListener("click", () => {
                currentLang = currentLang === "en" ? "zh_TW" : "en";
                localStorage.setItem("kds_lang", currentLang);
                render();
            });
        });
    }

    // ── Utilities ────────────────────────────────────────────
    function escapeHtml(str) {
        const div = document.createElement("div");
        div.appendChild(document.createTextNode(str || ""));
        return div.innerHTML;
    }

    // ── Initialize ──────────────────────────────────────────
    async function init() {
        initAudio();
        render(); // Show empty state
        showSoundOverlay();
        await fetchOrders();
        startTimers();
        startPolling();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
