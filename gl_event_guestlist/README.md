# Groundlift Event Gästeliste

Odoo 19 SH Modul für Gästelisten in der Veranstaltungsapp.

## Funktionen

- neuer Tab **Gästeliste** auf `event.event`
- Gästelistenzeilen mit:
  - Vor-/Nachname
  - Anzahl 1 bis 20
  - Bearbeiter
  - Kategorie / Preis: `gratis`, `Warteliste` plus Ticket-/Produktoptionen der Veranstaltung
  - Bestellt per: E-Mail, Telefon, Persönlich
  - Kontaktdaten
  - Bemerkung
- Kapazitätsprüfung gegen globale Event-Kapazität und begrenzte Ticketarten
- automatische Kennzeichnung des Veranstaltungsnamens mit **(Ausverkauft)**, sobald verkaufte/registrierte Plätze plus verbindliche Gästelistenplätze die Registrierungsbeschränkung erreichen
- automatische Schließung der Website-Registrierung, damit auf der Landingpage kein Ticketkauf-Link mehr angezeigt wird
- neue Gästelisten-Kategorie **Warteliste**; diese wird nicht auf Kapazität, Ausverkauft-Status oder Ticketart-Kontingente angerechnet
- QR-Code und token-geschützte öffentliche Check-in-Seite
- abhakbare Einlassliste mit Suchfunktion und Live-Zähler
- technische Summenzeile **Gästeliste** im Tickets-Tab:
  - kein Produkt
  - kein Maximum (`seats_max = 0`, Odoo-Logik: unbegrenzt)
  - Spalte `Registration` zeigt die Summe der verbindlichen Gästelistenplätze ohne Warteliste
  - nicht verkaufbar (`sale_available = False`) und nicht für Preisoptionen auswählbar
- kein eigenes App-Menü und kein Desktop-Icon (`application = False`)

## Installation / Update auf Odoo SH

1. ZIP entpacken.
2. Ordner `gl_event_guestlist` in den Addons-Pfad bzw. das Odoo-SH-Repository legen.
3. Commit + Push auf Staging.
4. Apps-Liste aktualisieren.
5. Modul **Groundlift Event Gästeliste** installieren oder aktualisieren.

Beim Modul-Update wird automatisch für bestehende Veranstaltungen die Summenzeile **Gästeliste** im Tickets-Tab erzeugt.

## Hinweise

Die öffentliche Check-in-Seite ist nicht loginpflichtig, aber über einen Veranstaltungstoken geschützt. Wer den Link oder QR-Code besitzt, kann die Gästeliste sehen und Check-ins setzen.
