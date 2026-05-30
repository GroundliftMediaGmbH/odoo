# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


FORBIDDEN_WINDOWS_CHARS = r'<>:"/\\|?*'


def clean_folder_name(value, max_len=160):
    value = value or 'Ohne Titel'
    value = ''.join('-' if c in FORBIDDEN_WINDOWS_CHARS else c for c in value)
    value = re.sub(r'[\x00-\x1f]', '', value)
    value = re.sub(r'\s+', ' ', value).strip(' .')
    return (value or 'Ohne Titel')[:max_len]


def stage_name_matches(stage_name, configured_names):
    if not stage_name:
        return False
    names = [x.strip().casefold() for x in (configured_names or '').split(',') if x.strip()]
    return stage_name.strip().casefold() in names


class GlScorseseEventMixin(models.AbstractModel):
    _name = 'gl.scorsese.record.mixin'
    _description = 'SCORSESE Record Helper Mixin'

    gl_folder_path = fields.Char(string='SCORSESE Ordnerpfad', copy=False, tracking=True)
    gl_folder_status = fields.Selection([
        ('missing', 'Nicht angelegt'),
        ('queued', 'Auftrag wartet'),
        ('created', 'Ordner angelegt'),
        ('error', 'Fehler'),
    ], default='missing', string='Ordnerstatus', copy=False, tracking=True)
    gl_folder_state = fields.Selection([
        ('in_progress', 'In Bearbeitung'),
        ('done', 'Fertig'),
        ('archive_all', 'Archivieren inkl. Rohmaterial'),
        ('archive_mp4', 'Archivieren Raw → MP4'),
        ('archive_master', 'Archivieren Mixdown/Master behalten'),
        ('delete', 'Löschen'),
    ], string='Ordner-Markierung', copy=False, tracking=True)

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
        parent_path = parent_path or storage.root_path
        target_path = self.env['gl.scorsese.job'].join_path(parent_path, folder_name)
        payload = {
            'storage_id': storage.id,
            'storage_name': storage.name,
            'storage_root': storage.root_path,
            'template_id': template.id,
            'template_name': template.name,
            'template_path': template.template_path,
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

    def _gl_queue_icon_state(self, state_key):
        self.ensure_one()
        self._gl_scorsese_status_or_error()
        if not self.gl_folder_path:
            raise UserError(_('Es ist noch kein SCORSESE Ordnerpfad hinterlegt.'))
        label = dict(self._fields['gl_folder_state'].selection).get(state_key, state_key)
        payload = {
            'folder_path': self.gl_folder_path,
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

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            configured = self.env['ir.config_parameter'].sudo().get_param(
                'gl_scorsese.event_announced_stage_names', 'Angekündigt,Announced'
            )
            for rec in self:
                if rec.stage_id and stage_name_matches(rec.stage_id.name, configured) and not rec.gl_folder_path:
                    try:
                        storage = rec._gl_default_storage('production')
                        template = rec._gl_default_template('event.event')
                        rec._gl_queue_create_folder(storage, template, check_connection=False)
                    except Exception as exc:
                        rec.message_post(body=_('SCORSESE konnte keinen automatischen Ordnerauftrag anlegen: %s') % exc)
        return res

    def action_gl_create_event_folder(self):
        self.ensure_one()
        storage = self._gl_default_storage('production')
        template = self._gl_default_template('event.event')
        job = self._gl_queue_create_folder(storage, template, check_connection=True)
        return self._gl_notification(_('Ordnerauftrag wurde angelegt: %s') % job.display_name, 'success')

    def action_gl_create_event_folder_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('SCORSESE Veranstaltungsordner erstellen'),
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
                            'Projekt ist „In Bearbeitung“. Bitte über den Button „SCORSESE Ordner erstellen“ Speicherpfad und Vorlage auswählen.'
                        ))
        return res

    def action_gl_create_project_folder_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('SCORSESE Projektordner erstellen'),
            'res_model': 'gl.scorsese.folder.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_target_model': self._name,
                'default_target_res_id': self.id,
                'default_record_name': self.display_name,
            },
        }
