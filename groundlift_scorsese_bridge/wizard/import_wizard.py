# -*- coding: utf-8 -*-
import re
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GlScorseseImportWizard(models.TransientModel):
    _name = 'gl.scorsese.import.wizard'
    _description = 'SCORSESE Ordner nach Odoo importieren'

    target_model = fields.Selection([
        ('event.event', 'Veranstaltung'),
        ('project.project', 'Projekt'),
    ], default='project.project', required=True)
    storage_id = fields.Many2one('gl.scorsese.storage', string='Speicher')
    folder_path = fields.Char(required=True, string='Ordnerpfad')
    name = fields.Char(string='Titel')
    parsed_date = fields.Date(string='Datum')
    create_validation_job = fields.Boolean(string='Ordner von SCORSESE validieren lassen', default=False)

    @api.onchange('folder_path')
    def _onchange_folder_path(self):
        for rec in self:
            title, parsed_date = rec._parse_folder_name(rec.folder_path)
            if not rec.name:
                rec.name = title
            if not rec.parsed_date:
                rec.parsed_date = parsed_date

    def _parse_folder_name(self, path):
        basename = re.split(r'[\\/]+', path or '')[-1].strip()
        match = re.match(r'^(\d{4})-(\d{2})-(\d{2})\s+(.+)$', basename)
        if match:
            year, month, day, title = match.groups()
            try:
                return title.strip(), fields.Date.to_date('%s-%s-%s' % (year, month, day))
            except Exception:
                return title.strip(), fields.Date.context_today(self)
        return basename or _('Importiertes Projekt'), fields.Date.context_today(self)

    def action_import(self):
        self.ensure_one()
        if not self.folder_path:
            raise UserError(_('Bitte einen Ordnerpfad angeben.'))
        title = self.name or self._parse_folder_name(self.folder_path)[0]
        date_value = self.parsed_date or fields.Date.context_today(self)
        if self.target_model == 'event.event':
            Model = self.env['event.event']
            dt_start = datetime.combine(date_value, datetime.min.time()).replace(hour=18)
            vals = {
                'name': title,
                'date_begin': fields.Datetime.to_string(dt_start),
                'date_end': fields.Datetime.to_string(dt_start + timedelta(hours=2)),
                'gl_folder_path': self.folder_path,
                'gl_folder_status': 'created',
            }
            if 'date_tz' in Model._fields:
                vals['date_tz'] = 'Europe/Berlin'
            record = Model.create(vals)
        else:
            Model = self.env['project.project']
            vals = {
                'name': title,
                'gl_folder_path': self.folder_path,
                'gl_folder_status': 'created',
            }
            if 'date_start' in Model._fields:
                vals['date_start'] = date_value
            record = Model.create(vals)

        if self.create_validation_job:
            self.env['gl.scorsese.job'].create_job(
                'validate_folder',
                target_record=record,
                payload={'folder_path': self.folder_path},
                priority=10,
                name=_('Importierten Ordner validieren – %s') % record.display_name,
            )
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.target_model,
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }
