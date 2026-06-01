# -*- coding: utf-8 -*-
import re
from datetime import date, datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _clean_path_basename(path):
    path = (path or '').strip().rstrip('\\/')
    return re.split(r'[\\/]+', path)[-1].strip()


def _parse_folder_name(path, fallback_title):
    basename = _clean_path_basename(path)
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})\s+(.+)$', basename)
    if match:
        year, month, day, title = match.groups()
        try:
            return title.strip(), fields.Date.to_date('%s-%s-%s' % (year, month, day))
        except Exception:
            return title.strip(), date.today()
    return basename or fallback_title, date.today()


class GlScorseseImportWizard(models.TransientModel):
    _name = 'gl.scorsese.import.wizard'
    _description = 'SCORSESE Ordner nach Odoo importieren'

    target_model = fields.Selection([
        ('event.event', 'Nur Veranstaltung'),
        ('project.project', 'Nur Projekt'),
        ('both', 'Projekt und Veranstaltung'),
    ], default='project.project', required=True)
    storage_id = fields.Many2one('gl.scorsese.storage', string='Speicher')
    folder_path = fields.Char(required=True, string='Ordnerpfad')
    name = fields.Char(string='Titel')
    parsed_date = fields.Date(string='Datum')
    existing_project_id = fields.Many2one('project.project', string='Bestehendes Projekt verknüpfen')
    existing_event_id = fields.Many2one('event.event', string='Bestehende Veranstaltung verknüpfen')
    create_validation_job = fields.Boolean(string='Ordner von SCORSESE validieren lassen', default=False)

    @api.onchange('folder_path')
    def _onchange_folder_path(self):
        for rec in self:
            title, parsed_date = rec._parse_folder_name(rec.folder_path)
            if not rec.name or rec.name in ('Importiertes Projekt', 'Importierte Veranstaltung'):
                rec.name = title
            if not rec.parsed_date:
                rec.parsed_date = parsed_date

    def _parse_folder_name(self, path):
        return _parse_folder_name(path, _('Importiertes Projekt'))

    def _stage_id_by_name(self, model, stage_names):
        if 'stage_id' not in model._fields:
            return False
        stage_field = model._fields['stage_id']
        stage_model = self.env[stage_field.comodel_name]
        normalized_names = [n.strip().casefold() for n in stage_names if n]
        for stage in stage_model.search([]):
            if (stage.name or '').strip().casefold() in normalized_names:
                return stage.id
        return False

    def _project_values(self, title, date_value):
        Model = self.env['project.project']
        vals = {
            'name': title,
            'gl_folder_path': self.folder_path,
            'gl_folder_status': 'linked',
        }
        if 'date_start' in Model._fields:
            vals['date_start'] = date_value
        stage_id = self._stage_id_by_name(Model, ['To-do', 'To do', 'Todo'])
        if stage_id:
            vals['stage_id'] = stage_id
        return vals

    def _event_values(self, title, date_value):
        Model = self.env['event.event']
        dt_start = datetime.combine(date_value, datetime.min.time()).replace(hour=18)
        vals = {
            'name': title,
            'date_begin': fields.Datetime.to_string(dt_start),
            'date_end': fields.Datetime.to_string(dt_start + timedelta(hours=2)),
            'gl_folder_path': self.folder_path,
            'gl_folder_status': 'linked',
        }
        if 'date_tz' in Model._fields:
            vals['date_tz'] = 'Europe/Berlin'
        stage_id = self._stage_id_by_name(Model, ['Neu', 'New'])
        if stage_id:
            vals['stage_id'] = stage_id
        return vals

    def _validate_inputs(self):
        self.ensure_one()
        self.folder_path = (self.folder_path or '').strip().rstrip('\\/')
        if not self.folder_path:
            raise UserError(_('Bitte einen Ordnerpfad angeben.'))

    def action_import(self):
        self.ensure_one()
        self._validate_inputs()
        parsed_title, parsed_date = self._parse_folder_name(self.folder_path)
        title = (self.name or parsed_title or '').strip()
        if not title or title in ('Importiertes Projekt', 'Importierte Veranstaltung'):
            title = parsed_title
        date_value = self.parsed_date or parsed_date or fields.Date.context_today(self)

        project = self.existing_project_id
        event = self.existing_event_id

        if self.target_model in ('project.project', 'both'):
            if project:
                project.write({
                    'name': project.name or title,
                    'gl_folder_path': self.folder_path,
                    'gl_folder_status': 'linked',
                })
                if 'date_start' in project._fields and not project.date_start:
                    project.write({'date_start': date_value})
            else:
                project = self.env['project.project'].create(self._project_values(title, date_value))

        if self.target_model in ('event.event', 'both'):
            if event:
                event.write({
                    'name': event.name or title,
                    'gl_folder_path': self.folder_path,
                    'gl_folder_status': 'linked',
                })
            else:
                event = self.env['event.event'].create(self._event_values(title, date_value))

        if project and event:
            project.write({'gl_scorsese_event_id': event.id})
            event.write({'gl_scorsese_project_id': project.id})
            # Beide Datensätze zeigen bewusst auf denselben bestehenden SCORSESE-Ordner.
            if not project.gl_folder_path:
                project.write({'gl_folder_path': self.folder_path, 'gl_folder_status': 'linked'})
            if not event.gl_folder_path:
                event.write({'gl_folder_path': self.folder_path, 'gl_folder_status': 'linked'})

        record = project or event
        if not record:
            raise UserError(_('Es wurde kein Datensatz erzeugt oder verknüpft.'))

        targets = [target for target in [project, event] if target]
        if self.create_validation_job:
            for target in targets:
                self.env['gl.scorsese.job'].create_job(
                    'validate_folder',
                    target_record=target,
                    payload={'folder_path': self.folder_path},
                    priority=10,
                    name=_('Importierten Ordner validieren – %s') % target.display_name,
                )

        # Bei importierten Ordnern darf kein neuer SCORSESE-Ordner erzeugt werden,
        # weil gl_folder_path bereits gesetzt ist. Optional wird nur das aktuelle Phasen-Icon gesetzt.
        for target in targets:
            if hasattr(target, '_gl_queue_current_stage_icon'):
                try:
                    target._gl_queue_current_stage_icon(check_connection=False)
                except Exception:
                    pass

        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }
