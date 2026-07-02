(function () {
    'use strict';

    const params = new URLSearchParams(window.location.search || '');
    if (!params.has('gl_color_scan')) {
        return;
    }
    if (window.__glWebsiteColorScanStarted) {
        return;
    }
    window.__glWebsiteColorScanStarted = true;

    const COLOR_PROPS = [
        'color',
        'background-color',
        'border-top-color',
        'border-right-color',
        'border-bottom-color',
        'border-left-color',
        'outline-color',
        'text-decoration-color',
        'column-rule-color',
        'caret-color',
        'fill',
        'stroke',
        'background',
        'background-image',
        'box-shadow',
        'text-shadow',
    ];
    const STYLE_RULE_HINTS = ['color', 'background', 'border', 'outline', 'shadow', 'fill', 'stroke', 'caret', 'column-rule'];
    const MAX_ELEMENTS = 3000;
    const MAX_SELECTED_ELEMENTS = 1200;
    const MAX_ROWS = 10000;

    const colorCache = new Map();
    const rows = new Map();
    let pickerCleanup = null;

    function escapeCss(value) {
        if (window.CSS && window.CSS.escape) {
            return window.CSS.escape(value);
        }
        return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function componentToHex(value) {
        const clamped = Math.max(0, Math.min(255, Math.round(value)));
        return clamped.toString(16).padStart(2, '0');
    }

    function rgbaToHex(value) {
        if (!value) {
            return null;
        }
        const match = String(value).match(/rgba?\(([^)]+)\)/i);
        if (!match) {
            return null;
        }
        let content = match[1].trim().replace(/\//g, ',');
        let parts = content.split(',').map((item) => item.trim()).filter(Boolean);
        if (parts.length < 3) {
            parts = content.split(/\s+/).map((item) => item.trim()).filter(Boolean);
        }
        if (parts.length < 3) {
            return null;
        }
        function parseChannel(channel) {
            if (channel.endsWith('%')) {
                return parseFloat(channel) * 2.55;
            }
            return parseFloat(channel);
        }
        const r = parseChannel(parts[0]);
        const g = parseChannel(parts[1]);
        const b = parseChannel(parts[2]);
        let alpha = 1;
        if (parts.length >= 4) {
            const alphaRaw = parts[3];
            alpha = alphaRaw.endsWith('%') ? parseFloat(alphaRaw) / 100 : parseFloat(alphaRaw);
        }
        if ([r, g, b].some((channel) => Number.isNaN(channel)) || Number.isNaN(alpha) || alpha <= 0) {
            return null;
        }
        return '#' + componentToHex(r) + componentToHex(g) + componentToHex(b);
    }

    function expandHex(value) {
        let color = String(value || '').trim().toLowerCase();
        if (!/^#[0-9a-f]{3,8}$/i.test(color)) {
            return null;
        }
        if (color.length === 4) {
            color = '#' + color.slice(1).split('').map((ch) => ch + ch).join('');
        }
        if (color.length === 9) {
            // Keep the visible color stable; alpha is preserved later through matched_value when possible.
            color = color.slice(0, 7);
        }
        if (color.length !== 7) {
            return null;
        }
        return color;
    }

    function normalizeCssColor(value) {
        const raw = String(value || '').trim();
        const lower = raw.toLowerCase();
        if (!raw || lower === 'transparent' || lower === 'none' || lower === 'currentcolor' || lower === 'inherit' || lower === 'initial') {
            return null;
        }
        if (colorCache.has(raw)) {
            return colorCache.get(raw);
        }
        let normalized = null;
        if (raw.startsWith('#')) {
            normalized = expandHex(raw);
        }
        if (!normalized && /^rgba?\(/i.test(raw)) {
            normalized = rgbaToHex(raw);
        }
        if (!normalized && document.body) {
            const probe = document.createElement('span');
            probe.style.color = '';
            probe.style.color = raw;
            if (probe.style.color) {
                probe.style.position = 'absolute';
                probe.style.left = '-99999px';
                probe.style.top = '-99999px';
                document.body.appendChild(probe);
                normalized = rgbaToHex(window.getComputedStyle(probe).color);
                probe.remove();
            }
        }
        colorCache.set(raw, normalized);
        return normalized;
    }

    function extractColors(rawValue) {
        const raw = String(rawValue || '').trim();
        if (!raw) {
            return [];
        }
        const matches = [];
        const patterns = [
            /#[0-9a-fA-F]{3,8}\b/g,
            /rgba?\([^)]*\)/gi,
            /hsla?\([^)]*\)/gi,
        ];
        for (const pattern of patterns) {
            let match;
            while ((match = pattern.exec(raw)) !== null) {
                const matched = match[0].trim();
                const normalized = normalizeCssColor(matched);
                if (normalized) {
                    matches.push({ matched, normalized });
                }
            }
        }
        if (!matches.length) {
            const normalized = normalizeCssColor(raw);
            if (normalized) {
                matches.push({ matched: raw, normalized });
            }
        }
        const seen = new Set();
        return matches.filter((item) => {
            const key = item.matched + '|' + item.normalized;
            if (seen.has(key)) {
                return false;
            }
            seen.add(key);
            return true;
        });
    }

    function cssPath(element) {
        if (!element || element.nodeType !== 1) {
            return '';
        }
        if (element.id && !/^o_/.test(element.id) && !/^gl-color-/.test(element.id)) {
            return '#' + escapeCss(element.id);
        }
        const parts = [];
        let current = element;
        while (current && current.nodeType === 1 && current !== document.documentElement && parts.length < 5) {
            const tag = current.tagName.toLowerCase();
            let segment = tag;
            const classes = Array.from(current.classList || [])
                .filter((cls) => cls && !/^o_editable/.test(cls) && !/^oe_/.test(cls) && !/^ui-/.test(cls) && !/^gl-color-/.test(cls))
                .slice(0, 3);
            if (classes.length) {
                segment += '.' + classes.map(escapeCss).join('.');
            }
            if (current.parentElement) {
                const sameTagSiblings = Array.from(current.parentElement.children).filter((child) => child.tagName === current.tagName);
                if (sameTagSiblings.length > 1) {
                    segment += ':nth-of-type(' + (sameTagSiblings.indexOf(current) + 1) + ')';
                }
            }
            parts.unshift(segment);
            current = current.parentElement;
        }
        return parts.join(' > ') || element.tagName.toLowerCase();
    }

    function sampleText(element) {
        if (!element) {
            return '';
        }
        const text = (element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim();
        if (text) {
            return text.slice(0, 180);
        }
        return element.getAttribute('aria-label') || element.getAttribute('alt') || element.tagName.toLowerCase();
    }

    function addRow(row) {
        if (!row || !row.normalized_color || rows.size >= MAX_ROWS) {
            return;
        }
        const key = [
            row.source_type || '',
            row.selector || '',
            row.property_name || '',
            row.css_variable || '',
            row.normalized_color || '',
            row.raw_value || '',
            row.matched_value || '',
            row.picked ? 'picked' : '',
        ].join('||');
        if (rows.has(key)) {
            rows.get(key).occurrence_count += 1;
            return;
        }
        rows.set(key, Object.assign({ occurrence_count: 1 }, row));
    }

    function scanComputedStylesForElements(elements, pickedInfo) {
        for (const element of elements) {
            if (!element || element.nodeType !== 1 || element.id === 'gl-color-scan-overlay' || element.id === 'gl-color-pick-highlight') {
                continue;
            }
            const style = window.getComputedStyle(element);
            if (!style || style.display === 'none' || style.visibility === 'hidden') {
                continue;
            }
            const selector = cssPath(element);
            const label = sampleText(element);
            for (const prop of COLOR_PROPS) {
                const rawValue = style.getPropertyValue(prop);
                const foundColors = extractColors(rawValue);
                for (const color of foundColors) {
                    addRow({
                        source_type: 'computed',
                        selector: selector,
                        property_name: prop,
                        css_variable: '',
                        color_value: color.normalized,
                        normalized_color: color.normalized,
                        raw_value: rawValue.trim(),
                        matched_value: color.matched,
                        sample_text: label,
                        picked: !!pickedInfo,
                        picked_selector: pickedInfo ? pickedInfo.selector : '',
                        picked_sample_text: pickedInfo ? pickedInfo.label : '',
                        picked_label: pickedInfo ? pickedInfo.label : '',
                    });
                }
            }
        }
    }

    function scanComputedStyles() {
        const rootItems = [document.documentElement, document.body].filter(Boolean);
        const elementItems = Array.from(document.body ? document.body.querySelectorAll('*') : []).slice(0, MAX_ELEMENTS);
        scanComputedStylesForElements(rootItems.concat(elementItems), null);
    }

    function scanSelectedArea(element) {
        const selected = pickTargetElement(element);
        const selector = cssPath(selected);
        const label = sampleText(selected);
        const childItems = Array.from(selected.querySelectorAll ? selected.querySelectorAll('*') : []).slice(0, MAX_SELECTED_ELEMENTS);
        const elements = [selected].concat(childItems);
        scanComputedStylesForElements(elements, { selector, label });
        return { selector, label, element: selected };
    }

    function scanRootCssVariables() {
        const style = window.getComputedStyle(document.documentElement);
        if (!style) {
            return;
        }
        for (let i = 0; i < style.length; i += 1) {
            const prop = style[i];
            if (!prop || !prop.startsWith('--')) {
                continue;
            }
            const rawValue = style.getPropertyValue(prop).trim();
            const foundColors = extractColors(rawValue);
            for (const color of foundColors) {
                addRow({
                    source_type: 'css_variable',
                    selector: ':root',
                    property_name: prop,
                    css_variable: prop,
                    color_value: color.normalized,
                    normalized_color: color.normalized,
                    raw_value: rawValue,
                    matched_value: color.matched,
                    sample_text: 'CSS variable ' + prop,
                });
            }
        }
    }

    function propertyLooksColorRelated(prop) {
        if (!prop) {
            return false;
        }
        if (prop.startsWith('--')) {
            return true;
        }
        return STYLE_RULE_HINTS.some((hint) => prop.includes(hint));
    }

    function walkCssRules(ruleList) {
        if (!ruleList) {
            return;
        }
        for (const rule of Array.from(ruleList)) {
            if (rule.cssRules) {
                try {
                    walkCssRules(rule.cssRules);
                } catch (error) {
                    // Ignore restricted nested rules.
                }
            }
            if (!rule.style) {
                continue;
            }
            const selector = rule.selectorText || ':root';
            for (let i = 0; i < rule.style.length; i += 1) {
                const prop = rule.style[i];
                if (!propertyLooksColorRelated(prop)) {
                    continue;
                }
                const rawValue = rule.style.getPropertyValue(prop).trim();
                const foundColors = extractColors(rawValue);
                for (const color of foundColors) {
                    const isVariable = prop.startsWith('--');
                    addRow({
                        source_type: isVariable ? 'css_variable' : 'stylesheet',
                        selector: isVariable ? ':root' : selector,
                        property_name: prop,
                        css_variable: isVariable ? prop : '',
                        color_value: color.normalized,
                        normalized_color: color.normalized,
                        raw_value: rawValue,
                        matched_value: color.matched,
                        sample_text: isVariable ? ('CSS variable ' + prop) : ('CSS rule ' + selector),
                    });
                }
            }
        }
    }

    function scanStylesheets() {
        for (const sheet of Array.from(document.styleSheets || [])) {
            try {
                walkCssRules(sheet.cssRules);
            } catch (error) {
                // Cross-origin or browser protected stylesheets cannot be inspected.
            }
        }
    }

    function showOverlay(message, state, options) {
        const opts = options || {};
        let overlay = document.getElementById('gl-color-scan-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'gl-color-scan-overlay';
            overlay.style.cssText = [
                'position:fixed',
                'right:18px',
                'bottom:18px',
                'z-index:2147483647',
                'max-width:450px',
                'padding:16px 18px',
                'border-radius:12px',
                'box-shadow:0 10px 35px rgba(0,0,0,.22)',
                'background:#111',
                'color:#fff',
                'font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif',
            ].join(';');
            document.body.appendChild(overlay);
        }
        const accent = state === 'error' ? '#ff4d4f' : state === 'done' ? '#52c41a' : state === 'pick' ? '#f5d76e' : '#ffffff';
        const links = [];
        if (opts.pickedEntriesUrl) {
            links.push('<a style="color:#fff;text-decoration:underline" href="' + escapeHtml(opts.pickedEntriesUrl) + '">Angeklickte Farben direkt bearbeiten</a>');
        }
        if (opts.pickedBackendUrl) {
            links.push('<a style="color:#fff;text-decoration:underline" href="' + escapeHtml(opts.pickedBackendUrl) + '">Auswahl-Scan öffnen</a>');
        }
        if (opts.backendUrl) {
            links.push('<a style="color:#fff;text-decoration:underline" href="' + escapeHtml(opts.backendUrl) + '">Alle Farben im Backend öffnen</a>');
        }
        overlay.innerHTML = '<div style="font-weight:700;margin-bottom:4px;color:' + accent + '">Groundlift Farbscan</div>' +
            '<div>' + escapeHtml(message) + '</div>' +
            (links.length ? '<div style="display:grid;gap:6px;margin-top:10px">' + links.map((link) => '<div>' + link + '</div>').join('') + '</div>' : '') +
            (opts.showPickButton ? '<div style="margin-top:12px"><button id="gl-color-pick-start" type="button" style="border:0;border-radius:8px;padding:8px 11px;background:#fff;color:#111;font-weight:700;cursor:pointer">Bereich auf der Seite anklicken</button></div>' : '') +
            (opts.showCancelButton ? '<div style="margin-top:12px"><button id="gl-color-pick-cancel" type="button" style="border:1px solid rgba(255,255,255,.35);border-radius:8px;padding:7px 10px;background:transparent;color:#fff;cursor:pointer">Auswahl abbrechen</button></div>' : '');
        const pickButton = overlay.querySelector('#gl-color-pick-start');
        if (pickButton) {
            pickButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                startElementPicker();
            });
        }
        const cancelButton = overlay.querySelector('#gl-color-pick-cancel');
        if (cancelButton) {
            cancelButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                stopElementPicker();
                showOverlay('Auswahl abgebrochen. Du kannst den Bereichsmodus erneut starten.', 'done', { showPickButton: true });
            });
        }
        return overlay;
    }

    function pickTargetElement(target) {
        if (!target || target.nodeType !== 1) {
            return document.body || document.documentElement;
        }
        if (target.closest && target.closest('#gl-color-scan-overlay')) {
            return document.body || document.documentElement;
        }
        const exact = target.closest('a, button, .btn, img, svg, input, textarea, select');
        if (exact) {
            return exact;
        }
        return target.closest('section, header, footer, article, .o_colored_level, [class*="s_"], .card, .container, .row, main') || target;
    }

    function ensureHighlight() {
        let box = document.getElementById('gl-color-pick-highlight');
        if (!box) {
            box = document.createElement('div');
            box.id = 'gl-color-pick-highlight';
            box.style.cssText = [
                'position:fixed',
                'z-index:2147483646',
                'pointer-events:none',
                'border:3px solid #f5d76e',
                'box-shadow:0 0 0 99999px rgba(0,0,0,.18),0 0 22px rgba(0,0,0,.25)',
                'border-radius:6px',
                'transition:all .05s linear',
            ].join(';');
            document.body.appendChild(box);
        }
        return box;
    }

    function moveHighlight(element) {
        const box = ensureHighlight();
        const rect = element.getBoundingClientRect();
        box.style.left = Math.max(0, rect.left) + 'px';
        box.style.top = Math.max(0, rect.top) + 'px';
        box.style.width = Math.max(1, rect.width) + 'px';
        box.style.height = Math.max(1, rect.height) + 'px';
    }

    function stopElementPicker() {
        if (pickerCleanup) {
            pickerCleanup();
            pickerCleanup = null;
        }
        const highlight = document.getElementById('gl-color-pick-highlight');
        if (highlight) {
            highlight.remove();
        }
        document.documentElement.style.cursor = '';
    }

    function startElementPicker() {
        stopElementPicker();
        showOverlay('Auswahlmodus aktiv: Bewege die Maus über den gewünschten Bereich und klicke einmal. ESC bricht ab.', 'pick', { showCancelButton: true });
        document.documentElement.style.cursor = 'crosshair';

        const onMove = (event) => {
            const overlay = document.getElementById('gl-color-scan-overlay');
            if (overlay && overlay.contains(event.target)) {
                return;
            }
            moveHighlight(pickTargetElement(event.target));
        };
        const onClick = (event) => {
            const overlay = document.getElementById('gl-color-scan-overlay');
            if (overlay && overlay.contains(event.target)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            const selected = pickTargetElement(event.target);
            stopElementPicker();
            runSelectedScan(selected);
        };
        const onKey = (event) => {
            if (event.key === 'Escape') {
                stopElementPicker();
                showOverlay('Auswahl abgebrochen. Du kannst den Bereichsmodus erneut starten.', 'done', { showPickButton: true });
            }
        };
        document.addEventListener('mousemove', onMove, true);
        document.addEventListener('click', onClick, true);
        document.addEventListener('keydown', onKey, true);
        pickerCleanup = () => {
            document.removeEventListener('mousemove', onMove, true);
            document.removeEventListener('click', onClick, true);
            document.removeEventListener('keydown', onKey, true);
        };
    }

    async function postScan(extraParams) {
        const websiteId = window.GroundliftColorManager && window.GroundliftColorManager.websiteId;
        const payload = {
            jsonrpc: '2.0',
            method: 'call',
            params: Object.assign({
                website_id: websiteId,
                url: window.location.href,
                colors: Array.from(rows.values()),
            }, extraParams || {}),
        };
        const response = await window.fetch('/gl_color_manager/scan_payload', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }
        const json = await response.json();
        if (json.error) {
            throw new Error(json.error.message || 'JSON-RPC error');
        }
        const result = json.result || {};
        if (!result.ok) {
            throw new Error(result.error || 'Scan konnte nicht gespeichert werden.');
        }
        return result;
    }

    async function runScan() {
        showOverlay('Scan läuft. Bitte diese Seite kurz geöffnet lassen …', 'running');
        try {
            rows.clear();
            scanComputedStyles();
            scanRootCssVariables();
            scanStylesheets();
            const result = await postScan({ selection_mode: false });
            showOverlay(
                'Fertig: ' + result.color_count + ' Farben und ' + result.entry_count + ' Fundstellen gespeichert.',
                'done',
                { backendUrl: result.backend_url, showPickButton: true }
            );
        } catch (error) {
            showOverlay('Fehler: ' + (error && error.message ? error.message : error), 'error', { showPickButton: true });
        }
    }

    async function runSelectedScan(selectedElement) {
        showOverlay('Bereich wird analysiert und gespeichert …', 'running');
        try {
            rows.clear();
            const pickedInfo = scanSelectedArea(selectedElement);
            const result = await postScan({
                selection_mode: true,
                picked_selector: pickedInfo.selector,
                picked_sample_text: pickedInfo.label,
            });
            showOverlay(
                'Fertig: ' + result.picked_color_count + ' Farben im angeklickten Bereich gefunden.',
                'done',
                {
                    pickedEntriesUrl: result.picked_entries_url,
                    pickedBackendUrl: result.picked_backend_url,
                    backendUrl: result.backend_url,
                    showPickButton: true,
                }
            );
        } catch (error) {
            showOverlay('Fehler bei der Bereichsauswahl: ' + (error && error.message ? error.message : error), 'error', { showPickButton: true });
        }
    }

    function boot() {
        if (params.has('gl_color_pick')) {
            window.setTimeout(startElementPicker, 500);
        } else {
            window.setTimeout(runScan, 500);
        }
    }

    if (document.readyState === 'complete') {
        boot();
    } else {
        window.addEventListener('load', boot, { once: true });
    }
}());
