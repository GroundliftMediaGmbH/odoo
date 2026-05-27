# Groundlift Event Gästeliste (Odoo 19 SH)

Dieses Modul erweitert die Veranstaltungsapp um einen Tab **Gästeliste**.

## Funktionen

- Tab „Gästeliste“ auf der Veranstaltungsform
- Gästelisten-Spalten:
  - Vor-/Nachname
  - Anzahl als Dropdown 1–20
  - Bearbeiter als Mitarbeiter-Dropdown
  - Preis als Veranstaltungspreisoption: `gratis` plus Ticket-/Produktoptionen der Veranstaltung
  - Bestellt per: E-Mail, Telefon, Persönlich
  - Kontaktdaten
  - Bemerkung
- Summierung der Gästelistenpersonen
- Kapazitätsprüfung gegen verfügbare Eventplätze und begrenzte Ticketarten
- Token-geschützter QR-Link je Veranstaltung
- Öffentliche Check-in-Seite mit Suche und abhakbarer Gästeliste
- Kein eigenes App-Menü und kein App-Icon

## Installation auf Odoo SH

1. Modulordner `gl_event_guestlist` in dein Custom-Addons-Repository kopieren.
2. Committen und auf den gewünschten Odoo-SH-Branch pushen.
3. In Odoo Apps-Liste aktualisieren.
4. Modul **Groundlift Event Gästeliste** installieren.
5. Veranstaltung öffnen und den neuen Tab **Gästeliste** verwenden.

## Hinweise

- Der QR-Link ist token-geschützt. Jede Person mit Link/QR kann die Gästeliste sehen und abhaken.
- Mit dem Button **QR-Link neu erzeugen** wird der alte Link ungültig.
- Preisoptionen werden automatisch aus den Ticketarten der Veranstaltung synchronisiert; der Button **Preisoptionen aktualisieren** ist als manuelle Sicherheitsfunktion enthalten.
