import re
import uuid
from urllib.parse import urlparse

from werkzeug.security import generate_password_hash

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


class ProjectShowcase(models.Model):
    _name = 'gl.project.showcase'
    _description = 'Groundlift Projekt-Ergebnislandingpage'
    _order = 'id desc'
    _rec_name = 'name'

    _project_unique = models.Constraint('UNIQUE(project_id)', 'Pro Projekt darf nur ein Showcase existieren.')

    project_id = fields.Many2one('project.project', string='Odoo-Projekt', required=True, ondelete='cascade', index=True)
    website_id = fields.Many2one('website', string='Website', required=True,
                                 default=lambda s: s.env['website'].search([], limit=1))
    name = fields.Char(string='Seitentitel', required=True)
    subtitle = fields.Char(string='Untertitel')
    intro = fields.Text(string='Einleitung / Ergebnisse')
    closing_text = fields.Text(string='Abschlusstext')
    client_label = fields.Char(string='Markenname / Kundenlabel')
    logo = fields.Image(string='Kundenlogo', attachment=True, max_width=1200, max_height=600)
    header_image = fields.Image(string='Titelbild', attachment=True, max_width=2400, max_height=1500)
    color_background = fields.Char(string='Hintergrundfarbe', default='#101820', required=True)
    color_text = fields.Char(string='Textfarbe', default='#FFFFFF', required=True)
    color_accent = fields.Char(string='Akzentfarbe', default='#C5A46D', required=True)
    font_choice = fields.Selection([
        ('modern', 'Modern / Sans'),
        ('classic', 'Klassisch / Serif'),
        ('technical', 'Technisch / Monospace'),
        ('rounded', 'Weich / Rounded'),
        ('custom', 'Eigene Unternehmensschrift (WOFF2)'),
    ], default='modern', required=True, string='Schriftstil')
    custom_font = fields.Binary(string='Unternehmensschrift WOFF2', attachment=True)
    custom_font_filename = fields.Char(string='Schriftdatei')
    visibility = fields.Selection([
        ('private', 'Nur Projektmitarbeitende'),
        ('customer', 'Angemeldeter Kundenkontakt'),
        ('password', 'Mit Passwort'),
        ('public', 'Öffentlich'),
    ], required=True, default='private', string='Zugriff')
    published = fields.Boolean(string='Veröffentlicht', default=False, copy=False)
    indexable = fields.Boolean(string='Suchmaschinenindexierung erlauben', default=False)
    legal_notice_url = fields.Char(string='Impressumslink')
    privacy_url = fields.Char(string='Datenschutzlink')
    password_hash = fields.Char(string='Passworthash', copy=False, groups='gl_project_showcase.group_showcase_editor')
    access_version = fields.Char(default=lambda s: uuid.uuid4().hex, copy=False)
    password_is_set = fields.Boolean(compute='_compute_password_is_set', string='Passwort gesetzt')
    video_ids = fields.One2many('gl.showcase.video', 'showcase_id', string='Vimeo-Videos', copy=False)
    document_ids = fields.One2many('gl.showcase.document', 'showcase_id', string='Dokumente', copy=False)
    photo_ids = fields.One2many('gl.showcase.photo', 'showcase_id', string='Fotogalerie', copy=False)
    page_url = fields.Char(compute='_compute_page_url', string='Landingpage-URL')

    @api.depends('password_hash')
    def _compute_password_is_set(self):
        for record in self:
            record.password_is_set = bool(record.password_hash)

    @api.depends('website_id', 'website_id.domain')
    def _compute_page_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for record in self:
            domain = (record.website_id.domain or '').strip().rstrip('/')
            if domain:
                domain = domain if '://' in domain else 'https://' + domain
                parsed = urlparse(domain)
                # Website domain is configured by trusted site administrators.
                domain = f'{parsed.scheme}://{parsed.netloc}' if parsed.netloc else base_url
            record.page_url = f'{domain or base_url}/showcase/{record.id}' if record.id else False

    @api.constrains('color_background', 'color_text', 'color_accent')
    def _validate_colors(self):
        for rec in self:
            for color in (rec.color_background, rec.color_text, rec.color_accent):
                if not color or not _HEX_COLOR.fullmatch(color):
                    raise ValidationError(_('Farben müssen das Format #RRGGBB besitzen.'))

    @api.constrains('website_id', 'project_id')
    def _validate_company(self):
        for rec in self:
            project_company = rec.project_id.company_id
            website_company = rec.website_id.company_id
            if project_company and website_company and project_company != website_company:
                raise ValidationError(_('Projekt und Showcase-Website müssen demselben Unternehmen zugeordnet sein.'))

    @api.constrains('published', 'visibility', 'password_hash', 'font_choice', 'custom_font')
    def _validate_publishing(self):
        for rec in self:
            if rec.published and rec.font_choice == 'custom' and not rec.custom_font:
                raise ValidationError(_('Bitte eine WOFF2-Schriftdatei hochladen oder eine andere Schrift auswählen.'))
            if rec.published and rec.visibility == 'password' and not rec.password_hash:
                raise ValidationError(_('Bitte erst ein Zugangspasswort festlegen.'))
            if rec.published and rec.visibility == 'customer' and not rec.project_id.partner_id:
                raise ValidationError(_('Im Projekt muss für Kundenlogin ein Kunde eingetragen sein.'))

    @api.constrains('custom_font')
    def _validate_font(self):
        from .media import decode_file
        for rec in self:
            if rec.custom_font and not decode_file(rec.custom_font, limit=4 * 1024 * 1024).startswith(b'wOF2'):
                raise ValidationError(_('Nur gültige WOFF2-Schriftdateien bis 4 MB sind erlaubt.'))

    @api.constrains('legal_notice_url', 'privacy_url')
    def _validate_legal_urls(self):
        for rec in self:
            for url in (rec.legal_notice_url, rec.privacy_url):
                if url:
                    parsed = urlparse(url)
                    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                        raise ValidationError(_('Für Impressum und Datenschutz ausschließlich vollständige HTTPS-Links eingeben.'))

    @api.onchange('project_id')
    def _onchange_project(self):
        if self.project_id and not self.name:
            self.name = self.project_id.name

    def action_publish(self):
        for rec in self:
            rec.write({'published': True})

    def action_unpublish(self):
        self.write({'published': False})

    def action_change_password(self):
        self.ensure_one()
        self.check_access('write')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Showcase-Passwort ändern'),
            'res_model': 'gl.showcase.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_showcase_id': self.id},
        }

    def _set_new_password(self, password):
        self.ensure_one()
        if not password or len(password) < 12:
            raise ValidationError(_('Das Passwort muss mindestens 12 Zeichen haben.'))
        self.write({
            'password_hash': generate_password_hash(password),
            'access_version': uuid.uuid4().hex,
        })

    def action_open_website(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_url', 'url': self.page_url, 'target': 'new'}

    @property
    def gl_css_variables(self):
        self.ensure_one()
        fonts = {
            'modern': 'Arial, Helvetica, sans-serif',
            'classic': 'Georgia, Times New Roman, serif',
            'technical': 'Consolas, Courier New, monospace',
            'rounded': 'Trebuchet MS, Arial, sans-serif',
            'custom': 'GroundliftCustom, Arial, sans-serif',
        }
        # Values are validated/whitelisted; no arbitrary HTML/CSS from customers.
        return '; '.join([
            f'--gl-bg: {self.color_background}',
            f'--gl-fg: {self.color_text}',
            f'--gl-accent: {self.color_accent}',
            f'--gl-font: {fonts.get(self.font_choice, fonts["modern"])}',
        ])
