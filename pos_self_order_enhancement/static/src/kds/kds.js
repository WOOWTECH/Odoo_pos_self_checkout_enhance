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
    const BASE_URL = INFO.base_url || "";

    // ── State ───────────────────────────────────────────────
    let orders = [];
    let completedOrders = [];
    let pollingActive = false;
    let timerInterval = null;
    let currentView = "active"; // "active" | "allday" | "completed"
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
    function playChime() {
        try {
            if (!chimeAudio) {
                // Generate a simple chime using Web Audio API
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.frequency.value = 880;
                osc.type = "sine";
                gain.gain.setValueAtTime(0.3, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.5);
            }
        } catch (e) {
            // Audio may not be available
        }
    }

    // ── Data fetching ───────────────────────────────────────
    async function fetchOrders() {
        const result = await rpc(`${BASE_URL}/pos-kds/orders/${CONFIG_ID}`);
        if (!result) return;

        const oldIds = new Set(orders.map((o) => o.id));
        orders = result.orders || [];

        // Check for new orders
        const hasNew = orders.some((o) => !oldIds.has(o.id));
        if (hasNew && oldIds.size > 0) {
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

    async function recallOrder(orderId) {
        const params = orderId ? { order_id: orderId } : {};
        await rpc(`${BASE_URL}/pos-kds/recall/${CONFIG_ID}`, params);
        currentView = "active";
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
        const activeClass = currentView === "active" ? "active" : "";
        const alldayClass = currentView === "allday" ? "active" : "";
        const completedClass = currentView === "completed" ? "active" : "";

        return `
        <header class="kds-header">
            <div class="kds-header-left">
                <span class="kds-logo">🍳</span>
                <span class="kds-title">廚房顯示 - ${escapeHtml(INFO.config_name)}</span>
            </div>
            <div class="kds-header-right">
                <button class="kds-btn kds-btn-header ${alldayClass}" data-action="allday">
                    📊 總覽
                </button>
                <button class="kds-btn kds-btn-header ${completedClass}" data-action="completed">
                    ✅ 已完成
                </button>
            </div>
        </header>`;
    }

    function renderBody() {
        if (currentView === "allday") {
            return renderAllDayView();
        }
        if (currentView === "completed") {
            return renderCompletedView();
        }
        return renderActiveView();
    }

    function renderActiveView() {
        if (orders.length === 0) {
            return `
            <div class="kds-empty">
                <div class="kds-empty-icon">👨‍🍳</div>
                <div class="kds-empty-text">目前沒有訂單</div>
                <div class="kds-empty-sub">No active orders</div>
            </div>`;
        }

        let html = '<div class="kds-grid">';
        for (const order of orders) {
            html += renderOrderCard(order, false);
        }
        html += "</div>";
        return html;
    }

    function renderOrderCard(order, isCompleted) {
        const mins = order.elapsed_minutes || 0;
        const secs = String(order.elapsed_seconds || 0).padStart(2, "0");
        const timerClass = getTimerClass(mins);
        const stateClass = order.kds_state === "in_progress" ? "state-progress" : "state-new";

        // Table or takeaway label
        let locationLabel = "";
        if (order.is_takeaway) {
            locationLabel = `<span class="kds-takeaway">外帶</span>`;
        } else if (order.table_name) {
            locationLabel = `桌 ${escapeHtml(order.table_name)}`;
        } else {
            locationLabel = order.name;
        }

        let linesHtml = "";
        for (const line of order.lines) {
            const doneClass = line.is_done ? "line-done" : "";
            const noteHtml = line.customer_note
                ? `<div class="kds-line-note">${escapeHtml(line.customer_note)}</div>`
                : "";
            linesHtml += `
            <div class="kds-line ${doneClass}" data-order-id="${order.id}" data-line-id="${line.id}">
                <span class="kds-line-check">${line.is_done ? '☑' : '☐'}</span>
                <span class="kds-line-qty">${line.qty}x</span>
                <span class="kds-line-name">${escapeHtml(line.product_name)}</span>
                ${noteHtml}
            </div>`;
        }

        // General note
        let generalNoteHtml = "";
        if (order.general_note) {
            generalNoteHtml = `<div class="kds-general-note">📝 ${escapeHtml(order.general_note)}</div>`;
        }

        const bumpBtn = isCompleted
            ? `<button class="kds-btn kds-btn-recall" data-action="recall-order" data-order-id="${order.id}">↩️ 召回</button>`
            : `<button class="kds-btn kds-btn-bump" data-action="bump" data-order-id="${order.id}">完成出餐</button>`;

        return `
        <div class="kds-card ${stateClass}" data-order-id="${order.id}">
            <div class="kds-card-header">
                <div class="kds-location">${locationLabel}</div>
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

    function renderAllDayView() {
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

        if (sorted.length === 0) {
            return `
            <div class="kds-empty">
                <div class="kds-empty-icon">📊</div>
                <div class="kds-empty-text">目前沒有訂單</div>
            </div>`;
        }

        let html = `
        <div class="kds-allday">
            <div class="kds-allday-header">
                <h2>📊 總覽 — All Day Summary</h2>
                <button class="kds-btn kds-btn-header" data-action="back-active">← 返回</button>
            </div>
            <div class="kds-allday-grid">`;

        for (const item of sorted) {
            const remaining = item.qty - item.done;
            const doneClass = remaining === 0 ? "allday-done" : "";
            html += `
            <div class="kds-allday-item ${doneClass}">
                <span class="kds-allday-qty">${item.qty}</span>
                <span class="kds-allday-name">${escapeHtml(item.name)}</span>
                ${item.done > 0 ? `<span class="kds-allday-progress">(${item.done}/${item.qty} done)</span>` : ""}
            </div>`;
        }

        html += "</div></div>";
        return html;
    }

    function renderCompletedView() {
        let html = `
        <div class="kds-completed-view">
            <div class="kds-allday-header">
                <h2>✅ 已完成 — Completed Orders</h2>
                <button class="kds-btn kds-btn-header" data-action="back-active">← 返回</button>
            </div>`;

        if (completedOrders.length === 0) {
            html += `
            <div class="kds-empty">
                <div class="kds-empty-icon">✅</div>
                <div class="kds-empty-text">沒有已完成的訂單</div>
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

        // Header buttons
        document.querySelectorAll('[data-action="allday"]').forEach((btn) => {
            btn.addEventListener("click", () => {
                currentView = currentView === "allday" ? "active" : "allday";
                render();
            });
        });

        document.querySelectorAll('[data-action="completed"]').forEach((btn) => {
            btn.addEventListener("click", async () => {
                if (currentView === "completed") {
                    currentView = "active";
                    render();
                } else {
                    currentView = "completed";
                    await fetchCompleted();
                }
            });
        });

        document.querySelectorAll('[data-action="back-active"]').forEach((btn) => {
            btn.addEventListener("click", () => {
                currentView = "active";
                render();
            });
        });

        document.querySelectorAll('[data-action="recall-order"]').forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const orderId = parseInt(btn.dataset.orderId);
                recallOrder(orderId);
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
        render(); // Show empty state
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
