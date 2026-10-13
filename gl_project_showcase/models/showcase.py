import re
import uuid
from urllib.parse import urlparse

from werkzeug.security import generate_password_hash

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .texts import SHOWCASE_TEXTS, CONFIG_PREFIX


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
    password_hash = fields.Char(string='Passworthash', copy=False, groups='base.group_user')
    access_version = fields.Char(default=lambda s: uuid.uuid4().hex, copy=False)
    password_is_set = fields.Boolean(compute='_compute_password_is_set', string='Passwort gesetzt')
    video_ids = fields.One2many('gl.showcase.video', 'showcase_id', string='Vimeo-Videos', copy=False)
    document_ids = fields.One2many('gl.showcase.document', 'showcase_id', string='Dokumente', copy=False)
    photo_ids = fields.One2many('gl.showcase.photo', 'showcase_id', string='Fotogalerie', copy=False)
    photo_tag_ids = fields.One2many(
        'gl.showcase.photo.tag', 'showcase_id', string='Galerie-Überschriften', copy=False,
    )
    page_url = fields.Char(compute='_compute_page_url', string='Landingpage-URL')

    # Optional per-showcase overrides. False means live default from Project settings.
    gl_text_brand_fallback = fields.Char(string='Branding: Ersatztext', help='Leer lassen = Projekteinstellungen: PROJECT SHOWCASE')
    gl_text_nav_results = fields.Char(string='Menü: Ergebnisse', help='Leer lassen = Projekteinstellungen: Ergebnisse')
    gl_text_nav_videos = fields.Char(string='Menü: Filme', help='Leer lassen = Projekteinstellungen: Filme')
    gl_text_nav_documents = fields.Char(string='Menü: Dokumente', help='Leer lassen = Projekteinstellungen: Dokumente')
    gl_text_nav_gallery = fields.Char(string='Menü: Galerie', help='Leer lassen = Projekteinstellungen: Galerie')
    gl_text_hero_eyebrow = fields.Char(string='Titelbild: Kategorie', help='Leer lassen = Projekteinstellungen: Projektabschluss · Ergebnisse')
    gl_text_hero_cta = fields.Char(string='Titelbild: Aufruf', help='Leer lassen = Projekteinstellungen: Ergebnisse entdecken')
    gl_text_results_index = fields.Char(string='Ergebnisse: Bereichslabel', help='Leer lassen = Projekteinstellungen: 01 / ÜBERBLICK')
    gl_text_results_title = fields.Char(string='Ergebnisse: Überschrift', help='Leer lassen = Projekteinstellungen: Das Ergebnis')
    gl_text_intro_fallback = fields.Char(string='Ergebnisse: Ersatztext', help='Leer lassen = Projekteinstellungen: Einblicke und freigegebene Ergebnisse aus unserem gemeinsamen Projekt.')
    gl_text_videos_index = fields.Char(string='Videos: Bereichslabel', help='Leer lassen = Projekteinstellungen: 02 / MOVING IMAGE')
    gl_text_videos_title = fields.Char(string='Videos: Überschrift', help='Leer lassen = Projekteinstellungen: Showreel & Videos')
    gl_text_video_start = fields.Char(string='Videos: Button', help='Leer lassen = Projekteinstellungen: Video auf Vimeo laden')
    gl_text_video_privacy = fields.Char(string='Videos: Datenschutzhinweis', help='Leer lassen = Projekteinstellungen: Beim Abspielen werden Daten an Vimeo übertragen.')
    gl_text_video_files = fields.Char(string='Videos: Dateibereich', help='Leer lassen = Projekteinstellungen: Zugehörige Dateien')
    gl_text_documents_index = fields.Char(string='Dokumente: Bereichslabel', help='Leer lassen = Projekteinstellungen: 03 / ASSETS & DOCUMENTS')
    gl_text_documents_title = fields.Char(string='Dokumente: Überschrift', help='Leer lassen = Projekteinstellungen: Dokumente')
    gl_text_document_view_only = fields.Char(string='Dokumente: Hinweis ohne Download', help='Leer lassen = Projekteinstellungen: Nur Ansicht · kein Download-Button')
    gl_text_document_preview = fields.Char(string='Dokumente: Vorschau', help='Leer lassen = Projekteinstellungen: Vorschau ansehen')
    gl_text_document_download = fields.Char(string='Dokumente: Download', help='Leer lassen = Projekteinstellungen: Herunterladen')
    gl_text_document_new_window = fields.Char(string='Dokumente: In neuem Fenster', help='Leer lassen = Projekteinstellungen: In neuem Fenster öffnen')
    gl_text_document_fullscreen = fields.Char(string='Dokumente: Vollbild', help='Leer lassen = Projekteinstellungen: Vollbild')
    gl_text_document_previous = fields.Char(string='Dokumente: Vorherige Seite', help='Leer lassen = Projekteinstellungen: Vorherige Seite')
    gl_text_document_next = fields.Char(string='Dokumente: Nächste Seite', help='Leer lassen = Projekteinstellungen: Nächste Seite')
    gl_text_document_zoom_in = fields.Char(string='Dokumente: Vergrößern', help='Leer lassen = Projekteinstellungen: Vergrößern')
    gl_text_document_zoom_out = fields.Char(string='Dokumente: Verkleinern', help='Leer lassen = Projekteinstellungen: Verkleinern')
    gl_text_document_print_blocked = fields.Char(string='Dokumente: Druckhinweis', help='Leer lassen = Projekteinstellungen: Drucken ist für dieses Dokument nicht freigegeben.')
    gl_text_gallery_index = fields.Char(string='Galerie: Bereichslabel', help='Leer lassen = Projekteinstellungen: 04 / STILL IMAGE')
    gl_text_gallery_title = fields.Char(string='Galerie: Überschrift', help='Leer lassen = Projekteinstellungen: Galerie')
    gl_text_gallery_untagged = fields.Char(string='Galerie: Fotos ohne Tag', help='Leer lassen = Projekteinstellungen: Weitere Fotos')
    gl_text_thanks = fields.Char(string='Abschluss: Überschrift', help='Leer lassen = Projekteinstellungen: VIELEN DANK')
    gl_text_imprint = fields.Char(string='Footer: Impressum', help='Leer lassen = Projekteinstellungen: Impressum')
    gl_text_privacy = fields.Char(string='Footer: Datenschutz', help='Leer lassen = Projekteinstellungen: Datenschutz')
    gl_text_skip_link = fields.Char(string='Barrierefreiheit: Zum Inhalt', help='Leer lassen = Projekteinstellungen: Zum Inhalt springen')
    gl_text_lightbox_close = fields.Char(string='Galerie: Schließen', help='Leer lassen = Projekteinstellungen: Schließen')
    gl_text_password_eyebrow = fields.Char(string='Passwortseite: Bereichslabel', help='Leer lassen = Projekteinstellungen: GESCHÜTZTER PROJEKTBEREICH')
    gl_text_password_title = fields.Char(string='Passwortseite: Überschrift', help='Leer lassen = Projekteinstellungen: Zugang zum Project Showcase')
    gl_text_password_help = fields.Char(string='Passwortseite: Hinweis', help='Leer lassen = Projekteinstellungen: Für diese Ergebnis-Landingpage benötigst du ein Zugangspasswort.')
    gl_text_password_label = fields.Char(string='Passwortseite: Eingabefeld', help='Leer lassen = Projekteinstellungen: Passwort')
    gl_text_password_submit = fields.Char(string='Passwortseite: Button', help='Leer lassen = Projekteinstellungen: Showcase öffnen')
    gl_text_password_invalid = fields.Char(string='Passwortseite: falsches Passwort', help='Leer lassen = Projekteinstellungen: Das Passwort ist nicht korrekt.')
    gl_text_password_limited = fields.Char(string='Passwortseite: zu viele Versuche', help='Leer lassen = Projekteinstellungen: Zu viele Versuche. Bitte später erneut versuchen.')

    gl_text_page_title_suffix = fields.Char(string='Browser-Titel: Namenszusatz', help='Leer lassen = Projekteinstellungen: Project Showcase')
    gl_text_password_browser_title = fields.Char(string='Passwortseite: Browser-Titel', help='Leer lassen = Projekteinstellungen: Geschütztes Project Showcase')
    gl_text_closing_body = fields.Char(string='Abschluss: Standardabsatz', help='Leer lassen = Projekteinstellungen: Vielen Dank für die Zusammenarbeit.')
    gl_text_aria_navigation = fields.Char(string='Barrierefreiheit: Navigationsbeschreibung', help='Leer lassen = Projekteinstellungen: Seitennavigation')
    gl_text_aria_pdf_preview = fields.Char(string='Barrierefreiheit: PDF-Vorschaubeschreibung', help='Leer lassen = Projekteinstellungen: PDF-Vorschau')
    gl_text_aria_lightbox = fields.Char(string='Barrierefreiheit: Galeriefenster', help='Leer lassen = Projekteinstellungen: Bild in Großansicht')
    gl_text_aria_logo = fields.Char(string='Barrierefreiheit: Logo-Ersatztext', help='Leer lassen = Projekteinstellungen: Logo')

    def gl_get_texts(self):
        """Return an escaped-by-QWeb plain-text map of current labels.

        Overrides remain empty on existing showcases, hence updated global
        Project settings apply immediately without a migration or duplication.
        """
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        result = {}
        for key, (_label, original_default) in SHOWCASE_TEXTS.items():
            local_value = self['gl_text_' + key]
            global_value = params.get_param(CONFIG_PREFIX + key)
            result[key] = local_value or global_value or original_default
        return result

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            project_id = vals.get('project_id')
            if project_id and not self.env.su:
                self.env['project.project'].browse(project_id).check_access('read')
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('project_id') and not self.env.su:
            self.env['project.project'].browse(vals['project_id']).check_access('read')
        return super().write(vals)

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
        from .media import decode_record_file
        for rec in self:
            if rec.custom_font and not decode_record_file(rec, 'custom_font', limit=4 * 1024 * 1024).startswith(b'wOF2'):
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

    def action_gl_refresh_video_thumbnails(self):
        self.ensure_one()
        self.check_access('write')
        # Deliberate user action; auto-fetch is also done on newly saved URLs.
        self.video_ids._gl_sync_thumbnails(force=True)
        return True

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

    def _gl_open_media_batch(self, media_kind, mode, video_id=False):
        self.ensure_one()
        self.check_access('write')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mehrfachupload' if mode == 'upload' else 'Gemeinsam bearbeiten',
            'res_model': 'gl.showcase.media.batch.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('gl_project_showcase.view_gl_showcase_media_batch_wizard').id,
            'target': 'new',
            'context': {
                'default_showcase_id': self.id,
                'default_media_kind': media_kind,
                'default_mode': mode,
                'default_video_id': video_id or False,
            },
        }

    def action_gl_upload_photos(self):
        return self._gl_open_media_batch('photo', 'upload')

    def action_gl_edit_photos(self):
        return self._gl_open_media_batch('photo', 'edit')

    def action_gl_upload_documents(self):
        return self._gl_open_media_batch('document', 'upload')

    def action_gl_edit_documents(self):
        return self._gl_open_media_batch('document', 'edit')

    def gl_gallery_groups(self):
        """Visible groups in tag sequence; untagged pictures are kept in a final group.

        Images with several tags deliberately appear in every matching section.
        """
        self.ensure_one()
        groups = []
        for tag in self.photo_tag_ids:
            photos = self.photo_ids.filtered(lambda photo: tag in photo.tag_ids)
            if photos:
                groups.append({'name': tag.name, 'photos': photos})
        untagged = self.photo_ids.filtered(lambda photo: not photo.tag_ids)
        if untagged:
            groups.append({
                'name': self.gl_get_texts()['gallery_untagged'] if groups else False,
                'photos': untagged,
            })
        return groups

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
