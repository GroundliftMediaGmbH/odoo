/** @odoo-module **/
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// Informational display only. Never changes cash counts or session closing logic.
const closingTipsService = {
    start(env) {
        let lastSession = null;
        let pending = false;
        let previousSignature = "";
        const formatAmount = (value, info) => {
            const number = Number(value || 0).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            return info.currency_position === "before" ? `${info.currency} ${number}` : `${number} ${info.currency}`;
        };
        const findSession = () => {
            const pos = env.services.pos;
            const raw = pos?.session?.id || pos?.pos_session?.id || pos?.config?.current_session_id?.id || pos?.config?.current_session_id;
            return Number(raw) || null;
        };
        const inspect = async () => {
            const dialogs = [...document.querySelectorAll('.modal, [role="dialog"]')];
            const dialog = dialogs.find((node) => {
                const title = node.querySelector('.modal-title, h4, h5, .dialog-title')?.textContent || '';
                return /Kassenabschluss|Closing Register|Close Register|Closing Control/i.test(title);
            });
            if (!dialog) {
                previousSignature = "";
                return;
            }
            const sessionId = findSession();
            if (!sessionId || pending) return;
            const signature = `${sessionId}:${dialog.querySelector('.gl-pos-tips-summary') ? 'shown' : 'missing'}`;
            if (signature === previousSignature || dialog.querySelector('.gl-pos-tips-summary')) return;
            previousSignature = signature;
            pending = true;
            try {
                const info = await rpc('/gl_pos_closing_tips/summary', {session_id: sessionId});
                if (info.error || !dialog.isConnected || dialog.querySelector('.gl-pos-tips-summary')) return;
                const section = document.createElement('section');
                section.className = 'gl-pos-tips-summary';
                section.style.cssText = 'margin:12px 4px;padding:10px 8px;border-top:1px solid var(--border-color,#777);font-size:13px;';
                const appendRow = (label, amount, bold = false) => {
                    const row = document.createElement('div');
                    row.style.cssText = `display:flex;justify-content:space-between;gap:14px;margin:4px 0;${bold ? 'font-weight:700;' : ''}`;
                    const lhs = document.createElement('span');
                    const rhs = document.createElement('span');
                    lhs.textContent = label;
                    rhs.textContent = formatAmount(amount, info);
                    row.append(lhs, rhs);
                    section.appendChild(row);
                };
                appendRow('Trinkgeld gesamt (bereits in Zahlungen enthalten)', info.total, true);
                appendRow('Davon bar', info.cash);
                appendRow('Davon unbar', info.noncash);
                if (info.mixed) appendRow('Nicht eindeutig zuordenbar (gemischte Zahlung)', info.mixed);
                const anchor = dialog.querySelector('.modal-body') || dialog;
                anchor.appendChild(section);
            } catch (error) {
                console.warn('Groundlift tip display unavailable:', error);
                previousSignature = '';
            } finally {
                pending = false;
            }
        };
        let timer = null;
        const observer = new MutationObserver(() => {
            if (timer) return;
            timer = window.setTimeout(() => {
                timer = null;
                inspect();
            }, 120);
        });
        observer.observe(document.body, {childList: true, subtree: true});
        inspect();
        return {stop() {observer.disconnect(); if (timer) window.clearTimeout(timer);}};
    },
};
registry.category('services').add('gl_pos_closing_tips', closingTipsService);
