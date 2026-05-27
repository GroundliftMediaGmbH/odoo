# -*- coding: utf-8 -*-
import uuid
from urllib.parse import quote

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


QUANTITY_SELECTION = [(str(i), str(i)) for i in range(1, 21)]
ORDERED_BY_SELECTION = [
    ('email', 'E-Mail'),
    ('phone', 'Telefon'),
    ('personal', 'Persönlich'),
]


class EventEvent(models.Model):
    _inherit = 'event.event'

    guestlist_line_ids = fields.One2many(
        'gl.event.guestlist.line',
        'event_id',
        string='Gästeliste',
        copy=False,
    )
    guestlist_price_option_ids = fields.One2many(
        'gl.event.guestlist.price.option',
        'event_id',
        string='Gästelisten-Preisoptionen',
        copy=False,
    )
    guestlist_access_token = fields.Char(
        string='Gästelisten-Zugriffstoken',
        default=lambda self: uuid.uuid4().hex,
        copy=False,
        readonly=True,
    )
    guestlist_public_url = fields.Char(
        string='Gästelisten-Link',
        compute='_compute_guestlist_public_url',
        readonly=True,
    )
    guestlist_qr_html = fields.Html(
        string='QR-Code',
        compute='_compute_guestlist_qr_html',
        sanitize=False,
        readonly=True,
    )
    guestlist_total_qty = fields.Integer(
        string='Personen auf Gästeliste',
        compute='_compute_guestlist_stats',
        readonly=True,
    )
    guestlist_checked_in_qty = fields.Integer(
        string='Eingecheckt',
        compute='_compute_guestlist_stats',
        readonly=True,
    )
    guestlist_remaining_qty = fields.Integer(
        string='Verfügbar nach Gästeliste',
        compute='_compute_guestlist_stats',
        readonly=True,
    )
    guestlist_capacity_info = fields.Char(
        string='Kapazitätsstatus',
        compute='_compute_guestlist_stats',
        readonly=True,
    )

    @api.depends('guestlist_access_token')
    def _compute_guestlist_public_url(self):
        for event in self:
            if event.id and event.guestlist_access_token:
                event.guestlist_public_url = '%s/event/guestlist/%s/%s' % (
                    event.get_base_url().rstrip('/'),
                    event.id,
                    event.guestlist_access_token,
                )
            else:
                event.guestlist_public_url = False

    @api.depends('guestlist_public_url')
    def _compute_guestlist_qr_html(self):
        for event in self:
            if not event.guestlist_public_url:
                event.guestlist_qr_html = Markup('<span class="text-muted">QR-Code wird nach dem Speichern erzeugt.</span>')
                continue
            qr_src = '/report/barcode/QR/%s?width=220&height=220&humanreadable=0' % quote(event.guestlist_public_url, safe='')
            event.guestlist_qr_html = Markup(
                '<div class="o_gl_guestlist_qr" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">'
                '<img src="%s" alt="Gästeliste QR-Code" style="width:180px;height:180px;border:1px solid #ddd;border-radius:12px;padding:8px;background:#fff;"/>'
                '<div><strong>QR-Code für den Einlass</strong><br/>'
                '<span class="text-muted">Öffnet die abhakbare Gästeliste für dieses Event.</span><br/>'
                '<small style="word-break:break-all;">%s</small></div>'
                '</div>'
            ) % (escape(qr_src), escape(event.guestlist_public_url))

    @api.depends(
        'guestlist_line_ids.quantity',
        'guestlist_line_ids.checked_in',
        'guestlist_line_ids.active',
        'seats_limited',
        'seats_max',
        'seats_available',
    )
    def _compute_guestlist_stats(self):
        for event in self:
            lines = event.guestlist_line_ids.filtered('active')
            total_qty = sum(lines.mapped('quantity_int'))
            checked_qty = sum(lines.filtered('checked_in').mapped('quantity_int'))
            event.guestlist_total_qty = total_qty
            event.guestlist_checked_in_qty = checked_qty
            if event.seats_limited and event.seats_max:
                remaining = event.seats_available - total_qty
                event.guestlist_remaining_qty = remaining
                event.guestlist_capacity_info = _(
                    '%(remaining)s von %(available)s aktuell verfügbaren Plätzen bleiben nach Gästeliste verfügbar.',
                    remaining=remaining,
                    available=event.seats_available,
                )
            else:
                event.guestlist_remaining_qty = 0
                event.guestlist_capacity_info = _('Diese Veranstaltung hat keine globale Teilnehmerbegrenzung.')

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        events._sync_guestlist_price_options()
        return events

    def write(self, vals):
        res = super().write(vals)
        if 'event_ticket_ids' in vals:
            self._sync_guestlist_price_options()
        capacity_fields = {'seats_max', 'seats_limited'}
        if capacity_fields.intersection(vals):
            self._check_guestlist_capacity()
        return res

    def action_sync_guestlist_price_options(self):
        self.ensure_one()
        self._sync_guestlist_price_options()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Gästeliste'),
                'message': _('Preisoptionen wurden aktualisiert.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_regenerate_guestlist_token(self):
        for event in self:
            event.guestlist_access_token = uuid.uuid4().hex
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Gästeliste'),
                'message': _('Der QR-Link wurde neu erzeugt. Alte Links funktionieren nicht mehr.'),
                'type': 'warning',
                'sticky': False,
            },
        }

    def _guestlist_ticket_option_name(self, ticket):
        self.ensure_one()
        label_parts = []
        if ticket.name:
            label_parts.append(ticket.name)
        product = getattr(ticket, 'product_id', False)
        if product:
            label_parts.append(product.display_name)
        if 'price' in ticket._fields:
            currency = ticket.currency_id if 'currency_id' in ticket._fields else self.company_id.currency_id
            label_parts.append('%s %s' % (ticket.price, currency.name or ''))
        return ' – '.join([part for part in label_parts if part]) or _('Ticket')

    def _sync_guestlist_price_options(self):
        Option = self.env['gl.event.guestlist.price.option'].sudo().with_context(active_test=False)
        for event in self.sudo():
            if not event.id:
                continue

            free_option = Option.search([
                ('event_id', '=', event.id),
                ('is_free', '=', True),
            ], limit=1)
            if free_option:
                free_option.write({
                    'name': _('gratis'),
                    'active': True,
                    'sequence': 0,
                    'ticket_id': False,
                    'product_id': False,
                })
            else:
                Option.create({
                    'name': _('gratis'),
                    'event_id': event.id,
                    'is_free': True,
                    'sequence': 0,
                })

            active_ticket_ids = set(event.event_ticket_ids.ids)
            existing_ticket_options = Option.search([
                ('event_id', '=', event.id),
                ('is_free', '=', False),
            ])

            for ticket in event.event_ticket_ids:
                option = existing_ticket_options.filtered(lambda opt: opt.ticket_id.id == ticket.id)[:1]
                vals = {
                    'name': event._guestlist_ticket_option_name(ticket),
                    'event_id': event.id,
                    'ticket_id': ticket.id,
                    'product_id': ticket.product_id.id if getattr(ticket, 'product_id', False) else False,
                    'is_free': False,
                    'active': True,
                    'sequence': ticket.sequence or 10,
                }
                if option:
                    option.write(vals)
                else:
                    Option.create(vals)

            obsolete_options = existing_ticket_options.filtered(lambda opt: opt.ticket_id.id not in active_ticket_ids)
            obsolete_options.write({'active': False})

    def _check_guestlist_capacity(self):
        for event in self:
            lines = event.guestlist_line_ids.filtered('active')
            guest_qty = sum(lines.mapped('quantity_int'))

            if event.seats_limited and event.seats_max and guest_qty > event.seats_available:
                raise ValidationError(_(
                    'Die Gästeliste für "%(event)s" ist überbucht.\n'
                    'Auf der Gästeliste stehen %(guest_qty)s Personen, aktuell verfügbar sind aber nur %(available)s Plätze.\n'
                    'Bitte reduziere die Gästeliste oder erhöhe die Kapazität.',
                    event=event.display_name,
                    guest_qty=guest_qty,
                    available=event.seats_available,
                ))

            for ticket in event.event_ticket_ids:
                if not ticket.seats_max:
                    continue
                ticket_guest_qty = sum(lines.filtered(lambda line: line.price_option_id.ticket_id == ticket).mapped('quantity_int'))
                if ticket_guest_qty > ticket.seats_available:
                    raise ValidationError(_(
                        'Die Gästeliste überbucht die Ticketart "%(ticket)s".\n'
                        'Für diese Ticketart stehen %(guest_qty)s Gästelistenplätze, aktuell verfügbar sind aber nur %(available)s Plätze.',
                        ticket=ticket.display_name,
                        guest_qty=ticket_guest_qty,
                        available=ticket.seats_available,
                    ))


class EventEventTicket(models.Model):
    _inherit = 'event.event.ticket'

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        tickets.mapped('event_id')._sync_guestlist_price_options()
        return tickets

    def write(self, vals):
        events = self.mapped('event_id')
        res = super().write(vals)
        affected_events = events | self.mapped('event_id')
        affected_events._sync_guestlist_price_options()
        capacity_fields = {'seats_max', 'seats_limited', 'event_id'}
        if capacity_fields.intersection(vals):
            affected_events._check_guestlist_capacity()
        return res

    def unlink(self):
        events = self.mapped('event_id')
        res = super().unlink()
        events._sync_guestlist_price_options()
        return res


class EventRegistration(models.Model):
    _inherit = 'event.registration'

    @api.model_create_multi
    def create(self, vals_list):
        registrations = super().create(vals_list)
        registrations.mapped('event_id')._check_guestlist_capacity()
        return registrations

    def write(self, vals):
        events_before = self.mapped('event_id')
        res = super().write(vals)
        capacity_fields = {'event_id', 'event_ticket_id', 'event_slot_id', 'state', 'active'}
        if capacity_fields.intersection(vals):
            (events_before | self.mapped('event_id'))._check_guestlist_capacity()
        return res


class GuestlistPriceOption(models.Model):
    _name = 'gl.event.guestlist.price.option'
    _description = 'Event-Gästeliste Preisoption'
    _order = 'sequence, name, id'

    name = fields.Char(required=True)
    event_id = fields.Many2one('event.event', string='Veranstaltung', required=True, ondelete='cascade', index=True)
    ticket_id = fields.Many2one('event.event.ticket', string='Ticketart', ondelete='set null', index=True)
    product_id = fields.Many2one('product.product', string='Produkt', ondelete='set null')
    is_free = fields.Boolean(string='Gratis')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    @api.constrains('event_id', 'ticket_id')
    def _check_ticket_belongs_to_event(self):
        for option in self:
            if option.ticket_id and option.ticket_id.event_id != option.event_id:
                raise ValidationError(_('Die Ticketart muss zur Veranstaltung der Preisoption gehören.'))


class GuestlistLine(models.Model):
    _name = 'gl.event.guestlist.line'
    _description = 'Event-Gästelisten-Eintrag'
    _order = 'checked_in, name, id'

    active = fields.Boolean(default=True)
    event_id = fields.Many2one('event.event', string='Veranstaltung', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Vor-/Nachname', required=True)
    quantity = fields.Selection(QUANTITY_SELECTION, string='Anzahl', required=True, default='1')
    quantity_int = fields.Integer(string='Anzahl numerisch', compute='_compute_quantity_int', store=True)
    employee_id = fields.Many2one(
        'hr.employee',
        string='Bearbeiter',
        default=lambda self: self.env.user.employee_id.id if self.env.user.employee_id else False,
    )
    price_option_id = fields.Many2one(
        'gl.event.guestlist.price.option',
        string='Preis',
        domain="[('event_id', '=', event_id), ('active', '=', True)]",
    )
    ordered_by = fields.Selection(ORDERED_BY_SELECTION, string='Bestellt per', default='email', required=True)
    ordered_by_label = fields.Char(string='Bestellt per', compute='_compute_ordered_by_label')
    contact_data = fields.Char(string='Kontaktdaten')
    note = fields.Text(string='Bemerkung')
    checked_in = fields.Boolean(string='Da')
    checked_in_datetime = fields.Datetime(string='Eingecheckt am', readonly=True)
    checked_by_user_id = fields.Many2one('res.users', string='Eingecheckt von', readonly=True)

    @api.depends('ordered_by')
    def _compute_ordered_by_label(self):
        labels = dict(ORDERED_BY_SELECTION)
        for line in self:
            line.ordered_by_label = labels.get(line.ordered_by, '')

    @api.depends('quantity')
    def _compute_quantity_int(self):
        for line in self:
            try:
                line.quantity_int = int(line.quantity or 0)
            except ValueError:
                line.quantity_int = 0

    @api.onchange('event_id')
    def _onchange_event_id(self):
        for line in self:
            if not line.event_id:
                line.price_option_id = False
                continue
            line.event_id._sync_guestlist_price_options()
            free_option = line.event_id.guestlist_price_option_ids.filtered(lambda opt: opt.active and opt.is_free)[:1]
            if free_option and not line.price_option_id:
                line.price_option_id = free_option

    @api.onchange('checked_in')
    def _onchange_checked_in(self):
        for line in self:
            if line.checked_in and not line.checked_in_datetime:
                line.checked_in_datetime = fields.Datetime.now()
            elif not line.checked_in:
                line.checked_in_datetime = False
                line.checked_by_user_id = False

    @api.model_create_multi
    def create(self, vals_list):
        event_ids = {vals.get('event_id') for vals in vals_list if vals.get('event_id')}
        events = self.env['event.event'].browse(event_ids)
        events._sync_guestlist_price_options()

        for vals in vals_list:
            event_id = vals.get('event_id')
            if event_id and not vals.get('price_option_id'):
                free_option = self.env['gl.event.guestlist.price.option'].search([
                    ('event_id', '=', event_id),
                    ('is_free', '=', True),
                    ('active', '=', True),
                ], limit=1)
                if free_option:
                    vals['price_option_id'] = free_option.id
            if vals.get('checked_in') and not vals.get('checked_in_datetime'):
                vals['checked_in_datetime'] = fields.Datetime.now()

        lines = super().create(vals_list)
        lines.mapped('event_id')._check_guestlist_capacity()
        return lines

    def write(self, vals):
        events_before = self.mapped('event_id')
        if vals.get('checked_in') and 'checked_in_datetime' not in vals:
            vals = dict(vals, checked_in_datetime=fields.Datetime.now())
        elif vals.get('checked_in') is False:
            vals = dict(vals, checked_in_datetime=False, checked_by_user_id=False)
        res = super().write(vals)
        capacity_fields = {'event_id', 'quantity', 'price_option_id', 'active'}
        if capacity_fields.intersection(vals):
            (events_before | self.mapped('event_id'))._check_guestlist_capacity()
        return res

    @api.constrains('event_id', 'price_option_id')
    def _check_price_option_belongs_to_event(self):
        for line in self:
            if line.price_option_id and line.price_option_id.event_id != line.event_id:
                raise ValidationError(_('Die Preisoption muss zur Veranstaltung gehören.'))

    @api.constrains('event_id', 'quantity', 'price_option_id', 'active')
    def _check_capacity_constraint(self):
        self.mapped('event_id')._check_guestlist_capacity()
