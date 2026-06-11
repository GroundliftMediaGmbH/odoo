# Groundlift Event Ticket Revenue Sync

Synchronisiert den Brutto-Ticketumsatz eines Events in ein vorhandenes Studio-Feld.

## Mapping

Quelle:

```text
event.event.sale_price_total
```

Zielfeld:

```text
event.event.x_studio_event_kalk_ist_ticketumsatz_max_brutto
```

## Wichtig

Das Modul liest `sale_price_total` nicht nur stumpf aus dem Cache, sondern berechnet den Wert robust nach der Odoo-Standardlogik aus bestätigten `sale.order.line`-Zeilen:

- `event_id` ist gesetzt
- `state = sale`
- `price_total != 0`
- Gruppierung nach Event und Währung
- Umrechnung in die Event-Währung

Dadurch entspricht der Wert der Logik von Odoos `sale_price_total`, ist aber bei direkten Aktualisierungen zuverlässiger.

## Aktualisierung erfolgt bei

- Verkaufsauftrag bestätigen
- Verkaufsauftrag stornieren
- Verkaufsauftrag zurück auf Entwurf
- Verkaufsauftragsposition erstellen, ändern oder löschen
- relevanten Preis-/Mengen-/Steueränderungen
- stündlichem Sicherheits-Cron
- einmalig direkt nach Installation

## Voraussetzung

Das Zielfeld muss bereits auf `event.event` existieren:

```text
x_studio_event_kalk_ist_ticketumsatz_max_brutto
```

Es sollte ein Decimal/Float- oder Monetary-Feld sein.
