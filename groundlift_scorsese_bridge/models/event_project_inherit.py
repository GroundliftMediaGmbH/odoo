# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .scorsese_models import clean_scorsese_path


FORBIDDEN_WINDOWS_CHARS = r'<>:"/\\|?*'


PROJECT_STAGE_ICON_MAP = {
    'to-do': 'todo',
    'to do': 'todo',
    'todo': 'todo',
    'in bearbeitung': 'in_progress',
    'in progress': 'in_progress',
    'vor ort erledigt': 'vor_ort_erledigt',
    'postproduktion': 'postproduktion',
    'post production': 'postproduktion',
    'abnahme und korrekturschleifen': 'abnahme_korrekturschleifen',
    'abnahme & korrekturschleifen': 'abnahme_korrekturschleifen',
    'an kunden geliefert und abgeschlossen': 'an_kunden_geliefert_abgeschlossen',
    'archivierbar - master behalten': 'archivierbar_master_behalten',
    'archivierbar master behalten': 'archivierbar_master_behalten',
    'archivierbar - rohdaten behalten': 'archivierbar_rohdaten_behalten',
    'archivierbar rohdaten behalten': 'archivierbar_rohdaten_behalten',
    'archivierbar - mp4en': 'archivierbar_mp4en',
    'archivierbar mp4en': 'archivierbar_mp4en',
    'auf server loeschen': 'auf_server_loeschen',
    'auf server löschen': 'auf_server_loeschen',
    'auf server geloescht': 'auf_server_geloescht',
    'auf server gelöscht': 'auf_server_geloescht',
    'abgebrochen': 'abgebrochen',
}

EVENT_STAGE_ICON_MAP = {
    'neu': 'event_neu',
    'new': 'event_neu',
    'gebucht': 'event_gebucht',
    'booked': 'event_gebucht',
    'angekuendigt': 'event_angekuendigt',
    'angekündigt': 'event_angekuendigt',
    'announced': 'event_angekuendigt',
    'abrechnung': 'event_abrechnung',
    'invoicing': 'event_abrechnung',
    'beendet': 'event_beendet',
    'ended': 'event_beendet',
    'done': 'event_beendet',
}


def clean_folder_name(value, max_len=160):
    value = value or 'Ohne Titel'
    value = ''.join('-' if c in FORBIDDEN_WINDOWS_CHARS else c for c in value)
    value = re.sub(r'[\x00-\x1f]', '', value)
    value = re.sub(r'\s+', ' ', value).strip(' .')
    return (value or 'Ohne Titel')[:max_len]


def normalized_stage_name(value):
    value = (value or '').strip().casefold()
    value = value.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    value = re.sub(r'\s+', ' ', value)
    return value


def stage_name_matches(stage_name, configured_names):
    if not stage_name:
        return False
    needle = normalized_stage_name(stage_name)
    names = [normalized_stage_name(x) for x in (configured_names or '').split(',') if x.strip()]
    return needle in names


def stage_to_icon_key(model_name, stage):
    """Erzeugt einen stabilen dynamischen Icon-Key aus der echten Odoo-Phase.

    Dadurch muss der Agent keine fest codierten Phasennamen mehr kennen. Wenn
    Odoo-Phasen umbenannt oder erweitert werden, bleibt die Zuordnung über die
    Stage-ID stabil.
    """
    if not stage:
        return False
    if model_name == 'project.project':
        return 'project_stage_%s' % stage.id
    if model_name == 'event.event':
        return 'event_stage_%s' % stage.id
    return False


def stage_to_icon_label(model_name, stage):
    if not stage:
        return False
    prefix = _('Projekt') if model_name == 'project.project' else _('Veranstaltung')
    return '%s: %s' % (prefix, stage.display_name or stage.name)


class GlScorseseRecordMixin(models.AbstractModel):
    _name = 'gl.scorsese.record.mixin'
    _description = 'SCORSESE Record Helper Mixin'

    gl_folder_path = fields.Char(string='SCORSESE Ordnerpfad', copy=False, tracking=True)
    gl_folder_status = fields.Selection([
        ('missing', 'Nicht angelegt'),
        ('queued', 'Auftrag wartet'),
        ('created', 'Ordner angelegt'),
        ('linked', 'Vorhandener Ordner verknüpft'),
        ('error', 'Fehler'),
    ], default='missing', string='Ordnerstatus', copy=False, tracking=True)
    gl_folder_state = fields.Char(string='Letzte SCORSESE Icon-Phase', copy=False, tracking=True)
    gl_folder_state_label = fields.Char(string='Letzte SCORSESE Icon-Beschriftung', copy=False, tracking=True)

    def _gl_scorsese_status_or_error(self):
        status = self.env['gl.scorsese.job'].get_connection_status()
        if not status.get('is_online'):
            raise UserError(_(
                'SCORSESE ist aktuell nicht verbunden. Letzter Heartbeat: %s. '
                'Bitte den lokalen Agenten auf SCORSESE prüfen.'
            ) % (status.get('last_heartbeat') or 'nie'))
        return status

    def _gl_default_storage(self, storage_type='production'):
        storage = self.env['gl.scorsese.storage'].search([
            ('active', '=', True),
            ('storage_type', '=', storage_type),
        ], limit=1)
        if not storage:
            storage = self.env['gl.scorsese.storage'].search([('active', '=', True)], limit=1)
        if not storage:
            raise UserError(_('Bitte zuerst mindestens einen SCORSESE Speicherpfad konfigurieren.'))
        return storage

    def _gl_public_event_storage(self):
        Storage = self.env['gl.scorsese.storage']
        storage = Storage.search([('active', '=', True), ('storage_type', '=', 'public_events')], limit=1)
        if storage:
            return storage
        storage = Storage.search([
            ('active', '=', True),
            ('code', 'in', ['public_events', 'public_event', 'oeffentliche_veranstaltungen', 'öffentliche_veranstaltungen']),
        ], limit=1)
        if storage:
            return storage
        for candidate in Storage.search([('active', '=', True)]):
            name = normalized_stage_name(candidate.name or '')
            code = normalized_stage_name(candidate.code or '')
            path = normalized_stage_name(candidate.root_path or '')
            if (
                ('oeffentliche' in name and 'veranstalt' in name)
                or ('oeffentliche' in path and 'veranstalt' in path)
                or ('05 oeffentliche veranstaltungen' in path)
                or ('public' in code and 'event' in code)
            ):
                return candidate
        return self._gl_default_storage('production')

    def _gl_default_template(self, target_model):
        Template = self.env['gl.scorsese.template']
        if target_model == 'event.event':
            domain = [('active', '=', True), ('is_default_event', '=', True)]
        else:
            domain = [('active', '=', True), ('is_default_project', '=', True)]
        template = Template.search(domain, limit=1)
        if not template:
            template = Template.search([
                ('active', '=', True),
                ('target_model', 'in', [target_model, 'both']),
            ], limit=1)
        if not template:
            raise UserError(_('Bitte zuerst eine SCORSESE Ordnervorlage konfigurieren.'))
        return template

    def _gl_date_for_folder(self):
        self.ensure_one()
        if self._name == 'event.event':
            dt = getattr(self, 'date_begin', False)
            if dt:
                return fields.Datetime.context_timestamp(self, dt).date()
        if self._name == 'project.project':
            if 'date_start' in self._fields and self.date_start:
                return self.date_start
            if 'date' in self._fields and self.date:
                return self.date
        return fields.Date.context_today(self)

    def _gl_folder_name(self):
        self.ensure_one()
        date_part = self._gl_date_for_folder().strftime('%Y-%m-%d')
        title = clean_folder_name(self.display_name or self.name)
        return '%s %s' % (date_part, title)

    def _gl_queue_create_folder(self, storage, template, parent_path=None, folder_name=None, check_connection=True):
        self.ensure_one()
        if check_connection:
            self._gl_scorsese_status_or_error()
        if self.gl_folder_path:
            raise UserError(_('Es ist bereits ein SCORSESE Ordnerpfad gesetzt:\n%s') % self.gl_folder_path)
        folder_name = folder_name or self._gl_folder_name()
        parent_path = clean_scorsese_path(parent_path or storage.root_path)
        storage_root = clean_scorsese_path(storage.root_path)
        template_path = clean_scorsese_path(template.template_path)
        target_path = self.env['gl.scorsese.job'].join_path(parent_path, folder_name)
        payload = {
            'storage_id': storage.id,
            'storage_name': storage.name,
            'storage_root': storage_root,
            'template_id': template.id,
            'template_name': template.name,
            'template_path': template_path,
            'parent_path': parent_path,
            'folder_name': folder_name,
            'target_path': target_path,
        }
        job = self.env['gl.scorsese.job'].create_job(
            'create_folder_from_template',
            target_record=self,
            payload=payload,
            priority=5,
            name=_('Ordner erstellen – %s') % self.display_name,
        )
        self.write({'gl_folder_status': 'queued'})
        return job

    def _gl_current_stage_icon_key(self):
        self.ensure_one()
        stage = getattr(self, 'stage_id', False) if 'stage_id' in self._fields else False
        return stage_to_icon_key(self._name, stage)

    def _gl_current_stage_icon_label(self):
        self.ensure_one()
        stage = getattr(self, 'stage_id', False) if 'stage_id' in self._fields else False
        return stage_to_icon_label(self._name, stage)

    def _gl_queue_current_stage_icon(self, check_connection=False):
        self.ensure_one()
        if not self.gl_folder_path:
            return False
        state_key = self._gl_current_stage_icon_key()
        if not state_key:
            return False
        if self.gl_folder_state == state_key:
            return False
        return self._gl_queue_icon_state(state_key, check_connection=check_connection, state_label=self._gl_current_stage_icon_label())

    def _gl_queue_icon_state(self, state_key, check_connection=True, state_label=None):
        self.ensure_one()
        if check_connection:
            self._gl_scorsese_status_or_error()
        if not self.gl_folder_path:
            raise UserError(_('Es ist noch kein SCORSESE Ordnerpfad hinterlegt.'))
        label = state_label or state_key
        payload = {
            'folder_path': clean_scorsese_path(self.gl_folder_path),
            'state_key': state_key,
            'state_label': label,
        }
        self.env['gl.scorsese.job'].create_job(
            'set_folder_icon',
            target_record=self,
            payload=payload,
            priority=5,
            name=_('Ordnericon setzen – %s – %s') % (label, self.display_name),
        )
        return self._gl_notification(_('SCORSESE Auftrag angelegt: Ordnericon „%s“ wird gesetzt.') % label, 'success')

    def _gl_notification(self, message, kind='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('SCORSESE'),
                'message': message,
                'type': kind,
                'sticky': False,
            }
        }

    # Alte Button-Methoden bleiben aus Kompatibilitätsgründen bestehen, werden aber nicht mehr in den Views angezeigt.
    def action_gl_state_in_progress(self):
        return self._gl_queue_icon_state('in_progress')

    def action_gl_state_done(self):
        return self._gl_queue_icon_state('done')

    def action_gl_state_archive_all(self):
        return self._gl_queue_icon_state('archive_all')

    def action_gl_state_archive_mp4(self):
        return self._gl_queue_icon_state('archive_mp4')

    def action_gl_state_archive_master(self):
        return self._gl_queue_icon_state('archive_master')

    def action_gl_state_delete(self):
        return self._gl_queue_icon_state('delete')

    def action_gl_open_jobs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('SCORSESE Aufträge'),
            'res_model': 'gl.scorsese.job',
            'view_mode': 'list,form',
            'domain': [('target_model', '=', self._name), ('target_res_id', '=', self.id)],
            'context': {'default_target_model': self._name, 'default_target_res_id': self.id},
        }


class EventEvent(models.Model):
    _inherit = ['event.event', 'gl.scorsese.record.mixin']

    gl_todo_ids = fields.One2many('project.task', 'gl_event_id', string='GROUNDLIFT ToDos')
    gl_scorsese_project_id = fields.Many2one('project.project', string='Verknüpftes SCORSESE Projekt', copy=False)

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            configured = self.env['ir.config_parameter'].sudo().get_param(
                'gl_scorsese.event_announced_stage_names', 'Angekündigt,Announced'
            )
            for rec in self:
                if rec.stage_id and stage_name_matches(rec.stage_id.name, configured) and not rec.gl_folder_path:
                    try:
                        storage = rec._gl_public_event_storage()
                        template = rec._gl_default_template('event.event')
                        rec._gl_queue_create_folder(storage, template, parent_path=storage.root_path, check_connection=False)
                    except Exception as exc:
                        rec.message_post(body=_('SCORSESE konnte keinen automatischen Veranstaltungsordner anlegen: %s') % exc)
                elif rec.gl_folder_path:
                    try:
                        rec._gl_queue_current_stage_icon(check_connection=False)
                    except Exception as exc:
                        rec.message_post(body=_('SCORSESE konnte keinen Icon-Auftrag für die Veranstaltungsphase anlegen: %s') % exc)
        if 'gl_scorsese_project_id' in vals:
            for rec in self:
                project = rec.gl_scorsese_project_id
                if project:
                    updates = {}
                    if not rec.gl_folder_path and project.gl_folder_path:
                        updates.update({'gl_folder_path': project.gl_folder_path, 'gl_folder_status': project.gl_folder_status or 'linked'})
                    if project.gl_scorsese_event_id.id != rec.id:
                        project.sudo().write({'gl_scorsese_event_id': rec.id})
                    if updates:
                        rec.sudo().write(updates)
        return res

    def action_gl_create_event_folder(self):
        self.ensure_one()
        storage = self._gl_public_event_storage()
        template = self._gl_default_template('event.event')
        job = self._gl_queue_create_folder(storage, template, parent_path=storage.root_path, check_connection=True)
        return self._gl_notification(_('Ordnerauftrag wurde angelegt: %s') % job.display_name, 'success')

    def action_gl_create_event_folder_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ordner auf Server erstellen'),
            'res_model': 'gl.scorsese.folder.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_target_model': self._name,
                'default_target_res_id': self.id,
                'default_record_name': self.display_name,
            },
        }


class ProjectProject(models.Model):
    _inherit = ['project.project', 'gl.scorsese.record.mixin']

    gl_folder_pending = fields.Boolean(string='SCORSESE Ordner muss angelegt werden', copy=False)
    gl_todo_ids = fields.One2many('project.task', 'gl_project_record_id', string='GROUNDLIFT ToDos')
    gl_scorsese_event_id = fields.Many2one('event.event', string='Verknüpfte SCORSESE Veranstaltung', copy=False)

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            configured = self.env['ir.config_parameter'].sudo().get_param(
                'gl_scorsese.project_work_stage_names', 'In Bearbeitung,In Progress'
            )
            for rec in self:
                stage = rec.stage_id if 'stage_id' in rec._fields else False
                if stage and stage_name_matches(stage.name, configured) and not rec.gl_folder_path:
                    rec.write({'gl_folder_pending': True})
                    if hasattr(rec, 'message_post'):
                        rec.message_post(body=_(
                            'SCORSESE Projektordner wurde noch nicht automatisch erstellt. '
                            'Bitte über den Button „Ordner auf Server erstellen“ Speicher, Ordner, Unterordner, Vorlage und Projektdatum auswählen.'
                        ))
                elif rec.gl_folder_path:
                    try:
                        rec._gl_queue_current_stage_icon(check_connection=False)
                    except Exception as exc:
                        if hasattr(rec, 'message_post'):
                            rec.message_post(body=_('SCORSESE konnte keinen Icon-Auftrag für die Projektphase anlegen: %s') % exc)
        if 'gl_scorsese_event_id' in vals:
            for rec in self:
                event = rec.gl_scorsese_event_id
                if event:
                    updates = {}
                    if not rec.gl_folder_path and event.gl_folder_path:
                        updates.update({'gl_folder_path': event.gl_folder_path, 'gl_folder_status': event.gl_folder_status or 'linked'})
                    if event.gl_scorsese_project_id.id != rec.id:
                        event.sudo().write({'gl_scorsese_project_id': rec.id})
                    if updates:
                        rec.sudo().write(updates)
        return res

    def action_gl_create_project_folder_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ordner auf Server erstellen'),
            'res_model': 'gl.scorsese.folder.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_target_model': self._name,
                'default_target_res_id': self.id,
                'default_record_name': self.display_name,
            },
        }
