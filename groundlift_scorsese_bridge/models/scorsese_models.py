# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)


def _json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=False, indent=2, default=str)


def _json_loads(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    return json.loads(value)


def clean_scorsese_path(value):
    """Entfernt versehentlich mitgespeicherte Anführungszeichen an Windows-Pfaden."""
    value = (value or '').strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    return value.strip().strip('\"').strip("'").strip().rstrip('\\/')


def _sanitize_path_vals(vals, fields_to_clean):
    for field in fields_to_clean:
        if field in vals and vals.get(field):
            vals[field] = clean_scorsese_path(vals[field])
    return vals


class GlScorseseDashboard(models.Model):
    _name = 'gl.scorsese.dashboard'
    _description = 'SCORSESE Dashboard'

    name = fields.Char(default='SCORSESE', required=True)
    agent_online = fields.Boolean(string='SCORSESE verbunden', compute='_compute_dashboard_values')
    last_heartbeat = fields.Datetime(string='Letzter Heartbeat', compute='_compute_dashboard_values')
    queued_job_count = fields.Integer(string='Wartende Aufträge', compute='_compute_dashboard_values')
    failed_job_count = fields.Integer(string='Fehlgeschlagene Aufträge', compute='_compute_dashboard_values')
    path_cache_count = fields.Integer(string='Ordner im Cache', compute='_compute_dashboard_values')

    def _compute_dashboard_values(self):
        Agent = self.env['gl.scorsese.agent'].sudo()
        Job = self.env['gl.scorsese.job'].sudo()
        Cache = self.env['gl.scorsese.path.cache'].sudo()
        agent = Agent.get_default_agent()
        queued_count = Job.search_count([('state', 'in', ('queued', 'running'))])
        failed_count = Job.search_count([('state', '=', 'failed')])
        cache_count = Cache.search_count([])
        for rec in self:
            rec.agent_online = bool(agent.is_online)
            rec.last_heartbeat = agent.last_heartbeat
            rec.queued_job_count = queued_count
            rec.failed_job_count = failed_count
            rec.path_cache_count = cache_count

    def action_open_import_wizard(self):
        self.ensure_one()
        return self.env.ref('groundlift_scorsese_bridge.action_gl_scorsese_import_wizard').read()[0]

    def action_open_connection(self):
        self.ensure_one()
        return self.env.ref('groundlift_scorsese_bridge.action_gl_scorsese_agent').read()[0]

    def action_open_jobs(self):
        self.ensure_one()
        return self.env.ref('groundlift_scorsese_bridge.action_gl_scorsese_job').read()[0]

    def action_open_storage(self):
        self.ensure_one()
        return self.env.ref('groundlift_scorsese_bridge.action_gl_scorsese_storage').read()[0]

    def action_open_templates(self):
        self.ensure_one()
        return self.env.ref('groundlift_scorsese_bridge.action_gl_scorsese_template').read()[0]


class GlScorseseStorage(models.Model):
    _name = 'gl.scorsese.storage'
    _description = 'SCORSESE Speicherpfad'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(help='Kurzer technischer Code, z. B. produktion, postproduktion, archiv_1')
    root_path = fields.Char(required=True, help='UNC- oder lokaler Windows-Pfad, z. B. \\SERVER\\Produktion oder D:\\Produktion')
    storage_type = fields.Selection([
        ('public_events', 'Öffentliche Veranstaltungen'),
        ('production', 'Produktion'),
        ('postproduction', 'Postproduktion'),
        ('archive', 'Archiv'),
        ('custom', 'Sonstiger Speicher'),
    ], default='custom', required=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            _sanitize_path_vals(vals, ['root_path'])
        return super().create(vals_list)

    def write(self, vals):
        _sanitize_path_vals(vals, ['root_path'])
        return super().write(vals)

    _sql_constraints = [
        ('gl_storage_code_unique', 'unique(code)', 'Der technische Code des Speicherpfads muss eindeutig sein.'),
    ]


class GlScorseseTemplate(models.Model):
    _name = 'gl.scorsese.template'
    _description = 'SCORSESE Ordnervorlage'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    template_path = fields.Char(required=True, help='Pfad zur lokalen Vorlage auf SCORSESE oder einem erreichbaren Speicher')
    target_model = fields.Selection([
        ('event.event', 'Veranstaltungen'),
        ('project.project', 'Projekte'),
        ('both', 'Veranstaltungen und Projekte'),
    ], default='both', required=True)
    active = fields.Boolean(default=True)
    is_default_event = fields.Boolean(string='Standard für Veranstaltungen')
    is_default_project = fields.Boolean(string='Standard für Projekte')
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            _sanitize_path_vals(vals, ['template_path'])
        return super().create(vals_list)

    def write(self, vals):
        _sanitize_path_vals(vals, ['template_path'])
        return super().write(vals)

    @api.constrains('is_default_event', 'is_default_project', 'target_model')
    def _check_single_default(self):
        for rec in self:
            if rec.is_default_event:
                domain = [('id', '!=', rec.id), ('is_default_event', '=', True), ('active', '=', True)]
                if self.search_count(domain):
                    raise UserError(_('Es darf nur eine aktive Standard-Vorlage für Veranstaltungen geben.'))
            if rec.is_default_project:
                domain = [('id', '!=', rec.id), ('is_default_project', '=', True), ('active', '=', True)]
                if self.search_count(domain):
                    raise UserError(_('Es darf nur eine aktive Standard-Vorlage für Projekte geben.'))


class GlScorseseAgent(models.Model):
    _name = 'gl.scorsese.agent'
    _description = 'SCORSESE Agent Status'
    _order = 'name'

    name = fields.Char(required=True, default='SCORSESE')
    machine = fields.Char()
    version = fields.Char()
    last_heartbeat = fields.Datetime()
    last_message = fields.Char()
    online_threshold_minutes = fields.Integer(default=5)
    is_online = fields.Boolean(compute='_compute_is_online', string='Verbunden')

    @api.depends('last_heartbeat', 'online_threshold_minutes')
    def _compute_is_online(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_online = bool(
                rec.last_heartbeat and
                rec.last_heartbeat >= now - timedelta(minutes=rec.online_threshold_minutes or 5)
            )

    @api.model
    def get_default_agent(self):
        agent = self.search([('name', '=', 'SCORSESE')], limit=1)
        if not agent:
            agent = self.create({'name': 'SCORSESE'})
        return agent


class GlScorsesePathCache(models.Model):
    _name = 'gl.scorsese.path.cache'
    _description = 'SCORSESE Ordnercache'
    _rec_name = 'child_name'
    _order = 'storage_id, browse_parent_path, child_name'

    storage_id = fields.Many2one('gl.scorsese.storage', required=True, ondelete='cascade')
    # WICHTIG: Der technische Feldname 'parent_path' ist in Odoo intern reserviert
    # und darf für normale Fachlogik nicht als Pflichtfeld verwendet werden.
    # In frueheren Versionen dieses Moduls existierte parent_path als required=True
    # und fuehrte unter Odoo 19 zu NOT NULL-Fehlern beim Anlegen von Cacheeintraegen.
    browse_parent_path = fields.Char(string='Parent Path', required=True, index=True)
    child_name = fields.Char(required=True)
    child_path = fields.Char(required=True, index=True)
    is_dir = fields.Boolean(default=True)
    last_seen = fields.Datetime(default=fields.Datetime.now)

    _sql_constraints = [
        ('gl_path_cache_unique', 'unique(storage_id, child_path)', 'Dieser Pfad ist für den Speicher bereits im Cache.'),
    ]

    def init(self):
        # Kompatibilitaetsfix fuer fruehe Modulversionen:
        # Dort gab es eine Spalte parent_path NOT NULL. Dieser Feldname kollidiert
        # mit Odoos internem Parent-Store-Konzept und kann beim Create auf NULL fallen.
        # Damit bestehende Staging-Datenbanken nach dem Upgrade nicht blockieren,
        # wird die alte Spalte, falls vorhanden, entschaerft und in das neue Feld
        # browse_parent_path migriert.
        cr = self.env.cr
        cr.execute("""
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'gl_scorsese_path_cache'
               AND column_name = 'parent_path'
        """)
        if cr.fetchone():
            cr.execute("ALTER TABLE gl_scorsese_path_cache ALTER COLUMN parent_path DROP NOT NULL")
            cr.execute("""
                UPDATE gl_scorsese_path_cache
                   SET browse_parent_path = COALESCE(NULLIF(browse_parent_path, ''), parent_path, '')
                 WHERE COALESCE(browse_parent_path, '') = ''
            """)


class GlScorseseJob(models.Model):
    _name = 'gl.scorsese.job'
    _description = 'SCORSESE Auftrag'
    _inherit = ['mail.thread']
    _order = 'priority, create_date desc'

    name = fields.Char(default='Neuer SCORSESE Auftrag', required=True, tracking=True)
    job_type = fields.Selection([
        ('create_folder_from_template', 'Ordner aus Vorlage erstellen'),
        ('set_folder_icon', 'Ordnericon setzen'),
        ('browse_folder', 'Ordner durchsuchen'),
        ('validate_folder', 'Ordner validieren'),
    ], required=True, tracking=True)
    state = fields.Selection([
        ('queued', 'Wartet'),
        ('running', 'Läuft'),
        ('done', 'Erledigt'),
        ('failed', 'Fehler'),
        ('cancelled', 'Abgebrochen'),
    ], default='queued', required=True, tracking=True, index=True)
    priority = fields.Integer(default=10, help='Kleiner Wert = höhere Priorität')
    target_model = fields.Char(index=True)
    target_res_id = fields.Integer(index=True)
    target_display_name = fields.Char()
    payload_json = fields.Text(required=True, default='{}')
    result_json = fields.Text(default='{}')
    last_error = fields.Text(tracking=True)
    agent_name = fields.Char(default='SCORSESE')
    attempts = fields.Integer(default=0)
    max_attempts = fields.Integer(default=3)
    claimed_at = fields.Datetime()
    completed_at = fields.Datetime()
    requested_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)

    payload_pretty = fields.Text(compute='_compute_payload_pretty')
    result_pretty = fields.Text(compute='_compute_result_pretty')

    @api.depends('payload_json')
    def _compute_payload_pretty(self):
        for rec in self:
            try:
                rec.payload_pretty = _json_dumps(_json_loads(rec.payload_json))
            except Exception:
                rec.payload_pretty = rec.payload_json or '{}'

    @api.depends('result_json')
    def _compute_result_pretty(self):
        for rec in self:
            try:
                rec.result_pretty = _json_dumps(_json_loads(rec.result_json))
            except Exception:
                rec.result_pretty = rec.result_json or '{}'

    @api.model
    def create_job(self, job_type, target_record=None, payload=None, priority=10, name=None):
        payload = payload or {}
        vals = {
            'job_type': job_type,
            'priority': priority,
            'payload_json': _json_dumps(payload),
            'name': name or self._default_job_name(job_type, target_record),
        }
        if target_record:
            vals.update({
                'target_model': target_record._name,
                'target_res_id': target_record.id,
                'target_display_name': target_record.display_name,
            })
        job = self.create(vals)
        if target_record and hasattr(target_record, 'message_post'):
            target_record.message_post(body=_('SCORSESE Auftrag angelegt: %s') % job.display_name)
        return job

    @api.model
    def _default_job_name(self, job_type, target_record=None):
        label = dict(self._fields['job_type'].selection).get(job_type, job_type)
        if target_record:
            return '%s – %s' % (label, target_record.display_name)
        return label

    def action_retry(self):
        for rec in self:
            if rec.state not in ('failed', 'cancelled'):
                continue
            rec.write({
                'state': 'queued',
                'last_error': False,
                'claimed_at': False,
                'completed_at': False,
            })

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_open_target(self):
        self.ensure_one()
        if not self.target_model or not self.target_res_id:
            raise UserError(_('Dieser Auftrag hat keinen Zieldatensatz.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.target_model,
            'res_id': self.target_res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def agent_heartbeat(self, agent_name='SCORSESE', version=None, machine=None, message=None):
        """Called by the local SCORSESE agent via JSON-2 API."""
        agent = self.env['gl.scorsese.agent'].sudo().search([('name', '=', agent_name)], limit=1)
        if not agent:
            agent = self.env['gl.scorsese.agent'].sudo().create({'name': agent_name})
        agent.sudo().write({
            'last_heartbeat': fields.Datetime.now(),
            'version': version or agent.version,
            'machine': machine or agent.machine,
            'last_message': message or 'OK',
        })
        return {'ok': True, 'server_time': fields.Datetime.now()}

    @api.model
    def agent_claim_jobs(self, agent_name='SCORSESE', limit=3):
        """Called by SCORSESE. Returns queued jobs and marks them running.

        JSON-2 calls use named arguments only, therefore the signature avoids *args.
        """
        self.agent_heartbeat(agent_name=agent_name, message='claim_jobs')
        limit = int(limit or 3)
        # Reset stale running jobs older than 30 minutes.
        stale_dt = fields.Datetime.now() - timedelta(minutes=30)
        stale_jobs = self.sudo().search([
            ('state', '=', 'running'),
            ('claimed_at', '<', stale_dt),
            ('attempts', '<', 999999),
        ])
        if stale_jobs:
            stale_jobs.sudo().write({'state': 'queued', 'last_error': 'Auftrag war zu lange im Status Läuft und wurde erneut freigegeben.'})

        jobs = self.sudo().search([('state', '=', 'queued')], order='priority, create_date', limit=limit)
        result = []
        for job in jobs:
            job.sudo().write({
                'state': 'running',
                'agent_name': agent_name,
                'attempts': job.attempts + 1,
                'claimed_at': fields.Datetime.now(),
                'last_error': False,
            })
            result.append({
                'id': job.id,
                'name': job.name,
                'job_type': job.job_type,
                'target_model': job.target_model,
                'target_res_id': job.target_res_id,
                'target_display_name': job.target_display_name,
                'payload': _json_loads(job.payload_json),
            })
        return result

    @api.model
    def agent_report_job(self, job_id, state, result=None, error=None, agent_name='SCORSESE'):
        """Called by SCORSESE after execution."""
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            return {'ok': False, 'error': 'job_not_found'}
        if job.agent_name and job.agent_name != agent_name:
            _logger.warning('Agent name mismatch for job %s: %s != %s', job.id, job.agent_name, agent_name)
        result = result or {}
        vals = {
            'result_json': _json_dumps(result),
            'completed_at': fields.Datetime.now(),
        }
        if state == 'done':
            vals.update({'state': 'done', 'last_error': False})
            job.sudo().write(vals)
            job.sudo()._apply_success_result(result)
        else:
            vals.update({'state': 'failed', 'last_error': error or result.get('error') or 'Unbekannter Fehler'})
            job.sudo().write(vals)
            job.sudo()._notify_target(_('SCORSESE Fehler: %s') % vals['last_error'])
        self.agent_heartbeat(agent_name=agent_name, message='reported %s' % job.id)
        return {'ok': True, 'job_id': job.id, 'state': job.state}

    def _notify_target(self, message):
        self.ensure_one()
        if not self.target_model or not self.target_res_id:
            return
        record = self.env[self.target_model].sudo().browse(self.target_res_id)
        if record.exists() and hasattr(record, 'message_post'):
            record.message_post(body=message)

    def _apply_success_result(self, result):
        for job in self:
            if job.job_type == 'create_folder_from_template':
                job._apply_create_folder_result(result)
            elif job.job_type == 'set_folder_icon':
                job._apply_icon_result(result)
            elif job.job_type == 'browse_folder':
                job._apply_browse_folder_result(result)
            else:
                job._notify_target(_('SCORSESE Auftrag erfolgreich abgeschlossen.'))

    def _apply_create_folder_result(self, result):
        self.ensure_one()
        target_path = clean_scorsese_path(result.get('target_path') or _json_loads(self.payload_json).get('target_path'))
        if self.target_model and self.target_res_id and target_path:
            record = self.env[self.target_model].sudo().browse(self.target_res_id)
            if record.exists():
                values = {}
                if 'gl_folder_path' in record._fields:
                    values['gl_folder_path'] = target_path
                if 'gl_folder_status' in record._fields:
                    values['gl_folder_status'] = 'created'
                if 'gl_folder_pending' in record._fields:
                    values['gl_folder_pending'] = False
                if values:
                    record.sudo().write(values)
                if hasattr(record, 'message_post'):
                    if record._name == 'project.project':
                        record.message_post(body=_('✅ SCORSESE Projektordner wurde erstellt: <code>%s</code>') % target_path)
                    elif record._name == 'event.event':
                        record.message_post(body=_('✅ SCORSESE Veranstaltungsordner wurde erstellt: <code>%s</code>') % target_path)
                    else:
                        record.message_post(body=_('✅ SCORSESE Ordner wurde erstellt: <code>%s</code>') % target_path)
                if hasattr(record, '_gl_queue_current_stage_icon'):
                    try:
                        record._gl_queue_current_stage_icon(check_connection=False)
                    except Exception as exc:
                        if hasattr(record, 'message_post'):
                            record.message_post(body=_('SCORSESE konnte nach der Ordnererstellung kein Phasen-Icon beauftragen: %s') % exc)

    def _apply_icon_result(self, result):
        self.ensure_one()
        payload = _json_loads(self.payload_json)
        state_key = result.get('state_key') or payload.get('state_key')
        if self.target_model and self.target_res_id and state_key:
            record = self.env[self.target_model].sudo().browse(self.target_res_id)
            if record.exists():
                values = {}
                if 'gl_folder_state' in record._fields:
                    values['gl_folder_state'] = state_key
                if values:
                    record.sudo().write(values)
                if hasattr(record, 'message_post'):
                    record.message_post(body=_('SCORSESE Ordnericon wurde gesetzt: %s') % state_key)

    def _apply_browse_folder_result(self, result):
        self.ensure_one()
        payload = _json_loads(self.payload_json)
        storage_id = payload.get('storage_id')
        parent_path = clean_scorsese_path(result.get('parent_path') or payload.get('path') or payload.get('storage_root'))
        entries = result.get('entries') or []
        if not storage_id or not parent_path:
            return
        cache_model = self.env['gl.scorsese.path.cache'].sudo()
        for entry in entries:
            if not entry.get('is_dir', True):
                continue
            child_path = clean_scorsese_path(entry.get('path'))
            child_name = entry.get('name')
            if not child_path or not child_name:
                continue
            existing = cache_model.search([('storage_id', '=', storage_id), ('child_path', '=', child_path)], limit=1)
            vals = {
                'storage_id': storage_id,
                'browse_parent_path': parent_path,
                'child_name': child_name,
                'child_path': child_path,
                'is_dir': True,
                'last_seen': fields.Datetime.now(),
            }
            if existing:
                existing.write(vals)
            else:
                cache_model.create(vals)

    @api.model
    def get_connection_status(self):
        agent = self.env['gl.scorsese.agent'].sudo().get_default_agent()
        return {
            'agent': agent.name,
            'is_online': agent.is_online,
            'last_heartbeat': agent.last_heartbeat,
            'machine': agent.machine,
            'version': agent.version,
            'message': agent.last_message,
        }

    @api.model
    def join_path(self, root, child):
        root = clean_scorsese_path(root)
        child = (child or '').strip().strip('\"').strip("'").strip('\\/')
        if not root:
            return child
        sep = '\\' if ('\\' in root or (len(root) > 1 and root[1] == ':')) else '/'
        return root + sep + child
