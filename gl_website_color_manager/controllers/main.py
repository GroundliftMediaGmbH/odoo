# -*- coding: utf-8 -*-
import re
from collections import defaultdict

from odoo import http, fields
from odoo.http import request

HEX_RE = re.compile(r'^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8}|[0-9a-fA-F]{3})$')
SAFE_SELECTOR_FORBIDDEN_RE = re.compile(r'[{};]')
SAFE_PROP_RE = re.compile(r'^[a-zA-Z-]+$')
SAFE_VAR_RE = re.compile(r'^--[a-zA-Z0-9_-]+$')

SIMPLE_PROPERTIES = {
    'color',
    'background-color',
    'border-color',
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
}
COMPLEX_PROPERTIES = {
    'background',
    'background-image',
    'box-shadow',
    'text-shadow',
}


def _normalize_hex(value):
    if not value:
        return False
    value = str(value).strip().lower()
    if not value.startswith('#'):
        value = '#' + value
    if not HEX_RE.match(value):
        return False
    if len(value) == 4:
        value = '#' + ''.join(ch * 2 for ch in value[1:])
    return value


def _is_allowed_user():
    user = request.env.user
    for group in ('base.group_system', 'website.group_website_designer'):
        try:
            if user.has_group(group):
                return True
        except Exception:
            continue
    return False


def _safe_selector(selector):
    selector = (selector or '').strip()
    if not selector or len(selector) > 700:
        return False
    if SAFE_SELECTOR_FORBIDDEN_RE.search(selector):
        return False
    return selector


def _safe_property(prop):
    prop = (prop or '').strip().lower()
    if not prop or len(prop) > 80:
        return False
    if prop.startswith('--'):
        return prop if SAFE_VAR_RE.match(prop) else False
    if not SAFE_PROP_RE.match(prop):
        return False
    if prop in SIMPLE_PROPERTIES or prop in COMPLEX_PROPERTIES:
        return prop
    if prop.endswith('-color') or prop in ('fill', 'stroke'):
        return prop
    return False


def _extract_alpha(css_color):
    if not css_color:
        return 1.0
    match = re.search(r'rgba?\(([^)]+)\)', css_color, re.I)
    if not match:
        return 1.0
    content = match.group(1).replace('/', ',')
    parts = [p.strip() for p in content.split(',') if p.strip()]
    if len(parts) < 4:
        return 1.0
    try:
        alpha_raw = parts[3]
        if alpha_raw.endswith('%'):
            return max(0.0, min(1.0, float(alpha_raw[:-1]) / 100.0))
        return max(0.0, min(1.0, float(alpha_raw)))
    except Exception:
        return 1.0


def _hex_to_rgba(color, alpha):
    color = _normalize_hex(color)
    if not color or alpha >= 0.999:
        return color
    if len(color) == 9:
        color = color[:7]
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    return 'rgba(%s, %s, %s, %.4g)' % (r, g, b, alpha)


class GlWebsiteColorManagerController(http.Controller):

    @http.route('/gl_color_manager/scan_payload', type='json', auth='user', methods=['POST'], csrf=False)
    def scan_payload(self, website_id=None, url=None, colors=None, **kwargs):
        if not _is_allowed_user():
            return {'ok': False, 'error': 'not_allowed'}

        Website = request.env['website'].sudo()
        website = Website.browse(int(website_id or 0)).exists()
        if not website:
            website = getattr(request, 'website', False)
        if not website:
            return {'ok': False, 'error': 'missing_website'}

        rows = colors or []
        if not isinstance(rows, list):
            rows = []
        rows = rows[:10000]

        Scan = request.env['gl.website.color.scan.session'].sudo()
        Swatch = request.env['gl.website.color.swatch'].sudo()
        Entry = request.env['gl.website.color.entry'].sudo()

        scan = Scan.create({
            'website_id': website.id,
            'url': url,
            'scan_date': fields.Datetime.now(),
            'state': 'done',
        })

        colors_seen = set()
        entries_written = 0
        now = fields.Datetime.now()

        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = _normalize_hex(row.get('normalized_color') or row.get('original_color') or row.get('color_value'))
            if not normalized:
                continue
            selector = (row.get('selector') or ':root').strip()[:700]
            prop = (row.get('property_name') or '').strip().lower()[:80]
            source_type = row.get('source_type') or 'computed'
            if source_type not in ('computed', 'css_variable', 'stylesheet'):
                source_type = 'computed'
            css_variable = (row.get('css_variable') or '').strip()[:120]
            raw_value = (row.get('raw_value') or row.get('matched_value') or '').strip()[:1000]
            matched_value = (row.get('matched_value') or row.get('raw_value') or '').strip()[:300]
            sample_text = (row.get('sample_text') or '').strip()[:240]
            try:
                occurrence_count = int(row.get('occurrence_count') or 1)
            except Exception:
                occurrence_count = 1

            swatch = Swatch.search([
                ('website_id', '=', website.id),
                ('original_color', '=', normalized),
            ], limit=1)
            if not swatch:
                swatch = Swatch.create({
                    'website_id': website.id,
                    'original_color': normalized,
                })
            colors_seen.add(swatch.id)

            domain = [
                ('swatch_id', '=', swatch.id),
                ('source_type', '=', source_type),
                ('selector', '=', selector),
                ('property_name', '=', prop),
                ('original_color', '=', normalized),
                ('raw_value', '=', raw_value),
                ('matched_value', '=', matched_value),
                ('css_variable', '=', css_variable),
            ]
            entry = Entry.search(domain, limit=1)
            vals = {
                'scan_session_id': scan.id,
                'last_seen': now,
                'occurrence_count': occurrence_count,
                'sample_text': sample_text,
            }
            if entry:
                entry.write(vals)
            else:
                vals.update({
                    'swatch_id': swatch.id,
                    'source_type': source_type,
                    'selector': selector,
                    'property_name': prop,
                    'css_variable': css_variable,
                    'original_color': normalized,
                    'raw_value': raw_value,
                    'matched_value': matched_value,
                    'active': True,
                })
                try:
                    with request.env.cr.savepoint():
                        Entry.create(vals)
                except Exception:
                    # Continue scanning even if a single unusual selector/value cannot be stored.
                    continue
            entries_written += 1

        scan.write({
            'color_count': len(colors_seen),
            'entry_count': entries_written,
            'message': 'Scan abgeschlossen.',
        })

        try:
            action_id = request.env.ref('gl_website_color_manager.action_gl_website_color_swatch').id
            backend_url = '/web#action=%s&model=gl.website.color.swatch&view_type=list' % action_id
        except Exception:
            backend_url = '/web#model=gl.website.color.swatch&view_type=list'

        return {
            'ok': True,
            'scan_id': scan.id,
            'color_count': len(colors_seen),
            'entry_count': entries_written,
            'backend_url': backend_url,
        }

    @http.route('/gl_color_manager/css/<int:website_id>.css', type='http', auth='public', methods=['GET'], csrf=False)
    def color_css(self, website_id, **kwargs):
        Swatch = request.env['gl.website.color.swatch'].sudo()
        swatches = Swatch.search([
            ('website_id', '=', website_id),
            ('active', '=', True),
            ('replacement_color', '!=', False),
        ])

        lines = [
            '/* Groundlift Website Color Manager - generated overrides */',
        ]
        root_vars = {}
        simple_rules = defaultdict(dict)
        complex_rules = {}

        for swatch in swatches:
            replacement = _normalize_hex(swatch.replacement_color)
            if not replacement:
                continue
            for entry in swatch.entry_ids.filtered(lambda e: e.active):
                selector = _safe_selector(entry.selector)
                prop = _safe_property(entry.css_variable or entry.property_name)
                if not selector or not prop:
                    continue

                raw_value = entry.raw_value or entry.matched_value or ''
                matched_value = entry.matched_value or entry.raw_value or ''
                value = replacement
                alpha = _extract_alpha(matched_value)
                replacement_with_alpha = _hex_to_rgba(replacement, alpha)

                if prop.startswith('--') or entry.source_type == 'css_variable':
                    var_name = _safe_property(entry.css_variable or entry.property_name)
                    if not var_name or not var_name.startswith('--'):
                        continue
                    if raw_value and matched_value and matched_value in raw_value and raw_value.strip() != matched_value.strip():
                        value = raw_value.replace(matched_value, replacement_with_alpha)
                    else:
                        value = replacement_with_alpha
                    root_vars[var_name] = value
                    continue

                if prop in SIMPLE_PROPERTIES or prop.endswith('-color') or prop in ('fill', 'stroke'):
                    simple_rules[selector][prop] = replacement_with_alpha
                    continue

                if prop in COMPLEX_PROPERTIES and raw_value and matched_value and matched_value in raw_value:
                    key = (selector, prop, raw_value)
                    current = complex_rules.get(key, raw_value)
                    complex_rules[key] = current.replace(matched_value, replacement_with_alpha)

        if root_vars:
            lines.append(':root {')
            for prop, value in sorted(root_vars.items()):
                lines.append('  %s: %s !important;' % (prop, value))
            lines.append('}')

        for selector, props in sorted(simple_rules.items()):
            if not props:
                continue
            lines.append('%s {' % selector)
            for prop, value in sorted(props.items()):
                lines.append('  %s: %s !important;' % (prop, value))
            lines.append('}')

        # Group complex properties by selector after all replacements have been applied.
        complex_by_selector = defaultdict(dict)
        for (selector, prop, _raw_value), value in complex_rules.items():
            complex_by_selector[selector][prop] = value
        for selector, props in sorted(complex_by_selector.items()):
            lines.append('%s {' % selector)
            for prop, value in sorted(props.items()):
                lines.append('  %s: %s !important;' % (prop, value))
            lines.append('}')

        body = '\n'.join(lines) + '\n'
        response = request.make_response(body)
        response.headers['Content-Type'] = 'text/css; charset=utf-8'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response
