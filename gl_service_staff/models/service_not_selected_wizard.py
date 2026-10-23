# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GLServiceNotSelectedWizard(models.TransientModel):
    _name = 'gl.service.not.selected.wizard'
    _description = 'Servicepersonal: Absagen für vollständig gebuchte Schicht'

    shift_id = fields.Many2one(
        'gl.service.shift', string='Veranstaltung / Projekt', required=True, readonly=True
    )
    resend_previous = fields.Boolean(
        string='Auch bereits abgesagte Personen erneut anschreiben', default=False,
        help=('Nur bewusst aktivieren: Bereits verschickte Absagen können dadurch '
              'erneut bei den Empfängern ankommen. Noch offene Mail-Freigaben '
              'werden niemals doppelt angelegt.'),
    )
    available_count = fields.Integer(string='Verfügbar, noch nicht gebucht', compute='_compute_preview')
    previous_count = fields.Integer(string='Bereits als abgesagt markiert', compute='_compute_preview')
    send_count = fields.Integer(string='Vorgesehene E-Mails', compute='_compute_preview')
    recipients_preview = fields.Text(string='Empfänger-Vorschau', compute='_compute_preview')

    @api.depends('shift_id', 'resend_previous')
    def _compute_preview(self):
        for wizard in self:
            lines = wizard.shift_id.line_ids
            eligible = lines.filtered(
                lambda line: line.state == 'available'
            )
            previous = lines.filtered(lambda line: line.state == 'not_selected')
            candidates = eligible
            if wizard.resend_previous:
                previous = wizard._excluding_open_mail_queue(previous)
                candidates |= previous
            deliverable = candidates.filtered(lambda line: bool(line.email))
            wizard.available_count = len(eligible)
            wizard.previous_count = len(lines.filtered(lambda line: line.state == 'not_selected'))
            wizard.send_count = len(deliverable)
            wizard.recipients_preview = '\n'.join(
                '%s – %s' % (line.member_id.name or '-', line.email)
                for line in deliverable.sorted(key=lambda line: (line.member_id.name or '').lower())
            ) or _('Keine Empfänger mit E-Mail-Adresse vorhanden.')

    def _excluding_open_mail_queue(self, lines):
        """An already queued decline must be approved, not queued again."""
        if not lines:
            return lines
        active = self.env['gl.service.mail.queue'].sudo().search([
            ('model_name', '=', 'gl.service.shift.line'),
            ('res_id', 'in', lines.ids),
            ('queue_kind', '=', 'not_selected'),
            ('state', 'in', ('pending', 'error')),
        ])
        return lines.filtered(lambda line: line.id not in set(active.mapped('res_id')))

    def action_confirm(self):
        self.ensure_one()
        shift = self.shift_id
        shift._check_manual_not_selected_access()
        booked = shift.line_ids.filtered(
            lambda line: line.state == 'accepted' and line.role == 'desired'
        )
        if shift.required_count <= 0 or len(booked) < shift.required_count:
            raise UserError(_('Die Serviceschicht ist nicht mehr vollständig besetzt.'))

        available = shift.line_ids.filtered(
            lambda line: line.state == 'available'
        )
        previous = shift.line_ids.filtered(lambda line: line.state == 'not_selected')
        repeat = self._excluding_open_mail_queue(previous) if self.resend_previous else previous.browse([])
        repeat = repeat.filtered(lambda line: bool(line.email))

        # Reuse the existing automatic close process (state, token revocation,
        # mail template and debug approval queue). The snapshot above ensures
        # that newly rejected staff do not get a duplicate on this same click.
        available_with_email = available.filtered(lambda line: bool(line.email))
        no_email_count = len(available) - len(available_with_email)
        if available:
            shift._close_full_staffing()

        for line in repeat:
            line._send_template(
                'gl_service_staff.mail_template_service_not_selected',
                param_name='gl_service_staff.not_selected_template_id',
                queue_kind='not_selected',
            )
            line.message_post(body=_(
                'Manueller erneuter Versand der Absage wegen vollständiger Besetzung '
                'durch %s vorbereitet/ausgelöst.'
            ) % self.env.user.name)

        count = len(available_with_email) + len(repeat)
        shift.message_post(body=_(
            'Service-Absagen manuell durch %s ausgelöst: %s E-Mail(s) '
            'vorbereitet/angestoßen, %s neue Absage(n), %s erneut angefragt.'
        ) % (self.env.user.name, count, len(available_with_email), len(repeat)))
        if count:
            delivery = (_('in die Mail-Freigabe gestellt') if shift._gl_mail_debugging_enabled()
                        else _('an den Mailversand übergeben'))
            message = _('%s Absage(n) %s.') % (count, delivery)
        else:
            message = _('Keine neuen Absagen: alle verfügbaren Personen wurden bereits berücksichtigt.')
        if no_email_count:
            message += _(' Hinweis: %s Person(en) ohne E-Mail-Adresse konnten nicht angeschrieben werden.') % no_email_count
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Service-Absagen'),
                'message': message,
                'type': 'success' if count else 'warning',
                'sticky': False,
            },
        }
