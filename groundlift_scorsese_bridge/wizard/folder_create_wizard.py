# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _clean_scorsese_path(value):
    value = (value or '').strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    return value.strip().strip('\"').strip("'").strip().rstrip('\\/')


class GlScorseseFolderCreateWizard(models.TransientModel):
    _name = 'gl.scorsese.folder.create.wizard'
    _description = 'SCORSESE Ordner erstellen Wizard'

    target_model = fields.Char(required=True)
    target_res_id = fields.Integer(required=True)
    record_name = fields.Char(readonly=True)
    storage_id = fields.Many2one('gl.scorsese.storage', string='Speicher', required=True)
    parent_path = fields.Char(string='Zielpfad', help='Wenn leer, wird der Root-Pfad des Speichers verwendet.')
    folder_name = fields.Char(string='Ordnername', required=True)
    template_id = fields.Many2one('gl.scorsese.template', string='Vorlage', required=True)
    cached_folder_id = fields.Many2one('gl.scorsese.path.cache', string='Ordner aus Cache auswählen')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        target_model = res.get('target_model') or self.env.context.get('default_target_model')
        target_res_id = res.get('target_res_id') or self.env.context.get('default_target_res_id')
        if target_model and target_res_id:
            record = self.env[target_model].browse(target_res_id)
            if record.exists():
                res['record_name'] = record.display_name
                if 'folder_name' in fields_list or not res.get('folder_name'):
                    res['folder_name'] = record._gl_folder_name() if hasattr(record, '_gl_folder_name') else record.display_name
                if not res.get('storage_id'):
                    if target_model == 'event.event' and hasattr(record, '_gl_public_event_storage'):
                        storage = record._gl_public_event_storage()
                    else:
                        storage_type = 'production' if target_model == 'event.event' else 'postproduction'
                        storage = record._gl_default_storage(storage_type) if hasattr(record, '_gl_default_storage') else False
                    if storage:
                        res['storage_id'] = storage.id
                if not res.get('template_id'):
                    template = record._gl_default_template(target_model) if hasattr(record, '_gl_default_template') else False
                    if template:
                        res['template_id'] = template.id
        return res

    @api.onchange('storage_id')
    def _onchange_storage_id(self):
        for rec in self:
            if rec.storage_id and not rec.parent_path:
                rec.parent_path = _clean_scorsese_path(rec.storage_id.root_path)

    @api.onchange('cached_folder_id')
    def _onchange_cached_folder_id(self):
        for rec in self:
            if rec.cached_folder_id:
                rec.parent_path = _clean_scorsese_path(rec.cached_folder_id.child_path)

    def _get_target_record(self):
        self.ensure_one()
        if not self.target_model or not self.target_res_id:
            raise UserError(_('Kein Zieldatensatz im Wizard-Kontext.'))
        record = self.env[self.target_model].browse(self.target_res_id)
        if not record.exists():
            raise UserError(_('Der Zieldatensatz existiert nicht mehr.'))
        return record

    def action_enqueue(self):
        self.ensure_one()
        record = self._get_target_record()
        job = record._gl_queue_create_folder(
            self.storage_id,
            self.template_id,
            parent_path=_clean_scorsese_path(self.parent_path or self.storage_id.root_path),
            folder_name=self.folder_name,
            check_connection=True,
        )
        return record._gl_notification(_('Ordnerauftrag wurde angelegt: %s') % job.display_name, 'success')

    def action_request_browse(self):
        self.ensure_one()
        path = _clean_scorsese_path(self.parent_path or self.storage_id.root_path)
        if not self.storage_id:
            raise UserError(_('Bitte zuerst einen Speicher auswählen.'))
        payload = {
            'storage_id': self.storage_id.id,
            'storage_name': self.storage_id.name,
            'storage_root': _clean_scorsese_path(self.storage_id.root_path),
            'path': path,
        }
        self.env['gl.scorsese.job'].create_job(
            'browse_folder',
            target_record=None,
            payload=payload,
            priority=20,
            name=_('Ordnercache aktualisieren – %s') % path,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('SCORSESE'),
                'message': _('SCORSESE lädt die Unterordner in den Cache. Öffne den Wizard nach wenigen Sekunden erneut oder wähle danach einen Cache-Ordner aus.'),
                'type': 'info',
                'sticky': False,
            }
        }

    def action_open_cache(self):
        self.ensure_one()
        domain = [('storage_id', '=', self.storage_id.id)]
        parent_path = _clean_scorsese_path(self.parent_path)
        if parent_path:
            domain.append(('browse_parent_path', '=', parent_path))
        return {
            'type': 'ir.actions.act_window',
            'name': _('SCORSESE Ordnercache'),
            'res_model': 'gl.scorsese.path.cache',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }
