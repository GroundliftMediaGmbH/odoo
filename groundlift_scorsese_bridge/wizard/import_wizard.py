# -*- coding: utf-8 -*-
import re
from datetime import date, datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _clean_scorsese_path(value):
    value = (value or '').strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    return value.strip().strip('\"').strip("'").strip().rstrip('\\/')


def _clean_path_basename(path):
    path = _clean_scorsese_path(path)
    return re.split(r'[\\/]+', path)[-1].strip()


def _norm_path_for_compare(value):
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
    _description = 'SCORSESE Veranstaltung/Projekt importieren'

    storage_id = fields.Many2one('gl.scorsese.storage', string='Speicher', required=True)
    show_unlinked_only = fields.Boolean(
        string='Nur nicht verknüpfte Ordner anzeigen',
        default=True,
        help='Wenn aktiv, werden im Ordnerpfad-Dropdown nur Cache-Ordner angezeigt, die noch mit keinem Projekt und keiner Veranstaltung verknüpft sind.',
    )
    available_cache_ids = fields.Many2many(
        'gl.scorsese.path.cache',
        'gl_scorsese_import_available_cache_rel',
        'wizard_id',
        'cache_id',
        string='Verfügbare Cache-Ordner',
        compute='_compute_available_cache_ids',
    )
    available_root_cache_ids = fields.Many2many(
        'gl.scorsese.path.cache',
        'gl_scorsese_import_root_cache_rel',
        'wizard_id',
        'cache_id',
        string='Verfügbare Hauptordner',
        compute='_compute_available_cache_ids',
    )
    available_subfolder_cache_ids = fields.Many2many(
        'gl.scorsese.path.cache',
        'gl_scorsese_import_sub_cache_rel',
        'wizard_id',
        'cache_id',
        string='Verfügbare Unterordner',
        compute='_compute_available_cache_ids',
    )
    cached_folder_id = fields.Many2one(
        'gl.scorsese.path.cache',
        string='Ordnerpfad',
        help='Interner/finaler ausgewählter Cacheordner. Wird automatisch aus Ordner oder Unterordner gesetzt.',
    )
    root_folder_cache_id = fields.Many2one(
        'gl.scorsese.path.cache',
        string='Ordner wählen',
        help='Erste Ordnerebene innerhalb des gewählten Speichers.',
    )
    subfolder_cache_id = fields.Many2one(
        'gl.scorsese.path.cache',
        string='Unterordner wählen',
        help='Optionaler Unterordner innerhalb des gewählten Ordners.',
    )
    folder_path = fields.Char(string='Ausgewählter vollständiger Pfad', readonly=True)
    target_model = fields.Selection([
        ('project.project', 'Projekt'),
        ('event.event', 'Veranstaltung'),
        ('both', 'Projekt und Veranstaltung'),
    ], string='Importieren als', default='project.project', required=True)
    name = fields.Char(string='Titel')
    parsed_date = fields.Date(string='Datum')
    existing_project_id = fields.Many2one('project.project', string='Bestehendes Projekt verknüpfen')
    existing_event_id = fields.Many2one('event.event', string='Bestehende Veranstaltung verknüpfen')
    create_validation_job = fields.Boolean(string='Ordner von SCORSESE validieren lassen', default=False)

    def _linked_folder_paths(self):
        """Return normalized SCORSESE folder paths already linked to projects/events.

        This is intentionally computed at wizard runtime instead of stored on the
        cache entries, because projects/events may be linked, unlinked, imported
        or modified outside the cache model.
        """
        paths = set()
        for model_name in ('project.project', 'event.event'):
            Model = self.env[model_name].sudo()
            if 'gl_folder_path' not in Model._fields:
                continue
            for rec in Model.search([('gl_folder_path', '!=', False)]):
                path = _clean_scorsese_path(rec.gl_folder_path)
                if path:
                    paths.add(path.casefold())
        return paths

    def _cache_entries_for_storage(self, storage):
        storage = storage or self.storage_id
        if not storage:
            return self.env['gl.scorsese.path.cache'].sudo().browse()
        return self.env['gl.scorsese.path.cache'].sudo().search([
            ('storage_id', '=', storage.id),
            ('is_dir', '=', True),
        ])

    def _root_children_for_storage(self, storage, entries=False):
        entries = entries or self._cache_entries_for_storage(storage)
        if not storage or not entries:
            return entries.browse()
        storage_root = _clean_scorsese_path(storage.root_path)
        root_children = entries.filtered(lambda item: _same_path(item.browse_parent_path, storage_root))
        if not root_children:
            root_children = entries.filtered(lambda item: _same_path(_path_parent(item.child_path), storage_root))
        # Fallback: Wenn nur Unterebenen gecacht wurden, zeigen wir die vorhandenen Einträge trotzdem an.
        return root_children or entries

    def _navigation_entries_for_storage(self, storage, entries=False):
        """Return all cached folders that may be used as the current navigation point.

        Earlier versions separated the selector into first-level folder and one
        optional subfolder. That limited the UI to two directory levels. The
        selector now keeps the same visible fields, but treats the first field as
        the current folder: choosing an item in the subfolder field promotes that
        folder to the current folder, so the next level can be selected.
        """
        entries = entries or self._cache_entries_for_storage(storage)
        if not storage or not entries:
            return entries.browse()
        return entries

    def _filter_unlinked_cache_entries(self, cache_entries, linked_paths):
        if not linked_paths:
            return cache_entries
        return cache_entries.filtered(
            lambda item: _clean_scorsese_path(item.child_path).casefold() not in linked_paths
        )

    @api.depends('storage_id', 'show_unlinked_only', 'root_folder_cache_id', 'root_folder_cache_id.child_path')
    def _compute_available_cache_ids(self):
        Cache = self.env['gl.scorsese.path.cache'].sudo()
        linked_paths = self._linked_folder_paths() if any(self.mapped('show_unlinked_only')) else set()
        for rec in self:
            rec.available_cache_ids = Cache.browse()
            rec.available_root_cache_ids = Cache.browse()
            rec.available_subfolder_cache_ids = Cache.browse()
            if not rec.storage_id:
                continue
            cache_entries = rec._cache_entries_for_storage(rec.storage_id)
            if not cache_entries:
                continue
            if rec.show_unlinked_only:
                cache_entries = rec._filter_unlinked_cache_entries(cache_entries, linked_paths)
            rec.available_cache_ids = cache_entries
            rec.available_root_cache_ids = rec._navigation_entries_for_storage(rec.storage_id, cache_entries)
            selected_parent = _clean_scorsese_path(
                rec.root_folder_cache_id.child_path if rec.root_folder_cache_id else False
            )
            if selected_parent:
                subfolders = cache_entries.filtered(lambda item: _same_path(item.browse_parent_path, selected_parent))
                if not subfolders:
                    subfolders = cache_entries.filtered(lambda item: _same_path(_path_parent(item.child_path), selected_parent))
                rec.available_subfolder_cache_ids = subfolders

    def _domain_result(self):
        self.ensure_one()
        return {
            'domain': {
                'root_folder_cache_id': [('id', 'in', self.available_root_cache_ids.ids)],
                'subfolder_cache_id': [('id', 'in', self.available_subfolder_cache_ids.ids)],
                'cached_folder_id': [('id', 'in', self.available_cache_ids.ids)],
            }
        }

    def _set_final_folder_from_selection(self):
        for rec in self:
            final_cache = rec.subfolder_cache_id or rec.root_folder_cache_id or rec.cached_folder_id
            rec.cached_folder_id = final_cache
            if final_cache:
                rec.folder_path = _clean_scorsese_path(final_cache.child_path)
                if not rec.storage_id:
                    rec.storage_id = final_cache.storage_id
                title, parsed_date = rec._parse_folder_name(rec.folder_path)
                rec.name = title
                rec.parsed_date = parsed_date
            else:
                rec.folder_path = False

    @api.onchange('storage_id', 'show_unlinked_only')
    def _onchange_storage_filter(self):
        for rec in self:
            rec.cached_folder_id = False
            rec.root_folder_cache_id = False
            rec.subfolder_cache_id = False
            rec.folder_path = False
            rec.name = False
            rec.parsed_date = False
        if len(self) == 1:
            return self._domain_result()
        return {}

    @api.onchange('storage_id')
    def _onchange_storage_id(self):
        for rec in self:
            rec.cached_folder_id = False
            rec.root_folder_cache_id = False
            rec.subfolder_cache_id = False
            rec.folder_path = False
            rec.name = False
            rec.parsed_date = False
        if len(self) == 1:
            return self._domain_result()
        return {}

    @api.onchange('root_folder_cache_id')
    def _onchange_root_folder_cache_id(self):
        for rec in self:
            rec.subfolder_cache_id = False
        self._set_final_folder_from_selection()
        if len(self) == 1:
            return self._domain_result()
        return {}

    @api.onchange('subfolder_cache_id')
    def _onchange_subfolder_cache_id(self):
        # Eine Auswahl im Unterordner-Dropdown wird sofort zum aktuellen Ordner.
        # Dadurch kann man beliebig tief navigieren: Unterordner wählen -> der
        # gewählte Unterordner wird oben als aktueller Ordner gesetzt -> dessen
        # Unterordner erscheinen wieder im Unterordner-Dropdown.
        for rec in self:
            if rec.subfolder_cache_id:
                rec.root_folder_cache_id = rec.subfolder_cache_id
                rec.subfolder_cache_id = False
        self._set_final_folder_from_selection()
        if len(self) == 1:
            return self._domain_result()
        return {}

    @api.onchange('cached_folder_id')
    def _onchange_cached_folder_id(self):
        # Rückwärtskompatibilität für ältere Views/Bookmarks: Falls das alte finale Feld direkt gesetzt wird,
        # übernehmen wir es weiterhin als ausgewählten Pfad.
        self._set_final_folder_from_selection()
    @api.onchange('folder_path')
    def _onchange_folder_path(self):
        for rec in self:
            title, parsed_date = rec._parse_folder_name(rec.folder_path)
            if rec.folder_path and (not rec.name or rec.name in ('Importiertes Projekt', 'Importierte Veranstaltung')):
                rec.name = title
            if rec.folder_path and not rec.parsed_date:
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

    def _ensure_folder_path_from_cache(self):
        self.ensure_one()
        final_cache = self.subfolder_cache_id or self.root_folder_cache_id or self.cached_folder_id
        if final_cache:
            self.cached_folder_id = final_cache
            self.folder_path = _clean_scorsese_path(final_cache.child_path)
            if not self.storage_id:
                self.storage_id = final_cache.storage_id
        else:
            self.folder_path = _clean_scorsese_path(self.folder_path)

    def _validate_inputs(self):
        self.ensure_one()
        self._ensure_folder_path_from_cache()
        if not self.storage_id:
            raise UserError(_('Bitte zuerst einen Speicher auswählen.'))
        if not self.folder_path:
            raise UserError(_('Bitte einen Ordner aus dem Ordnerpfad-Dropdown auswählen.'))

    def _queue_browse_job(self, path, message):
        self.ensure_one()
        if not self.storage_id:
            raise UserError(_('Bitte zuerst einen Speicher auswählen.'))
        path = _clean_scorsese_path(path or self.storage_id.root_path)
        if not path:
            raise UserError(_('Der Speicher hat keinen gültigen Root-Pfad.'))
        self.env['gl.scorsese.job'].create_job(
            'browse_folder',
            target_record=None,
            payload={
                'storage_id': self.storage_id.id,
                'storage_name': self.storage_id.name,
                'storage_root': _clean_scorsese_path(self.storage_id.root_path),
                'path': path,
            },
            priority=20,
            name=_('Ordnercache aktualisieren – %s') % path,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('SCORSESE'),
                'message': message,
                'type': 'info',
                'sticky': False,
            }
        }

    def action_browse_storage_root(self):
        self.ensure_one()
        return self._queue_browse_job(
            self.storage_id.root_path,
            _('SCORSESE lädt die Ordnerstruktur des ausgewählten Speichers. Öffne das Dropdown nach wenigen Sekunden erneut oder lade das Fenster kurz neu.'),
        )

    def action_browse_selected_folder(self):
        self.ensure_one()
        # Gezielt den aktuell markierten Ordner laden: erst Unterordner, sonst Hauptordner, sonst Speicher-Root.
        if self.subfolder_cache_id:
            path = self.subfolder_cache_id.child_path
        elif self.root_folder_cache_id:
            path = self.root_folder_cache_id.child_path
        elif self.cached_folder_id:
            path = self.cached_folder_id.child_path
        else:
            path = self.storage_id.root_path if self.storage_id else False
        if not path:
            raise UserError(_('Bitte zuerst einen Speicher oder Ordner auswählen.'))
        return self._queue_browse_job(
            path,
            _('SCORSESE lädt die nächste Ordnerebene. Danach sind Unterordner im Dropdown sichtbar.'),
        )

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
