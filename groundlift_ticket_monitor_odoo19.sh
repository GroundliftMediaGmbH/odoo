#!/usr/bin/env bash
# GROUNDLIFT Odoo.sh / Odoo 19 - lesender Ticketkauf-Monitor
# Aufruf: bash groundlift_ticket_monitor_odoo19.sh [--hours 24] [--since '2026-10-22 15:00'] [--order AN1001332]
# Aendert KEINE Bestellungen, Zahlungen, Registrierungen oder E-Mails.
set -euo pipefail

GL_CHECK_HOURS=24
GL_CHECK_SINCE=""
GL_CHECK_ORDER=""

usage() {
  cat <<'EOF'
GROUNDLIFT Ticket-Monitor fuer Odoo.sh 19 (nur lesend)

Aufruf:
  bash groundlift_ticket_monitor_odoo19.sh
  bash groundlift_ticket_monitor_odoo19.sh --hours 2
  bash groundlift_ticket_monitor_odoo19.sh --since '2026-10-22 15:00'
  bash groundlift_ticket_monitor_odoo19.sh --order AN1001332

  --hours N   letzte N Stunden (Standard 24)
  --since X   ab Berliner Ortszeit, Format 'JJJJ-MM-TT HH:MM'
  --order X   nur einen bestimmten Website-Auftrag untersuchen
  --help      Hilfe anzeigen

Das Skript muss in der normalen Odoo.sh-Linux-Shell laufen,
NICHT innerhalb von psql (=>) oder der Python-Shell (In [1]:).
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --hours)
      [ "$#" -ge 2 ] || { echo "Fehlt Wert fuer --hours" >&2; exit 1; }
      GL_CHECK_HOURS="$2"; shift 2 ;;
    --since)
      [ "$#" -ge 2 ] || { echo "Fehlt Wert fuer --since" >&2; exit 1; }
      GL_CHECK_SINCE="$2"; shift 2 ;;
    --order)
      [ "$#" -ge 2 ] || { echo "Fehlt Wert fuer --order" >&2; exit 1; }
      GL_CHECK_ORDER="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unbekannte Option: $1" >&2; usage; exit 1 ;;
  esac
done

if ! [[ "$GL_CHECK_HOURS" =~ ^[0-9]+$ ]] || [ "$GL_CHECK_HOURS" -lt 1 ]; then
  echo "--hours muss eine positive ganze Zahl sein" >&2; exit 1
fi
if [ -n "$GL_CHECK_ORDER" ] && ! [[ "$GL_CHECK_ORDER" =~ ^AN[0-9]+([\-][0-9]+)?$ ]]; then
  echo "--order erwartet z. B. AN1001332" >&2; exit 1
fi
if ! command -v odoo-bin >/dev/null 2>&1; then
  echo "odoo-bin nicht gefunden. Bitte die Shell des Odoo.sh-Branches oeffnen." >&2; exit 1
fi

export GL_CHECK_HOURS GL_CHECK_SINCE GL_CHECK_ORDER

# Odoo 19 fuehrt bei umgeleiteter Standardeingabe den Python-Code im
# geladenen Odoo-ORM-Kontext 'env' aus und beendet die Shell danach.
odoo-bin shell <<'PY'
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Berlin')
now_utc = datetime.now(timezone.utc)
now_naive = now_utc.replace(tzinfo=None)
order_name = os.environ.get('GL_CHECK_ORDER', '').strip()
since_text = os.environ.get('GL_CHECK_SINCE', '').strip()
hours = int(os.environ.get('GL_CHECK_HOURS', '24'))

if since_text:
    try:
        local_from = datetime.strptime(since_text, '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
    except ValueError:
        raise SystemExit("FEHLER: --since bitte als 'JJJJ-MM-TT HH:MM' in Berliner Zeit angeben")
    since_utc = local_from.astimezone(timezone.utc).replace(tzinfo=None)
else:
    since_utc = (now_utc - timedelta(hours=hours)).replace(tzinfo=None)


def fmt_berlin(dt):
    if not dt:
        return '-'
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ).strftime('%d.%m.%Y %H:%M:%S')


def currency(amount, symbol='EUR'):
    return f'{amount:.2f} {symbol}'


def age_minutes(when):
    if not when:
        return 999999
    dt = when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when
    return max(0, (now_utc - dt).total_seconds() / 60)


print('\n' + '=' * 86)
print('GROUNDLIFT  |  TICKETKAUF-KONTROLLE  |  Odoo 19 SH  |  NUR LESEN')
print('=' * 86)
print('Datenbank:', env.cr.dbname)
print('Abfragezeit:', fmt_berlin(now_naive), '(Europe/Berlin)')
print('Auftrag:', order_name if order_name else 'Alle Website-Ticketauftraege')
if not order_name:
    print('Zeitraum ab:', fmt_berlin(since_utc))
print('Statushinweis: Die Odoo-Zahlung done beweist nicht die Bankauszahlung oder Zustellung.')
print('-' * 86)

# Website-Ticketverkaeufe, nach Auftrags- und Erstellzeit gefiltert.
domain = [
    ('website_id', '!=', False),
    ('order_line.event_ticket_id', '!=', False),
]
if order_name:
    domain.append(('name', '=', order_name))
else:
    domain.extend(['|', ('date_order', '>=', since_utc), ('create_date', '>=', since_utc)])

Sale = env['sale.order'].sudo()
max_orders = 300
orders = Sale.search(domain, order='date_order desc', limit=max_orders + 1)
if len(orders) > max_orders:
    print(f'HINWEIS: Nur die neuesten {max_orders} Auftraege im Ergebnis. Zeitraum verkuerzen!')
    orders = orders[:max_orders]

stats = Counter()

for so in orders:
    ticket_lines = so.order_line.filtered(lambda ln: bool(ln.event_ticket_id) and ln.service_tracking == 'event' and not ln.display_type)
    if not ticket_lines:
        continue
    all_txs = so.transaction_ids
    # Abgebrochene Warenkoerbe ohne Zahlungsversuch nicht als Kauf melden.
    if not all_txs and so.state not in ('sale', 'done'):
        continue
    stats['insgesamt'] += 1

    done_txs = all_txs.filtered(lambda tx: tx.state == 'done')
    matching_done_txs = done_txs.filtered(lambda tx: not tx.currency_id or tx.currency_id == so.currency_id)
    done_amount = sum(matching_done_txs.mapped('amount'))
    total_amount = float(so.amount_total)
    rounding = float(so.currency_id.rounding or 0.01)
    is_free = total_amount <= rounding / 2
    payment_ok = (is_free and so.state in ('sale', 'done')) or (
        bool(matching_done_txs) and done_amount + rounding >= total_amount
    )
    double_paid = bool(matching_done_txs) and done_amount > total_amount + rounding and not is_free
    booked = so.state in ('sale', 'done')
    complete_age = age_minutes(max([tx.write_date for tx in matching_done_txs] or [so.date_order or so.create_date]))
    grace = complete_age < 3.0  # Odoo-Zahlung/Bestellbestaetigung kann Sekunden benoetigen
    email_grace = complete_age < 30.0  # Mail-Cron laeuft eventuell deutlich spaeter

    issues = []
    pending = []
    lines_info = []
    registered_count = 0
    expected_count = 0
    mail_progress = Counter()

    if not payment_ok:
        if done_txs and len(matching_done_txs) != len(done_txs):
            issues.append('Eine erfolgreiche Transaktion hat eine abweichende Waehrung')
        elif done_txs:
            issues.append('Erfolgreiche Zahlung(en) decken den Auftragsbetrag nicht')
        else:
            pending.append('Keine vollstaendige Zahlung mit Status done gefunden')
    else:
        stats['bezahlt'] += 1
        if not booked:
            (pending if grace else issues).append('Zahlung done, aber Verkaufsauftrag noch nicht sale')
    if double_paid:
        issues.append('Mehrere done-Zahlungen / moegliche Ueberzahlung pruefen')

    for ln in ticket_lines:
        qty = float(ln.product_uom_qty)
        qty_int = int(round(qty))
        regs = ln.registration_ids
        expected_count += max(qty_int, 0)
        registered_count += len(regs.filtered(lambda reg: reg.state in ('open', 'done')))
        if abs(qty - qty_int) > 0.001:
            issues.append(f'Ticketposition {ln.id}: Menge {qty:g} ist nicht ganzzahlig')
        if len(regs) != qty_int:
            (pending if payment_ok and grace else issues).append(
                f'Ticketposition {ln.id}: {len(regs)} Registrierungen statt {qty_int}'
            )

        # Gibt es fuer dieses Event ueberhaupt eine Mail nach Registrierung?
        event_schedulers = ln.event_id.event_mail_ids.filtered(lambda s: s.interval_type == 'after_sub')
        expects_auto_mail = bool(event_schedulers)

        for reg in regs:
            if payment_ok and reg.state not in ('open', 'done'):
                (pending if grace else issues).append(
                    f'Registrierung {reg.id}: {reg.state} statt open / done'
                )
            if payment_ok and reg.sale_status != 'sold':
                (pending if grace else issues).append(
                    f'Registrierung {reg.id}: Verkaufsstatus {reg.sale_status!r} statt sold'
                )

            relevant_plans = reg.mail_registration_ids.filtered(
                lambda p: p.scheduler_id.interval_type == 'after_sub'
            )
            if not expects_auto_mail:
                mail_progress['nicht_konfiguriert'] += 1
            elif not relevant_plans:
                mail_progress['fehlt'] += 1
                if payment_ok:
                    (pending if email_grace else issues).append(
                        f'Registrierung {reg.id}: keine Anmeldebestaetigungs-Mailplanung'
                    )
            elif any(p.mail_sent for p in relevant_plans):
                mail_progress['angestossen'] += 1
            else:
                mail_progress['wartet'] += 1
                if payment_ok:
                    # Die Event-Kommunikation kann asynchron/zeitversetzt ausgefuehrt werden.
                    pending.append(f'Registrierung {reg.id}: Event-Mail geplant, noch nicht verarbeitet')

            # Nur eindeutige technische SMTP-/Queue-Fehler auslesen.
            # mail.mail kann nach Versand geloescht werden; Abwesenheit ist KEIN Fehler.
            if payment_ok:
                msg_ids = env['mail.message'].sudo().search([
                    ('model', '=', 'event.registration'), ('res_id', '=', reg.id),
                ], limit=30).ids
                if msg_ids:
                    exceptions = env['mail.mail'].sudo().search([
                        ('mail_message_id', 'in', msg_ids), ('state', '=', 'exception')
                    ], limit=5)
                    for mail in exceptions:
                        reason = (mail.failure_reason or 'unbekannt').replace('\n', ' ')[:150]
                        issues.append(f'Registrierung {reg.id}: E-Mail-Versandfehler: {reason}')

        event_label = (ln.event_id.name or '-')[:55]
        lines_info.append(f'  Event: {event_label} | Position {ln.id} | Soll {qty_int}, Ist {len(regs)}')
        for reg in regs:
            relevant_plans = reg.mail_registration_ids.filtered(lambda p: p.scheduler_id.interval_type == 'after_sub')
            if not expects_auto_mail:
                email_stage = 'nicht konfiguriert'
            elif not relevant_plans:
                email_stage = 'KEINE MAILPLANUNG'
            elif any(p.mail_sent for p in relevant_plans):
                email_stage = 'angestossen (KEIN Zustellnachweis)'
            else:
                email_stage = 'geplant/offen'
            lines_info.append(
                f'    Ticket-ID {reg.id}: state={reg.state}, sale_status={reg.sale_status}, Mail={email_stage}'
            )

    if issues:
        overall = 'FEHLER'
        stats['fehler'] += 1
    elif not payment_ok:
        overall = 'OFFEN'
        stats['offen'] += 1
    elif pending or mail_progress['nicht_konfiguriert']:
        overall = 'PRUEFEN'
        stats['pruefen'] += 1
    else:
        overall = 'OK'
        stats['ok'] += 1

    symbol = (so.currency_id.name or 'EUR')
    print(f'\n[{overall}] {so.name} | Auftrag={so.state} | {currency(total_amount, symbol)}'
          f' | done={currency(done_amount, symbol)} | {fmt_berlin(so.date_order)}')
    tx_summary = ', '.join(f'{tx.reference}:{tx.state}({tx.amount:.2f})' for tx in all_txs)
    print('  Zahlungs-Transaktionen:', tx_summary or 'keine')
    print(f'  Tickets gebucht: {registered_count}/{expected_count}'
          f' | Mailprozess angestossen: {mail_progress["angestossen"]}'
          f' | offen: {mail_progress["wartet"]}'
          f' | ohne Plan: {mail_progress["fehlt"]}')
    print('  Checkout-Kundendatenmarker:', bool(so.meta_first_name) if 'meta_first_name' in so._fields else 'n/v')
    for line in lines_info:
        print(line)
    for issue in dict.fromkeys(issues):
        print('  !!', issue)
    for item in dict.fromkeys(pending):
        print('  ..', item)
    if mail_progress['nicht_konfiguriert']:
        print('  .. Kein Event-Mail-Trigger nach Anmeldung fuer mindestens eine Position konfiguriert')

print('\n' + '=' * 86)
print('ZUSAMMENFASSUNG')
print('Website-Ticketauftraege:', stats['insgesamt'])
print('Davon voll bezahlt / kostenlos bestaetigt:', stats['bezahlt'])
print('OK (Zahlung, Registrierung, Mailverarbeitung angestossen):', stats['ok'])
print('PRUEFEN (frisch, Mail noch offen oder Konfiguration):', stats['pruefen'])
print('FEHLER (inkonsistent, nach Frist oder SMTP-Fehler):', stats['fehler'])
print('OFFEN (noch keine vollstaendige done-Zahlung):', stats['offen'])
if not stats['insgesamt']:
    print('Keine passenden Website-Ticketauftraege gefunden (Zeitraum ggf. erweitern).')
print('\nWICHTIG: mail_sent = True bedeutet Verarbeitung angestossen, nicht zugestellt.')
print('Ein SMTP-Erfolg garantiert keine Zustellung im Kundenpostfach.')
print('Das Skript veraendert weder Buchungen noch Zahlungen oder E-Mails.')
print('=' * 86 + '\n')
PY
