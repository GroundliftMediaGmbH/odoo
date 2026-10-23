#!/usr/bin/env bash
# Groundlift Odoo 19 SH - read-only diagnostic for missing online payment methods.
# Usage: bash groundlift_payment_methods_diagnose_odoo19.sh --name 'Nachname'
#        bash groundlift_payment_methods_diagnose_odoo19.sh --order AN1001234
#        bash groundlift_payment_methods_diagnose_odoo19.sh --recent 4
set -euo pipefail

GL_SEARCH_NAME=''; GL_SEARCH_EMAIL=''; GL_SEARCH_ORDER=''; GL_RECENT_HOURS='24'
while [[ $# -gt 0 ]]; do
    case "$1" in
        --name|--email|--order|--recent)
            [[ $# -ge 2 ]] || { echo "Fehlender Wert fuer $1" >&2; exit 2; }
            case "$1" in
                --name) GL_SEARCH_NAME="$2" ;;
                --email) GL_SEARCH_EMAIL="$2" ;;
                --order) GL_SEARCH_ORDER="$2" ;;
                --recent) GL_RECENT_HOURS="$2" ;;
            esac
            shift 2 ;;
        -h|--help)
            echo "Aufruf: bash $0 [--name 'Nachname' | --email 'mail@domain.de' | --order AN1001234 | --recent 4]"; exit 0 ;;
        *) echo "Unbekannter Parameter: $1" >&2; exit 2 ;;
    esac
done
[[ "$GL_RECENT_HOURS" =~ ^[0-9]+$ ]] || { echo "--recent muss eine ganze Stundenzahl sein" >&2; exit 2; }
export GL_SEARCH_NAME GL_SEARCH_EMAIL GL_SEARCH_ORDER GL_RECENT_HOURS
command -v odoo-bin >/dev/null || { echo "odoo-bin nicht gefunden. Im normalen Odoo.sh-Linux-Terminal starten, nicht bei 'In [1]:'." >&2; exit 1; }

odoo-bin shell <<'PY'
import os
from datetime import datetime, timedelta
from pprint import pformat

name = os.environ.get('GL_SEARCH_NAME', '').strip()
email = os.environ.get('GL_SEARCH_EMAIL', '').strip()
order_name = os.environ.get('GL_SEARCH_ORDER', '').strip()
recent_hours = int(os.environ.get('GL_RECENT_HOURS', '24'))

Sale = env['sale.order'].sudo()
print('\n' + '='*83)
print('GROUNDLIFT | ZAHLUNGSMETHODEN-DIAGNOSE | NUR LESEND')
print('Filter:', 'Auftrag ' + order_name if order_name else 'Kunde ' + (name or email) if (name or email) else 'letzte %s Stunden (Entwuerfe)' % recent_hours)
print('='*83)

if order_name:
    orders = Sale.search([('name', '=', order_name)], limit=5)
elif name or email:
    domain_p = []
    if name and email:
        domain_p = ['|', ('name', 'ilike', name), ('email', 'ilike', email)]
    elif name:
        domain_p = [('name', 'ilike', name)]
    else:
        domain_p = [('email', 'ilike', email)]
    partners = env['res.partner'].sudo().search(domain_p, limit=100)
    print('Gefundene Kontakte:', len(partners))
    if partners:
        pid = partners.ids
        orders = Sale.search([
            ('website_id', '!=', False),
            '|', '|',
            ('partner_id', 'in', pid),
            ('partner_invoice_id', 'in', pid),
            ('partner_shipping_id', 'in', pid),
        ], order='write_date desc', limit=25)
    else:
        orders = Sale.browse([])
else:
    cutoff = datetime.utcnow() - timedelta(hours=recent_hours)
    orders = Sale.search([
        ('website_id', '!=', False),
        ('state', 'in', ('draft', 'sent')),
        ('write_date', '>=', cutoff),
    ], order='write_date desc', limit=30)

print('Gefundene Website-Auftraege:', len(orders))
if not orders:
    print('Kein zugeordneter Auftrag gefunden. Bei einem anonymen Checkout kann')
    print('der Warenkorb noch am oeffentlichen Website-Kontakt haengen:')
    print('Dann nach Uhrzeit + Betrag/Veranstaltung suchen (--recent 4).')

pub_user = env.ref('base.public_user', raise_if_not_found=False)
if not pub_user:
    print('HINWEIS: base.public_user nicht gefunden. Anzeige im Frontend ggf. abweichend.')

for so in orders:
    print('\n' + '-'*83)
    print('AUFTRAG:', so.name, '| ID:', so.id, '| Status:', so.state)
    print('Erstellt (UTC):', so.create_date, '| Zuletzt (UTC):', so.write_date)
    print('Website:', so.website_id.display_name or '-', '| Firma:', so.company_id.display_name)
    print('Betrag:', so.amount_total, so.currency_id.name, '| Partner ID:', so.partner_id.id)
    print('Kontakt:', so.partner_id.name or '-', '| Mail:', so.partner_id.email or '-')
    print('Land (Auftragspartner):', so.partner_id.country_id.name or 'NICHT GESETZT')
    print('Land (Rechnungspartner):', so.partner_invoice_id.country_id.name or 'NICHT GESETZT')
    print('Kundendaten-RPC Marker:', bool(getattr(so, 'meta_first_name', False)) if 'meta_first_name' in so._fields else 'Feld fehlt')
    print('Positionen:', [(l.name[:65], l.product_uom_qty, l.price_total) for l in so.order_line if not l.display_type][:8])
    txs = so.transaction_ids
    print('Zahlungstransaktionen:', [(t.reference, t.state) for t in txs] if txs else 'keine')

    # Mimic a website visitor rather than an internal Odoo admin; an internal user
    # can see providers that are not published. sudo grants only reading rights.
    pmod = env['payment.provider'].with_user(pub_user).sudo() if pub_user else env['payment.provider'].sudo()
    mmod = env['payment.method'].with_user(pub_user).sudo() if pub_user else env['payment.method'].sudo()
    pmod = pmod.with_company(so.company_id).with_context(website_id=so.website_id.id)
    mmod = mmod.with_company(so.company_id).with_context(website_id=so.website_id.id)

    # Odoo 19 website_sale uses order.partner_id for anonymous users and the
    # logged-in user's partner for portal users, not necessarily invoice partner.
    # We inspect order.partner_id as the best available retrospective proxy.
    partner = so.partner_id
    print('Pruefpartner:', partner.id, '| Firmenzuordnung:', partner.company_id.display_name or 'keine')
    if so.partner_invoice_id != so.partner_id:
        print('ACHTUNG: Rechnungspartner unterscheidet sich; bei angemeldeten Nutzern')
        print('haengt die tatsaechliche Zahlungsmethoden-Auswahl vom Login-Partner ab.')
    provider_report = {}
    method_report = {}
    try:
        providers = pmod._get_compatible_providers(
            so.company_id.id, partner.id, so.amount_total,
            currency_id=so.currency_id.id, website_id=so.website_id.id,
            sale_order_id=so.id, report=provider_report,
        )
        # If the public user could not be set, force the website visibility filter.
        if not pub_user:
            providers = providers.filtered('is_published')
        methods = mmod._get_compatible_payment_methods(
            providers.ids, partner.id, currency_id=so.currency_id.id,
            report=method_report, website_id=so.website_id.id, sale_order_id=so.id,
        )
        print('Frontend-kompatible Anbieter:', [(p.name, p.code) for p in providers] or 'KEINE')
        print('Frontend-kompatible Methoden:', [(m.name, m.code) for m in methods] or 'KEINE')
        print('Provider-Filterreport:', pformat(provider_report, width=120)[:4500])
        print('Methoden-Filterreport:', pformat(method_report, width=120)[:4500])
    except Exception as exc:
        print('FEHLER bei Verfuegbarkeitspruefung:', type(exc).__name__, str(exc)[:1000])
        # Roll back only this shell's transaction after a read-path exception.
        env.cr.rollback()

    all_providers = env['payment.provider'].sudo().search([
        ('company_id', '=', so.company_id.id),
        ('state', 'in', ('enabled', 'test')),
    ])
    print('Anbieterkonfiguration:')
    for p in all_providers:
        print('  %s [%s] state=%s published=%s max=%s country=%s currency=%s methods=%s' % (
            p.name, p.code, p.state, p.is_published, p.maximum_amount,
            ','.join(p.available_country_ids.mapped('code')) or 'alle',
            ','.join(p.available_currency_ids.mapped('name')) or 'alle',
            ','.join(p.payment_method_ids.mapped('name')) or '-',
        ))

print('\nHINWEIS: Dies ist eine Momentaufnahme der AKTUELLEN Provider-Einstellungen.')
print('Falls sich Kundendaten, Warenkorb oder Provider-Konfiguration geaendert haben,')
print('muss das Ergebnis nicht dem Zustand beim urspruenglichen Kaufversuch entsprechen.')
print('Kein Auftrag bedeutet nicht, dass die Kundin die Seite nicht besucht hat.')
print('Es wurden keinerlei Auftraege, Zahlungen oder Provider-Einstellungen geaendert.')
print('='*83)
PY
