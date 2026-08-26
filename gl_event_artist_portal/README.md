# Groundlift Künstler- & Agenturportal – Odoo 19 SH

## Zweck

Dieses Modul erweitert `gl_event_guestlist` um eine token-geschützte Website für Künstler und Agenturen.

Das Portal ist ausschließlich erreichbar, solange die Veranstaltung in der Odoo-Phase **„Angekündigt“** steht.

## Funktionen

- pro Veranstaltung eigener geheimer Portal-Link + QR-Code im Reiter **Gästeliste**
- Link ist nur in Phase **Angekündigt** aktiv
- Künstler/Agenturen können ohne Odoo-Login eintragen:
  - **Gästeliste** → kostenlose Preisoption der vorhandenen Gästelisten-App
  - **Ticket · Abendkasse** → echte Ticketkategorie der Veranstaltung; Zahlung erfolgt erst vor Ort
- Einträge landen direkt als `gl.event.guestlist.line` in der vorhandenen Gästelisten-App
- vorhandene Kapazitäts-, Ticketlimit- und Ausverkauftlogik bleibt damit maßgeblich
- Live-Übersicht im Portal:
  - verkaufte Tickets je Kategorie
  - insgesamt verkaufte Tickets
  - reservierte Plätze je Kategorie
  - verbleibende Plätze je Kategorie
  - insgesamt verbleibende Plätze
- Portal zeigt die bereits über den Künstlerlink erfassten Einträge
- Backend-Kennzeichnung, ob ein Eintrag über das Künstlerportal kam und ob es sich um Gästeliste oder Abendkasse handelt
- Portal-Link kann im Backend neu erzeugt und der alte Link dadurch sofort ungültig gemacht werden

## Installation

1. Voraussetzung: `gl_event_guestlist` ist installiert.
2. Ordner `gl_event_artist_portal` in das Odoo-SH-Repository/Addons-Verzeichnis legen.
3. Commit + Push.
4. Apps-Liste aktualisieren.
5. Modul **Groundlift Künstler- & Agenturportal** installieren.

## Bedienung

1. Veranstaltung öffnen.
2. Reiter **Gästeliste** öffnen.
3. Im Block **Künstler- / Agenturportal** steht der Link samt QR-Code bereit, sobald die Phase **Angekündigt** ist.
4. Link an Künstler/Agentur senden.
5. Nach einem Phasenwechsel weg von **Angekündigt** bleibt der Token gespeichert, die Seite ist aber gesperrt.

## Technische Zähllogik

- **Verkauft**: native Odoo-Ticketzahl `event.event.ticket.seats_taken` der echten Ticketarten; die technische Gästelisten-Summenzeile wird ausgeschlossen.
- **Reserviert**: verbindliche Zeilen der vorhandenen Gästelisten-App, die einer Ticketart zugeordnet sind.
- **Verfügbar**: native Odoo-Verfügbarkeit abzüglich verbindlicher Gästelistenplätze; ein globales Veranstaltungslimit wird zusätzlich berücksichtigt.
