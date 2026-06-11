# Groundlift Event Ticket Revenue Sync

Kleines Odoo-19-Modul für Odoo.sh.

## Zweck

Das Modul synchronisiert den von Odoo berechneten Brutto-Ticketumsatz eines Events aus:

```text
sale_price_total
```

in das Groundlift-Studio-Feld:

```text
x_studio_event_kalk_ist_ticketumsatz_max_brutto
```

Odoos Feld `sale_price_total` kommt aus `event_sale` und entspricht dem steuerinkludierten Verkaufswert bestätigter Verkaufsauftragspositionen, die mit dem Event verknüpft sind.

## Aktualisierung erfolgt bei

- Erstellung von Verkaufsauftragspositionen
- Änderung relevanter Verkaufsauftragspositionen
- Löschen von Verkaufsauftragspositionen
- Bestätigung eines Verkaufsauftrags
- Storno eines Verkaufsauftrags
- Zurücksetzen auf Entwurf
- relevanten Änderungen am Verkaufsauftrag
- täglich zusätzlich per Sicherheits-Cron
- einmalig direkt nach Modulinstallation für bestehende Events

## Voraussetzung

Das Studio-Feld muss auf `event.event` existieren:

```text
x_studio_event_kalk_ist_ticketumsatz_max_brutto
```

Empfohlen: Feldtyp `Monetary` oder `Float`.

## Installation in Odoo.sh

1. Ordner `gl_event_ticket_revenue_sync` in euer Custom-Addons-Repository kopieren.
2. In Odoo.sh committen und deployen.
3. App-Liste aktualisieren.
4. Modul `Groundlift Event Ticket Revenue Sync` installieren.
5. Bestehende Events werden beim Installieren einmalig synchronisiert.

## Hinweis

Das Modul legt kein neues Feld an, sondern schreibt bewusst in das bestehende Studio-Feld. Wenn das Feld fehlt, wird nichts geschrieben und ein Hinweis im Log erzeugt.
