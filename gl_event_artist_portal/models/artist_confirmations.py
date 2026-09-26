# -*- coding: utf-8 -*-
"""Setlist acknowledgement and backend rider approval with artist emails."""
import html

from odoo import _, fields, models
from odoo.exceptions import UserError

from .artist_media import RIDER_FIELDS

TECH_CONFIRM_PARAMETER = 'gl_event_artist_portal.tech_confirmation_text'
HOSPITALITY_CONFIRM_PARAMETER = 'gl_event_artist_portal.hospitality_confirmation_text'
DEFAULT_TECH_CONFIRMATION = (
    'Hallo,\n\n'
    'wir haben die Bühnenanweisung / den Technical Rider für {event} geprüft und bestätigt.\n'
    'Die Bestätigung ist auch in eurem Künstler-/Agenturportal hinterlegt:\n'
    '{portal_url}\n\nViele Grüße\nEuer GROUNDLIFT-Team'
)
DEFAULT_HOSPITALITY_CONFIRMATION = (
    'Hallo,\n\n'
    'wir haben den Hospitality Rider für {event} geprüft und bestätigt.\n'
    'Die Bestätigung ist auch in eurem Künstler-/Agenturportal hinterlegt:\n'
    '{portal_url}\n\nViele Grüße\nEuer GROUNDLIFT-Team'
)


class EventEvent(models.Model):
    _inherit = 'event.event'

    artist_portal_setlist_submitted = fields.Boolean(
        string='Setliste wurde eingereicht', copy=False, readonly=True)
    artist_portal_setlist_submitted_at = fields.Datetime(
        string='Setliste gemeldet am', copy=False, readonly=True)
    artist_portal_tech_confirmed = fields.Boolean(
        string='Technical Rider bestätigt', copy=False)
    artist_portal_hospitality_confirmed = fields.Boolean(
        string='Hospitality Rider bestätigt', copy=False)
    artist_portal_tech_confirmation_queued_at = fields.Datetime(
        string='Tech-Bestätigungsmail vorgemerkt am', copy=False, readonly=True)
    artist_portal_hospitality_confirmation_queued_at = fields.Datetime(
        string='Hospitality-Bestätigungsmail vorgemerkt am', copy=False, readonly=True)

    def _artist_portal_queue_rider_confirmation(self, kind):
        """Create exactly one mail for a new unchecked -> checked transition.

        Odoo.sh staging never receives an external recipient; production uses
        the very same contract contact that receives the portal invitation.
        """
        self.ensure_one()
        if kind not in RIDER_FIELDS:
            raise UserError(_('Unbekannte Rider-Art.'))
        staging = self._artist_portal_staging()
        contact = self.artist_portal_contract_contact_id
        if not staging and not (contact and contact.email and '@' in contact.email):
            raise UserError(_(
                'Bitte zuerst unter „Info für Band/Agentur“ den Vertragskontakt '
                'mit E-Mail-Adresse hinterlegen. Die Bestätigung wurde nicht gespeichert.'
            ))
        recipient = 'julius@groundlift.de' if staging else contact.email.strip()
        if not self.artist_portal_access_token:
            # Historical events normally have a token; restore only when missing.
            import uuid
            self.with_context(artist_portal_source=True).write({
                'artist_portal_access_token': uuid.uuid4().hex})
        portal_url = '%s/event/artist/%s/%s' % (
            self.get_base_url().rstrip('/'), self.id, self.artist_portal_access_token)
        kind_label = 'Technical Rider / Bühnenanweisung' if kind == 'tech' else 'Hospitality Rider'
        param_name, default_text = (
            (TECH_CONFIRM_PARAMETER, DEFAULT_TECH_CONFIRMATION) if kind == 'tech'
            else (HOSPITALITY_CONFIRM_PARAMETER, DEFAULT_HOSPITALITY_CONFIRMATION)
        )
        text = self.env['ir.config_parameter'].sudo().get_param(
            param_name, default=default_text) or ''
        text = (text.replace('{event}', self.name or '')
                    .replace('{portal_url}', portal_url)
                    .replace('{rider}', kind_label))
        if '{portal_url}' not in (self.env['ir.config_parameter'].sudo().get_param(
                param_name, default=default_text) or ''):
            text = (text + '\n\n' + portal_url).strip()
        label = '[STAGING TEST] ' if staging else ''
        email_from = self.company_id.email or self.env.user.email or 'info@groundlift.de'
        mail = self.env['mail.mail'].sudo().create({
            'subject': '%sGROUNDLIFT: %s bestätigt – %s' % (label, kind_label, self.name or ''),
            'body_html': '<div style="font-family:Arial,sans-serif;white-space:pre-line">%s</div>'
                         % html.escape(text),
            'email_to': recipient,
            'email_from': email_from,
            'reply_to': email_from,
            'auto_delete': False,
        })
        date_field = ('artist_portal_tech_confirmation_queued_at' if kind == 'tech'
                      else 'artist_portal_hospitality_confirmation_queued_at')
        self.with_context(artist_portal_source=True).write({date_field: fields.Datetime.now()})
        return mail

    def write(self, vals):
        confirm_fields = {
            'tech': 'artist_portal_tech_confirmed',
            'hospitality': 'artist_portal_hospitality_confirmed',
        }
        # The fast path preserves the normal Odoo bulk-write behaviour.
        if not any(name in vals for name in (*confirm_fields.values(), *RIDER_FIELDS.values())):
            return super().write(vals)
        # Preflight all records before writing. A failure rolls the transaction
        # back; no "confirmed" status may be shown without the queued email.
        for event in self:
            for kind, confirm_field in confirm_fields.items():
                if vals.get(confirm_field) and not event[confirm_field]:
                    rider_field = RIDER_FIELDS[kind]
                    new_content = vals.get(rider_field, event[rider_field] if rider_field in event._fields else False)
                    if rider_field not in event._fields or not new_content:
                        raise UserError(_(
                            'Bitte vor der Bestätigung den %s hochladen.'
                        ) % ('Technical Rider' if kind == 'tech' else 'Hospitality Rider'))
                    if not event._artist_portal_staging():
                        contact = event.artist_portal_contract_contact_id
                        if not (contact and contact.email and '@' in contact.email):
                            raise UserError(_(
                                'Bitte erst den Vertragskontakt mit E-Mail-Adresse eintragen. '
                                'Ohne Empfänger kann die Bestätigung nicht verschickt werden.'
                            ))
        for event in self:
            values = dict(vals)
            # A replacement invalidates the previous approval (from artist
            # portal OR backend); reapproval queues a fresh confirmation.
            for kind, rider_field in RIDER_FIELDS.items():
                confirm_field = confirm_fields[kind]
                if (rider_field in values and rider_field in event._fields
                        and values[rider_field] != event[rider_field]
                        and confirm_field not in values):
                    values[confirm_field] = False
            new_confirmations = [
                kind for kind, confirm_field in confirm_fields.items()
                if values.get(confirm_field) and not event[confirm_field]
            ]
            super(EventEvent, event).write(values)
            for kind in new_confirmations:
                event._artist_portal_queue_rider_confirmation(kind)
        return True
