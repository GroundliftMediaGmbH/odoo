# -*- coding: utf-8 -*-
import re
from urllib.parse import quote_plus

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

HEX_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')


def normalize_hex(value):
    if not value:
        return False
    value = str(value).strip()
    if not value:
        return False
    if not value.startswith('#'):
        value = '#' + value
    if not HEX_RE.match(value):
        return value
    value = value.lower()
    if len(value) == 4:
        value = '#' + ''.join(ch * 2 for ch in value[1:])
    return value


class GlWebsiteColorSwatch(models.Model):
    _name = 'gl.website.color.swatch'
    _description = 'Website Color Swatch'
    _order = 'website_id, original_color'
    _rec_name = 'name'

    name = fields.Char(compute='_compute_name', store=True)
    website_id = fields.Many2one('website', string='Website', required=True, ondelete='cascade', index=True)
    original_color = fields.Char(string='Gefundene Farbe', required=True, index=True, help='Normalisierte gefundene Farbe, meist als #RRGGBB.')
    replacement_color = fields.Char(string='Neue Farbe', help='HTML/CSS-Farbe als Hex-Wert, z. B. #ff6600.')
    active = fields.Boolean(string='Aktiv', default=False, help='Wenn aktiv, wird die neue Farbe im Website-Frontend überschrieben.')
    entry_ids = fields.One2many('gl.website.color.entry', 'swatch_id', string='Fundstellen')
    occurrence_count = fields.Integer(string='Fundstellen', compute='_compute_stats', store=False)
    picked_entry_count = fields.Integer(string='Angeklickte Fundstellen', compute='_compute_stats', store=False)
    last_seen = fields.Datetime(string='Zuletzt gesehen', compute='_compute_stats', store=False)
    notes = fields.Text(string='Notizen')

    _sql_constraints = [
        ('website_original_color_unique', 'unique(website_id, original_color)', 'Diese Farbe existiert für diese Website bereits.'),
    ]

    @api.depends('original_color', 'replacement_color', 'active')
    def _compute_name(self):
        for record in self:
            if record.replacement_color:
                record.name = '%s → %s%s' % (
                    record.original_color or '',
                    record.replacement_color or '',
                    ' (aktiv)' if record.active else '',
                )
            else:
                record.name = record.original_color or _('Farbe')

    def _compute_stats(self):
        for record in self:
            entries = record.entry_ids
            record.occurrence_count = len(entries)
            record.picked_entry_count = len(entries.filtered('picked'))
            record.last_seen = max(entries.mapped('last_seen')) if entries else False

    @api.constrains('original_color', 'replacement_color')
    def _check_hex_colors(self):
        for record in self:
            for field_name in ('original_color', 'replacement_color'):
                value = record[field_name]
                if value and not HEX_RE.match(value.strip()):
                    raise ValidationError(_('%s muss ein Hex-Farbwert sein, z. B. #ff6600.') % record._fields[field_name].string)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('original_color'):
                vals['original_color'] = normalize_hex(vals['original_color'])
            if vals.get('replacement_color'):
                vals['replacement_color'] = normalize_hex(vals['replacement_color'])
                vals.setdefault('active', True)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('original_color'):
            vals['original_color'] = normalize_hex(vals['original_color'])
        if vals.get('replacement_color'):
            vals['replacement_color'] = normalize_hex(vals['replacement_color'])
            if 'active' not in vals:
                vals['active'] = True
        return super().write(vals)

    @api.onchange('replacement_color')
    def _onchange_replacement_color(self):
        for record in self:
            if record.replacement_color:
                record.replacement_color = normalize_hex(record.replacement_color)
                record.active = True

    def action_activate(self):
        for record in self:
            if not record.replacement_color:
                raise ValidationError(_('Bitte zuerst eine neue Farbe eintragen.'))
        self.write({'active': True})

    def action_deactivate(self):
        self.write({'active': False})

    def action_reset(self):
        self.write({'active': False, 'replacement_color': False})

    def action_open_entries(self):
        self.ensure_one()
        action = self.env.ref('gl_website_color_manager.action_gl_website_color_entry').read()[0]
        action['domain'] = [('swatch_id', '=', self.id)]
        action['context'] = {'default_swatch_id': self.id, 'default_website_id': self.website_id.id}
        return action

    @api.model
    def get_css_cache_key(self, website_id):
        """Return a small version key for the dynamic frontend CSS URL.

        Odoo.sh, browsers and intermediary proxies can keep a stylesheet with a
        stable URL longer than expected. The website template appends this key as
        ?v=... so every saved color change gets a fresh URL.
        """
        try:
            website_id = int(website_id or 0)
        except Exception:
            website_id = 0
        if not website_id:
            return '0'
        dates = []
        for table in ('gl_website_color_swatch', 'gl_website_color_entry', 'gl_website_color_override'):
            try:
                self.env.cr.execute('SELECT MAX(write_date) FROM %s WHERE website_id = %%s' % table, [website_id])
                value = self.env.cr.fetchone()[0]
                if value:
                    dates.append(value)
            except Exception:
                # During installation or first template rendering the override
                # table may not exist yet. Failing open keeps the website online.
                continue
        if not dates:
            return '0'
        latest = max(dates)
        try:
            return latest.strftime('%Y%m%d%H%M%S')
        except Exception:
            return str(latest).replace(' ', '').replace(':', '').replace('-', '')[:20]


class GlWebsiteColorOverride(models.Model):
    _name = 'gl.website.color.override'
    _description = 'Website Color Direct Override'
    _order = 'website_id, selector, property_name, original_color'
    _rec_name = 'name'

    name = fields.Char(compute='_compute_name', store=True)
    website_id = fields.Many2one('website', string='Website', required=True, ondelete='cascade', index=True)
    active = fields.Boolean(string='Aktiv', default=True, index=True)
    source_type = fields.Selection([
        ('computed', 'Gerenderter Stil'),
        ('css_variable', 'CSS-Variable'),
        ('stylesheet', 'Stylesheet-Regel'),
    ], string='Quelle', required=True, default='computed', index=True)
    selector = fields.Char(string='CSS-Selektor', required=True)
    property_name = fields.Char(string='CSS-Eigenschaft', required=True)
    css_variable = fields.Char(string='CSS-Variable')
    original_color = fields.Char(string='Originalfarbe', required=True, index=True)
    replacement_color = fields.Char(string='Neue Farbe', required=True, help='HTML/CSS-Farbe als Hex-Wert, z. B. #ff6600.')
    raw_value = fields.Char(string='Originaler CSS-Wert')
    matched_value = fields.Char(string='Gefundener Farbwert im CSS')
    picked_selector = fields.Char(string='Angeklickter CSS-Selektor')
    picked_label = fields.Char(string='Angeklickter Bereich')
    sample_text = fields.Char(string='Beispieltext / Element')
    last_seen = fields.Datetime(string='Zuletzt gesehen', default=fields.Datetime.now, index=True)

    @api.depends('selector', 'property_name', 'original_color', 'replacement_color', 'active')
    def _compute_name(self):
        for record in self:
            record.name = '%s / %s: %s → %s%s' % (
                record.selector or '',
                record.css_variable or record.property_name or '',
                record.original_color or '',
                record.replacement_color or '',
                '' if record.active else ' (inaktiv)',
            )

    @api.constrains('original_color', 'replacement_color')
    def _check_hex_colors(self):
        for record in self:
            for field_name in ('original_color', 'replacement_color'):
                value = record[field_name]
                if value and not HEX_RE.match(value.strip()):
                    raise ValidationError(_('%s muss ein Hex-Farbwert sein, z. B. #ff6600.') % record._fields[field_name].string)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('original_color'):
                vals['original_color'] = normalize_hex(vals['original_color'])
            if vals.get('replacement_color'):
                vals['replacement_color'] = normalize_hex(vals['replacement_color'])
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('original_color'):
            vals['original_color'] = normalize_hex(vals['original_color'])
        if vals.get('replacement_color'):
            vals['replacement_color'] = normalize_hex(vals['replacement_color'])
        return super().write(vals)


class GlWebsiteColorEntry(models.Model):
    _name = 'gl.website.color.entry'
    _description = 'Website Color Entry'
    _order = 'website_id, swatch_id, selector, property_name'
    _rec_name = 'name'

    name = fields.Char(compute='_compute_name', store=True)
    swatch_id = fields.Many2one('gl.website.color.swatch', string='Farbe', required=True, ondelete='cascade', index=True)
    website_id = fields.Many2one(related='swatch_id.website_id', store=True, readonly=True, index=True)
    scan_session_id = fields.Many2one('gl.website.color.scan.session', string='Scan', ondelete='set null')
    replacement_color = fields.Char(related='swatch_id.replacement_color', readonly=False, string='Neue Farbe')
    swatch_active = fields.Boolean(related='swatch_id.active', readonly=False, string='Override aktiv')
    active = fields.Boolean(string='Für CSS nutzen', default=True, help='Deaktivieren, wenn eine einzelne Fundstelle nicht überschrieben werden soll.')
    picked = fields.Boolean(string='Per Klick ausgewählt', default=False, index=True)
    picked_at = fields.Datetime(string='Ausgewählt am', index=True)
    picked_label = fields.Char(string='Angeklickter Bereich')
    source_type = fields.Selection([
        ('computed', 'Gerenderter Stil'),
        ('css_variable', 'CSS-Variable'),
        ('stylesheet', 'Stylesheet-Regel'),
    ], string='Quelle', required=True, default='computed', index=True)
    selector = fields.Char(string='CSS-Selektor', required=True)
    property_name = fields.Char(string='CSS-Eigenschaft', required=True)
    css_variable = fields.Char(string='CSS-Variable')
    original_color = fields.Char(string='Farbe', required=True, index=True)
    raw_value = fields.Char(string='Originaler CSS-Wert')
    matched_value = fields.Char(string='Gefundener Farbwert im CSS')
    sample_text = fields.Char(string='Beispieltext / Element')
    occurrence_count = fields.Integer(string='Vorkommen im Scan', default=1)
    last_seen = fields.Datetime(string='Zuletzt gesehen', default=fields.Datetime.now, index=True)

    @api.depends('selector', 'property_name', 'original_color', 'source_type')
    def _compute_name(self):
        for record in self:
            record.name = '%s / %s / %s' % (
                record.original_color or '',
                record.property_name or '',
                record.selector or '',
            )


class GlWebsiteColorScanSession(models.Model):
    _name = 'gl.website.color.scan.session'
    _description = 'Website Color Scan Session'
    _order = 'scan_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    website_id = fields.Many2one('website', string='Website', required=True, ondelete='cascade', index=True)
    scan_date = fields.Datetime(string='Scan-Datum', default=fields.Datetime.now, required=True)
    url = fields.Char(string='Gescannte URL')
    color_count = fields.Integer(string='Farben')
    entry_count = fields.Integer(string='Fundstellen')
    state = fields.Selection([
        ('done', 'Fertig'),
        ('error', 'Fehler'),
    ], string='Status', default='done')
    message = fields.Text(string='Meldung')
    entry_ids = fields.One2many('gl.website.color.entry', 'scan_session_id', string='Fundstellen')
    picked_selector = fields.Char(string='Angeklickter CSS-Selektor')
    picked_sample_text = fields.Char(string='Angeklickter Bereich')
    picked_swatch_ids = fields.Many2many(
        'gl.website.color.swatch',
        'gl_website_color_scan_swatch_rel',
        'scan_id',
        'swatch_id',
        string='Angeklickte Farben',
    )

    def action_open_picked_swatches(self):
        self.ensure_one()
        action = self.env.ref('gl_website_color_manager.action_gl_website_color_swatch').read()[0]
        action['domain'] = [('id', 'in', self.picked_swatch_ids.ids)]
        action['context'] = {'default_website_id': self.website_id.id}
        return action

    def action_open_picked_entries(self):
        self.ensure_one()
        action = self.env.ref('gl_website_color_manager.action_gl_website_color_entry').read()[0]
        action['domain'] = [('scan_session_id', '=', self.id), ('picked', '=', True)]
        action['context'] = {'default_scan_session_id': self.id}
        return action

    @api.depends('website_id', 'scan_date')
    def _compute_name(self):
        for record in self:
            record.name = '%s – %s' % (record.website_id.display_name or _('Website'), record.scan_date or '')


class GlWebsiteColorScanWizard(models.TransientModel):
    _name = 'gl.website.color.scan.wizard'
    _description = 'Website Color Scan Wizard'

    def _default_website_id(self):
        return self.env['website'].search([], limit=1).id

    website_id = fields.Many2one('website', string='Website', required=True, default=_default_website_id)
    path = fields.Char(string='Pfad', default='/', required=True, help='Relativer Pfad der Website, z. B. / oder /kontakt.')

    def _build_scan_url(self, pick_mode=False):
        self.ensure_one()
        path = (self.path or '/').strip() or '/'
        if not path.startswith('/') and not path.startswith('http://') and not path.startswith('https://'):
            path = '/' + path
        params = 'gl_color_scan=1'
        if pick_mode:
            params += '&gl_color_pick=1'
        separator = '&' if '?' in path else '?'
        scan_url = '%s%s%s' % (path, separator, params)

        domain = getattr(self.website_id, 'domain', False)
        if domain and not path.startswith('http://') and not path.startswith('https://'):
            domain = domain.rstrip('/')
            if not domain.startswith('http://') and not domain.startswith('https://'):
                domain = 'https://' + domain
            scan_url = domain + scan_url
        return scan_url

    def action_start_homepage_scan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'name': _('Website-Farbscan starten'),
            'url': self._build_scan_url(pick_mode=False),
            'target': 'new',
        }

    def action_start_click_pick_scan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'name': _('Website-Bereich auswählen'),
            'url': self._build_scan_url(pick_mode=True),
            'target': 'new',
        }

    def action_scan_custom_path(self):
        return self.action_start_homepage_scan()
