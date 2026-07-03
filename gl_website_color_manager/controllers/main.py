# -*- coding: utf-8 -*-
import hashlib
import re
from collections import defaultdict
from urllib.parse import quote_plus

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


def _row_context_hash(row):
    if not isinstance(row, dict):
        return False
    parts = [
        row.get('source_type') or '',
        row.get('selector') or '',
        row.get('property_name') or '',
        row.get('css_variable') or '',
        row.get('normalized') or row.get('normalized_color') or row.get('original_color') or row.get('color_value') or '',
        row.get('raw_value') or '',
        row.get('matched_value') or '',
    ]
    payload = '\x1f'.join(str(part) for part in parts)
    return hashlib.sha1(payload.encode('utf-8', errors='ignore')).hexdigest()


def _clean_row(row):
    if not isinstance(row, dict):
        return False
    normalized = _normalize_hex(row.get('normalized_color') or row.get('original_color') or row.get('color_value'))
    if not normalized:
        return False
    source_type = row.get('source_type') or 'computed'
    if source_type not in ('computed', 'css_variable', 'stylesheet'):
        source_type = 'computed'
    clean = {
        'normalized': normalized,
        'selector': (row.get('selector') or ':root').strip()[:700],
        'property_name': (row.get('property_name') or '').strip().lower()[:80],
        'source_type': source_type,
        'css_variable': (row.get('css_variable') or '').strip()[:120],
        'raw_value': (row.get('raw_value') or row.get('matched_value') or '').strip()[:1000],
        'matched_value': (row.get('matched_value') or row.get('raw_value') or '').strip()[:300],
        'sample_text': (row.get('sample_text') or '').strip()[:240],
        'picked': bool(row.get('picked')),
        'picked_label': (row.get('picked_label') or row.get('picked_sample_text') or '').strip()[:240],
        'occurrence_count': row.get('occurrence_count') or 1,
    }
    clean['override_context_key'] = _row_context_hash(clean)
    return clean


def _append_css_record(record, replacement, root_vars, simple_rules, complex_rules):
    selector = _safe_selector(record.selector)
    prop = _safe_property((record.css_variable or record.property_name or '').strip())
    if not selector or not prop:
        return

    raw_value = record.raw_value or record.matched_value or ''
    matched_value = record.matched_value or record.raw_value or ''
    alpha = _extract_alpha(matched_value)
    replacement_with_alpha = _hex_to_rgba(replacement, alpha)

    if prop.startswith('--') or record.source_type == 'css_variable':
        var_name = _safe_property(record.css_variable or record.property_name)
        if not var_name or not var_name.startswith('--'):
            return
        if raw_value and matched_value and matched_value in raw_value and raw_value.strip() != matched_value.strip():
            value = raw_value.replace(matched_value, replacement_with_alpha)
        else:
            value = replacement_with_alpha
        simple_rules[selector][var_name] = value
        return

    if prop in SIMPLE_PROPERTIES or prop.endswith('-color') or prop in ('fill', 'stroke'):
        simple_rules[selector][prop] = replacement_with_alpha
        return

    if prop in COMPLEX_PROPERTIES and raw_value and matched_value and matched_value in raw_value:
        key = (selector, prop, raw_value)
        current = complex_rules.get(key, raw_value)
        complex_rules[key] = current.replace(matched_value, replacement_with_alpha)


def _render_css_blocks(root_vars, simple_rules, complex_rules):
    lines = []
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

    complex_by_selector = defaultdict(dict)
    for (selector, prop, _raw_value), value in complex_rules.items():
        complex_by_selector[selector][prop] = value
    for selector, props in sorted(complex_by_selector.items()):
        lines.append('%s {' % selector)
        for prop, value in sorted(props.items()):
            lines.append('  %s: %s !important;' % (prop, value))
        lines.append('}')
    return lines



class GlWebsiteColorManagerController(http.Controller):

    @http.route('/gl_color_manager/scan_payload', type='json', auth='user', methods=['POST'], csrf=False)
    def scan_payload(self, website_id=None, url=None, colors=None, selection_mode=False, picked_selector=None, picked_sample_text=None, **kwargs):
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
            'picked_selector': (picked_selector or '').strip()[:700],
            'picked_sample_text': (picked_sample_text or '').strip()[:240],
        })

        colors_seen = set()
        picked_swatch_ids = set()
        picked_entry_ids = set()
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
            picked = bool(row.get('picked'))
            picked_label = (row.get('picked_label') or row.get('picked_sample_text') or picked_sample_text or sample_text or '').strip()[:240]
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
            if picked:
                vals.update({
                    'picked': True,
                    'picked_at': now,
                    'picked_label': picked_label,
                })
                picked_swatch_ids.add(swatch.id)

            if entry:
                entry.write(vals)
                if picked:
                    picked_entry_ids.add(entry.id)
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
                        entry = Entry.create(vals)
                        if picked:
                            picked_entry_ids.add(entry.id)
                except Exception:
                    # Continue scanning even if a single unusual selector/value cannot be stored.
                    continue
            entries_written += 1

        scan_vals = {
            'color_count': len(colors_seen),
            'entry_count': entries_written,
            'message': 'Bereichsauswahl gespeichert.' if picked_swatch_ids else 'Scan abgeschlossen.',
        }
        if picked_swatch_ids:
            scan_vals['picked_swatch_ids'] = [(6, 0, list(picked_swatch_ids))]
        scan.write(scan_vals)

        try:
            action_id = request.env.ref('gl_website_color_manager.action_gl_website_color_swatch').id
            backend_url = '/web#action=%s&model=gl.website.color.swatch&view_type=list' % action_id
        except Exception:
            action_id = False
            backend_url = '/web#model=gl.website.color.swatch&view_type=list'

        try:
            scan_action_id = request.env.ref('gl_website_color_manager.action_gl_website_color_scan_session').id
            picked_backend_url = '/web#id=%s&action=%s&model=gl.website.color.scan.session&view_type=form' % (scan.id, scan_action_id)
        except Exception:
            picked_backend_url = '/web#id=%s&model=gl.website.color.scan.session&view_type=form' % scan.id

        try:
            entry_action_id = request.env.ref('gl_website_color_manager.action_gl_website_color_entry').id
            picked_domain = quote_plus(str([('scan_session_id', '=', scan.id), ('picked', '=', True)]))
            picked_entries_url = '/web#action=%s&model=gl.website.color.entry&view_type=list&domain=%s' % (entry_action_id, picked_domain)
        except Exception:
            picked_entries_url = picked_backend_url

        return {
            'ok': True,
            'scan_id': scan.id,
            'color_count': len(colors_seen),
            'entry_count': entries_written,
            'picked_color_count': len(picked_swatch_ids),
            'picked_entry_count': len(picked_entry_ids),
            'backend_url': backend_url,
            'picked_backend_url': picked_backend_url if picked_swatch_ids else False,
            'picked_entries_url': picked_entries_url if picked_swatch_ids else False,
        }

    @http.route('/gl_color_manager/apply_override', type='json', auth='user', methods=['POST'], csrf=False)
    def apply_override(self, website_id=None, original_color=None, replacement_color=None, colors=None, context_key=None, picked_selector=None, picked_sample_text=None, **kwargs):
        if not _is_allowed_user():
            return {'ok': False, 'error': 'not_allowed'}

        Website = request.env['website'].sudo()
        website = Website.browse(int(website_id or 0)).exists()
        if not website:
            website = getattr(request, 'website', False)
        if not website:
            return {'ok': False, 'error': 'missing_website'}

        original = _normalize_hex(original_color)
        replacement = _normalize_hex(replacement_color)
        if not original or not replacement:
            return {'ok': False, 'error': 'invalid_color'}

        rows = colors or []
        if not isinstance(rows, list):
            rows = []
        rows = rows[:10000]

        Override = request.env['gl.website.color.override'].sudo()
        now = fields.Datetime.now()
        override_ids = set()
        cleaned_rows = []

        for raw_row in rows:
            row = _clean_row(raw_row)
            if not row or row['normalized'] != original:
                continue
            cleaned_rows.append(row)
            selector = row['selector'] or ':root'
            prop = row['property_name'] or row['css_variable'] or ''
            if not selector or not prop:
                continue
            domain = [
                ('website_id', '=', website.id),
                ('source_type', '=', row['source_type']),
                ('selector', '=', selector),
                ('property_name', '=', prop),
                ('css_variable', '=', row['css_variable']),
                ('original_color', '=', original),
                ('raw_value', '=', row['raw_value']),
                ('matched_value', '=', row['matched_value']),
                ('override_context_key', '=', row.get('override_context_key') or False),
            ]
            vals = {
                'website_id': website.id,
                'active': True,
                'source_type': row['source_type'],
                'selector': selector,
                'property_name': prop,
                'css_variable': row['css_variable'],
                'original_color': original,
                'replacement_color': replacement,
                'override_context_key': row.get('override_context_key') or False,
                'raw_value': row['raw_value'],
                'matched_value': row['matched_value'],
                'sample_text': row['sample_text'],
                'picked_selector': (picked_selector or '').strip()[:700],
                'picked_label': (picked_sample_text or row['picked_label'] or row['sample_text'] or '').strip()[:240],
                'last_seen': now,
            }
            override = Override.search(domain, limit=1)
            try:
                with request.env.cr.savepoint():
                    if override:
                        override.write(vals)
                    else:
                        override = Override.create(vals)
                    override_ids.add(override.id)
            except Exception:
                continue

        # Older picker versions could save broader stylesheet/CSS-variable rows
        # for the same clicked area. The picker is now intentionally specific: a
        # saved overlay change should only target the exact computed element
        # selector. Deactivate old broad direct overrides for the same click/color
        # once a new specific row is saved.
        if override_ids:
            picked = (picked_selector or '').strip()[:700]
            saved_props = set((row.get('property_name') or row.get('css_variable') or '') for row in cleaned_rows)
            legacy_domain = [
                ('website_id', '=', website.id),
                ('original_color', '=', original),
                ('active', '=', True),
            ]
            if picked:
                legacy_domain.append(('picked_selector', '=', picked))
            legacy = Override.search(legacy_domain)
            if legacy:
                legacy.filtered(lambda rec: rec.id not in override_ids and (
                    not saved_props or rec.property_name in saved_props or rec.css_variable in saved_props or rec.source_type in ('stylesheet', 'css_variable')
                )).write({'active': False})

        version = request.env['gl.website.color.swatch'].sudo().get_css_cache_key(website.id)
        css_url = '/gl_color_manager/css/%s.css?v=%s' % (website.id, version)
        return {
            'ok': True,
            'override_count': len(override_ids),
            'css_url': css_url,
            'css_version': version,
        }

    @http.route('/gl_color_manager/undo_override', type='json', auth='user', methods=['POST'], csrf=False)
    def undo_override(self, website_id=None, original_color=None, colors=None, context_key=None, picked_selector=None, picked_sample_text=None, **kwargs):
        if not _is_allowed_user():
            return {'ok': False, 'error': 'not_allowed'}

        Website = request.env['website'].sudo()
        website = Website.browse(int(website_id or 0)).exists()
        if not website:
            website = getattr(request, 'website', False)
        if not website:
            return {'ok': False, 'error': 'missing_website'}

        original = _normalize_hex(original_color)
        rows = colors or []
        if not isinstance(rows, list):
            rows = []
        rows = rows[:10000]

        Override = request.env['gl.website.color.override'].sudo()
        deactivated_ids = set()

        for raw_row in rows:
            row = _clean_row(raw_row)
            if not row:
                continue
            row_original = row['normalized']
            if original and row_original != original:
                continue
            selector = row['selector'] or ':root'
            prop = row['property_name'] or row['css_variable'] or ''
            domain = [
                ('website_id', '=', website.id),
                ('source_type', '=', row['source_type']),
                ('selector', '=', selector),
                ('property_name', '=', prop),
                ('css_variable', '=', row['css_variable']),
                ('original_color', '=', row_original),
                ('raw_value', '=', row['raw_value']),
                ('matched_value', '=', row['matched_value']),
                ('override_context_key', '=', row.get('override_context_key') or False),
                ('active', '=', True),
            ]
            matches = Override.search(domain)
            if not matches:
                fallback_domain = [
                    ('website_id', '=', website.id),
                    ('source_type', '=', row['source_type']),
                    ('selector', '=', selector),
                    ('property_name', '=', prop),
                    ('css_variable', '=', row['css_variable']),
                    ('active', '=', True),
                ]
                picked = (picked_selector or '').strip()[:700]
                if picked:
                    fallback_domain.append(('picked_selector', '=', picked))
                matches = Override.search(fallback_domain)
            if matches:
                matches.write({'active': False})
                deactivated_ids.update(matches.ids)

        # Safety fallback for rows created before exact context keys existed.
        if not deactivated_ids and original:
            legacy_domain = [
                ('website_id', '=', website.id),
                ('original_color', '=', original),
                ('active', '=', True),
                ('override_context_key', '=', False),
            ]
            picked = (picked_selector or '').strip()[:700]
            if picked:
                legacy_domain.append(('picked_selector', '=', picked))
            legacy = Override.search(legacy_domain)
            if legacy:
                legacy.write({'active': False})
                deactivated_ids.update(legacy.ids)

        version = request.env['gl.website.color.swatch'].sudo().get_css_cache_key(website.id)
        css_url = '/gl_color_manager/css/%s.css?v=%s' % (website.id, version)
        return {
            'ok': True,
            'deactivated_count': len(deactivated_ids),
            'css_url': css_url,
            'css_version': version,
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
                _append_css_record(entry, replacement, root_vars, simple_rules, complex_rules)

        lines.extend(_render_css_blocks(root_vars, simple_rules, complex_rules))

        # Direct overrides come last and therefore win over the older color-swatch
        # overrides. They are created by the on-page picker and target the concrete
        # CSS reference that was clicked, not every occurrence of the same color.
        Override = request.env['gl.website.color.override'].sudo()
        overrides = Override.search([
            ('website_id', '=', website_id),
            ('active', '=', True),
            ('replacement_color', '!=', False),
        ])
        root_vars = {}
        simple_rules = defaultdict(dict)
        complex_rules = {}
        for override in overrides:
            replacement = _normalize_hex(override.replacement_color)
            if replacement:
                _append_css_record(override, replacement, root_vars, simple_rules, complex_rules)
        direct_lines = _render_css_blocks(root_vars, simple_rules, complex_rules)
        if direct_lines:
            lines.append('/* Direct on-page picker overrides */')
            lines.extend(direct_lines)

        body = '\n'.join(lines) + '\n'
        response = request.make_response(body)
        response.headers['Content-Type'] = 'text/css; charset=utf-8'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
