# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _clean_scorsese_path(value):
    value = (value or '').strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    return value.strip().strip('\\"').strip("'").strip().rstrip('\\/')


def _clean_folder_title(value):
    value = (value or '').strip()
    for char in '<>:"/\\|?*':
        value = value.replace(char, '-')
    value = ' '.join(value.split())
    return value or 'Unbenannt'


def _join_path(root, child):
    root = _clean_scorsese_path(root)
    child = (child or '').strip().strip('\\"').strip("'").strip('\\/')
    if not root:
        return child
    sep = '\\' if ('\\' in root or (len(root) > 1 and root[1] == ':')) else '/'
    return root + sep + child


def _norm_path_for_compare(value):
    """Normalize SCORSESE paths for robust comparisons inside Odoo domains.

    Cache entries may contain Windows paths with backslashes, UNC paths or paths
    that came from JSON with forward slashes. Exact XML-domain comparisons are
    therefore fragile. The wizard computes candidate IDs in Python and uses an
    ID-domain in the view.
    """
    value = _clean_scorsese_path(value)
    value = value.replace('/', '\\')
    while '\\\\' in value and not value.startswith('\\\\'):
        value = value.replace('\\\\', '\\')
    return value.rstrip('\\').casefold()


def _same_path(left, right):
    return _norm_path_for_compare(left) == _norm_path_for_compare(right)


def _path_parent(value):
    value = _clean_scorsese_path(value).replace('/', '\\').rstrip('\\')
    if '\\' not in value:
        return ''
    return value.rsplit('\\', 1)[0]


class GlScorseseFolderCreateWizard(models.TransientModel):
    _name = 'gl.scorsese.folder.create.wizard'
    _description = 'SCORSESE Ordner erstellen Wizard'

    target_model = fields.Char(required=True)
    target_res_id = fields.Integer(required=True)
    record_name = fields.Char(readonly=True)

    storage_id = fields.Many2one('gl.scorsese.storage', string='Speicher', required=True)
    storage_root_path = fields.Char(string='Speicher-Root', readonly=True)

    root_folder_cache_id = fields.Many2one(
        'gl.scorsese.path.cache',
        string='Ordner wählen',
        help='Erste Ordnerebene innerhalb des gewählten Speichers.',
    )
    root_folder_path = fields.Char(string='Gewählter Ordnerpfad', readonly=True)

    subfolder_cache_id = fields.Many2one(
        'gl.scorsese.path.cache',
        string='Unterordner wählen',
        help='Optionaler Unterordner innerhalb des gewählten Ordners.',
    )
    available_root_cache_ids = fields.Many2many(
        'gl.scorsese.path.cache',
        'gl_scorsese_folder_create_root_cache_rel',
        'wizard_id',
        'cache_id',
        string='Verfügbare Hauptordner',
        compute='_compute_available_cache_ids',
    )
    available_subfolder_cache_ids = fields.Many2many(
        'gl.scorsese.path.cache',
        'gl_scorsese_folder_create_sub_cache_rel',
        'wizard_id',
        'cache_id',
        string='Verfügbare Unterordner',
        compute='_compute_available_cache_ids',
    )
    parent_path = fields.Char(string='Zielpfad', readonly=True, help='Hier wird der neue Ordner erstellt.')

    template_id = fields.Many2one('gl.scorsese.template', string='Vorlage', required=True)
    folder_name = fields.Char(string='Neuer Ordnername', required=True)

    create_project_from_event = fields.Boolean(string='Projekt daraus erzeugen')
    project_date_start = fields.Date(string='Projekt von')
    project_date_end = fields.Date(string='Projekt bis')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        target_model = res.get('target_model') or self.env.context.get('default_target_model')
        target_res_id = res.get('target_res_id') or self.env.context.get('default_target_res_id')
        if target_model and target_res_id:
            record = self.env[target_model].browse(target_res_id)
            if record.exists():
                res['record_name'] = record.display_name
                if not res.get('project_date_start'):
                    date_start, date_end = self._default_project_dates(record)
                    if date_start:
                        res['project_date_start'] = date_start
                    if date_end:
                        res['project_date_end'] = date_end
                if 'folder_name' in fields_list or not res.get('folder_name'):
                    date_for_name = res.get('project_date_start') if target_model == 'project.project' else False
                    res['folder_name'] = self._folder_name_for_record(record, date_for_name=date_for_name)
                if not res.get('storage_id'):
                    if target_model == 'event.event' and hasattr(record, '_gl_public_event_storage'):
                        storage = record._gl_public_event_storage()
                    else:
                        storage_type = 'production' if target_model == 'event.event' else 'postproduction'
                        storage = record._gl_default_storage(storage_type) if hasattr(record, '_gl_default_storage') else False
                    if storage:
                        res['storage_id'] = storage.id
                        res['storage_root_path'] = _clean_scorsese_path(storage.root_path)
                        res['parent_path'] = _clean_scorsese_path(storage.root_path)
                if not res.get('template_id'):
                    template = record._gl_default_template(target_model) if hasattr(record, '_gl_default_template') else False
                    if template:
                        res['template_id'] = template.id
        return res

    @api.model
    def _default_project_dates(self, record):
        date_start = False
        date_end = False
        if record._name == 'event.event':
            if getattr(record, 'date_begin', False):
                date_start = fields.Datetime.context_timestamp(record, record.date_begin).date()
            if getattr(record, 'date_end', False):
                date_end = fields.Datetime.context_timestamp(record, record.date_end).date()
        elif record._name == 'project.project':
            if 'date_start' in record._fields and record.date_start:
                date_start = record.date_start
            elif 'date' in record._fields and record.date:
                # In manchen Odoo-Versionen ist date das Enddatum; daher nur Fallback.
                date_start = record.date
            if 'date_end' in record._fields and record.date_end:
                date_end = record.date_end
            elif 'date' in record._fields and record.date:
                date_end = record.date
        return date_start, date_end

    @api.model
    def _folder_name_for_record(self, record, date_for_name=False):
        if date_for_name:
            date_part = date_for_name.strftime('%Y-%m-%d') if hasattr(date_for_name, 'strftime') else str(date_for_name)
            return '%s %s' % (date_part, _clean_folder_title(record.display_name or record.name))
        if hasattr(record, '_gl_folder_name'):
            return record._gl_folder_name()
        return _clean_folder_title(record.display_name or record.name)

    @api.depends('storage_id', 'storage_root_path', 'root_folder_cache_id', 'root_folder_path')
    def _compute_available_cache_ids(self):
        Cache = self.env['gl.scorsese.path.cache'].sudo()
        for rec in self:
            rec.available_root_cache_ids = Cache.browse()
            rec.available_subfolder_cache_ids = Cache.browse()
            if not rec.storage_id:
                continue

            storage_root = _clean_scorsese_path(rec.storage_root_path or rec.storage_id.root_path)
            cache_entries = Cache.search([
                ('storage_id', '=', rec.storage_id.id),
                ('is_dir', '=', True),
            ])
            if not cache_entries:
                continue

            # Normalfall: SCORSESE hat den Speicher-Root gebrowst und alle
            # direkten Kinder stehen mit browse_parent_path == storage_root im Cache.
            root_children = cache_entries.filtered(lambda item: _same_path(item.browse_parent_path, storage_root))

            # Fallback 1: Falls alte Cache-Einträge nur child_path enthalten oder
            # browse_parent_path mit anderer Slash-Schreibweise gespeichert wurde,
            # berechnen wir direkte Kinder anhand des vollständigen Pfads.
            if not root_children:
                root_children = cache_entries.filtered(lambda item: _same_path(_path_parent(item.child_path), storage_root))

            # Fallback 2: Wenn der Speicher-Root selbst nie gebrowst wurde, aber
            # Unterordner bereits im Cache existieren, zeigen wir diese trotzdem an.
            # So bleibt der Wizard nutzbar und man muss keine Pfade kopieren.
            if not root_children:
                root_children = cache_entries

            rec.available_root_cache_ids = root_children

            selected_parent = _clean_scorsese_path(
                rec.root_folder_path or rec.root_folder_cache_id.child_path or False
            )
            if selected_parent:
                subfolders = cache_entries.filtered(lambda item: _same_path(item.browse_parent_path, selected_parent))
                if not subfolders:
                    subfolders = cache_entries.filtered(lambda item: _same_path(_path_parent(item.child_path), selected_parent))
                rec.available_subfolder_cache_ids = subfolders

    def _folder_cache_domain_result(self):
        self.ensure_one()
        return {
            'domain': {
                'root_folder_cache_id': [('id', 'in', self.available_root_cache_ids.ids)],
                'subfolder_cache_id': [('id', 'in', self.available_subfolder_cache_ids.ids)],
            }
        }

    @api.onchange('storage_id')
    def _onchange_storage_id(self):
        for rec in self:
            rec.root_folder_cache_id = False
            rec.root_folder_path = False
            rec.subfolder_cache_id = False
            if rec.storage_id:
                root = _clean_scorsese_path(rec.storage_id.root_path)
                rec.storage_root_path = root
                rec.parent_path = root
            else:
                rec.storage_root_path = False
                rec.parent_path = False
        if len(self) == 1:
            return self._folder_cache_domain_result()
        return {}

    @api.onchange('root_folder_cache_id')
    def _onchange_root_folder_cache_id(self):
        for rec in self:
            rec.subfolder_cache_id = False
            if rec.root_folder_cache_id:
                path = _clean_scorsese_path(rec.root_folder_cache_id.child_path)
                rec.root_folder_path = path
                rec.parent_path = path
            else:
                rec.root_folder_path = False
                rec.parent_path = _clean_scorsese_path(rec.storage_id.root_path) if rec.storage_id else False
        if len(self) == 1:
            return self._folder_cache_domain_result()
        return {}

    @api.onchange('subfolder_cache_id')
    def _onchange_subfolder_cache_id(self):
        for rec in self:
            if rec.subfolder_cache_id:
                rec.parent_path = _clean_scorsese_path(rec.subfolder_cache_id.child_path)
            elif rec.root_folder_cache_id:
                rec.parent_path = _clean_scorsese_path(rec.root_folder_cache_id.child_path)
            elif rec.storage_id:
                rec.parent_path = _clean_scorsese_path(rec.storage_id.root_path)

    @api.onchange('project_date_start')
    def _onchange_project_date_start(self):
        for rec in self:
            if rec.target_model == 'project.project' and rec.project_date_start and rec.target_res_id:
                record = self.env[rec.target_model].browse(rec.target_res_id)
                if record.exists():
                    rec.folder_name = rec._folder_name_for_record(record, date_for_name=rec.project_date_start)

    def _get_target_record(self):
        self.ensure_one()
        if not self.target_model or not self.target_res_id:
            raise UserError(_('Kein Zieldatensatz im Wizard-Kontext.'))
        record = self.env[self.target_model].browse(self.target_res_id)
        if not record.exists():
            raise UserError(_('Der Zieldatensatz existiert nicht mehr.'))
        return record

    def _project_date_write_values(self, model):
        self.ensure_one()
        vals = {}
        if self.project_date_start:
            if 'date_start' in model._fields:
                vals['date_start'] = self.project_date_start
            elif 'date' in model._fields:
                vals['date'] = self.project_date_start
        if self.project_date_end:
            if 'date_end' in model._fields:
                vals['date_end'] = self.project_date_end
            elif 'date' in model._fields:
                vals['date'] = self.project_date_end
        return vals

    def _create_project_from_event(self, event):
        self.ensure_one()
        Project = self.env['project.project'].sudo()
        vals = {
            'name': event.name or event.display_name,
        }
        if 'company_id' in Project._fields and getattr(event, 'company_id', False):
            vals['company_id'] = event.company_id.id
        vals.update(self._project_date_write_values(Project))
        project = Project.create(vals)
        event.sudo().write({'gl_scorsese_project_id': project.id})
        if 'gl_scorsese_event_id' in project._fields:
            project.sudo().write({'gl_scorsese_event_id': event.id})
        if hasattr(event, 'message_post'):
            event.message_post(body=_('SCORSESE: Zugehöriges Projekt wurde erstellt und verknüpft: %s') % project.display_name)
        return project

    def _sync_project_dates_to_target(self, record):
        self.ensure_one()
        if record._name != 'project.project':
            return
        vals = self._project_date_write_values(record)
        if vals:
            record.sudo().write(vals)

    def action_enqueue(self):
        self.ensure_one()
        record = self._get_target_record()
        self._sync_project_dates_to_target(record)

        if self.create_project_from_event and record._name == 'event.event':
            if record.gl_scorsese_project_id:
                project = record.gl_scorsese_project_id
                date_vals = self._project_date_write_values(project)
                if date_vals:
                    project.sudo().write(date_vals)
            else:
                self._create_project_from_event(record)

        parent_path = _clean_scorsese_path(self.parent_path or self.storage_id.root_path)
        job = record._gl_queue_create_folder(
            self.storage_id,
            self.template_id,
            parent_path=parent_path,
            folder_name=self.folder_name,
            check_connection=True,
        )
        target_label = _('Projektordner') if self.target_model == 'project.project' else _('Veranstaltungsordner')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('SCORSESE'),
                'message': _('%s wurde an SCORSESE übergeben. Die Bestätigung „%s wurde erstellt“ erscheint im Chatter, sobald der Agent fertig ist. Auftrag: %s') % (target_label, target_label, job.display_name),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def action_request_browse(self):
        self.ensure_one()
        if not self.storage_id:
            raise UserError(_('Bitte zuerst einen Speicher auswählen.'))
        path = _clean_scorsese_path(self.parent_path or self.storage_id.root_path)
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
                'message': _('SCORSESE lädt die Unterordner in den Cache. Danach sind sie im Dropdown sichtbar.'),
                'type': 'info',
                'sticky': False,
            }
        }

    def action_open_cache(self):
        self.ensure_one()
        domain = [('storage_id', '=', self.storage_id.id)]
        parent_path = _clean_scorsese_path(self.parent_path or self.storage_id.root_path)
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
