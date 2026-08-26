# Groundlift Künstler- & Agenturportal – Odoo 19 SH

## Zweck

Dieses Modul erweitert `gl_event_guestlist` um eine token-geschützte Website für Künstler und Agenturen.

Das Portal ist ausschließlich erreichbar, solange die Veranstaltung in der Odoo-Phase **„Angekündigt“** steht.

## Funktionen

- pro Veranstaltung eigener geheimer Portal-Link + QR-Code im Reiter **Info für Band/Agentur**
- Link ist nur in Phase **Angekündigt** aktiv
- Künstler/Agenturen können ohne Odoo-Login eintragen:
  - **Gästeliste** → kostenlose Preisoption der vorhandenen Gästelisten-App
  - **Ticket · Abendkasse** → echte Ticketkategorie der Veranstaltung; Zahlung erfolgt erst vor Ort
- Künstler/Agenturen können ihre über dieses Portal angelegten Einträge nachträglich **ändern**
  - Name
  - Anzahl
  - Gästeliste / Abendkasse
  - Ticketkategorie
  - Kontaktdaten
  - Ansprechpartner
  - Bemerkung
- Künstler/Agenturen können ihre Einträge **stornieren**; die reservierte Kapazität wird sofort wieder freigegeben
- stornierte Datensätze werden intern archiviert statt gelöscht, damit ein Audit-Trail erhalten bleibt
- Einträge landen direkt als `gl.event.guestlist.line` in der vorhandenen Gästelisten-App
- vorhandene Kapazitäts-, Ticketlimit- und Ausverkauftlogik bleibt damit maßgeblich
- Live-Übersicht im Portal:
  - verkaufte Tickets je Kategorie
  - insgesamt verkaufte Tickets
  - reservierte Plätze je Kategorie
  - verbleibende Plätze je Kategorie
  - insgesamt verbleibende Plätze
- Portal zeigt die bereits über den Künstlerlink erfassten aktiven Einträge
- Backend-Kennzeichnung, ob ein Eintrag über das Künstlerportal kam und ob es sich um Gästeliste oder Abendkasse handelt
- Portal-Link kann im Backend neu erzeugt und der alte Link dadurch sofort ungültig gemacht werden

## Sicherheit

- Ändern/Stornieren ist nur mit dem gültigen Event-Token möglich.
- Zusätzlich wird serverseitig geprüft, dass der zu ändernde Datensatz wirklich zu derselben Veranstaltung gehört und über das Künstlerportal angelegt wurde.
- Kapazitätsänderungen laufen in einem Datenbank-Savepoint. Wird eine Änderung wegen Überbuchung abgelehnt, bleibt der ursprüngliche Eintrag unverändert.

## Installation

1. Voraussetzung: `gl_event_guestlist` ist installiert.
2. Ordner `gl_event_artist_portal` in das Odoo-SH-Repository/Addons-Verzeichnis legen.
3. Commit + Push.
4. Apps-Liste aktualisieren.
5. Modul **Groundlift Künstler- & Agenturportal** installieren bzw. upgraden.

## Bedienung

1. Veranstaltung öffnen.
2. Reiter **Info für Band/Agentur** öffnen.
3. Dort steht der Link samt QR-Code bereit, sobald die Phase **Angekündigt** ist.
4. Link an Künstler/Agentur senden.
5. Im öffentlichen Portal stehen bei jedem eigenen Eintrag die Aktionen **Ändern** und **Stornieren** zur Verfügung.
6. Nach einem Phasenwechsel weg von **Angekündigt** bleibt der Token gespeichert, die Seite ist aber gesperrt.

## Technische Zähllogik

- **Verkauft**: native Odoo-Ticketzahl `event.event.ticket.seats_taken` der echten Ticketarten; die technische Gästelisten-Summenzeile wird ausgeschlossen.
- **Reserviert**: verbindliche Zeilen der vorhandenen Gästelisten-App, die einer Ticketart zugeordnet sind.
- **Verfügbar**: native Odoo-Verfügbarkeit abzüglich verbindlicher Gästelistenplätze; ein globales Veranstaltungslimit wird zusätzlich berücksichtigt.

## Änderungen

### 19.0.1.0.3

- Künstler/Agenturen können Portal-Einträge ändern oder stornieren.
- Stornierungen archivieren den Eintrag und geben die Kapazität sofort frei.
- Portal-Link/QR-Code wurden aus **Gästeliste** in den neuen Reiter **Info für Band/Agentur** verschoben.
- Zusätzliche serverseitige Prüfung der Event-Zugehörigkeit bei Änderung/Stornierung.
- Savepoints schützen Create/Update vor Teiländerungen bei Kapazitätsfehlern.

### 19.0.1.0.2

- Ticketpreise werden im Künstlerportal mit der Odoo-Währungsformatierung angezeigt.
- Dropdown-Optionen sind im Darkmode lesbar.

### 19.0.1.0.1

- Odoo-19-QWeb-Fix: `t-field` für das Veranstaltungsdatum liegt nun auf einem echten `<span>`-Element statt auf `<t>`. Dadurch wird der Künstler-/Agentur-Link ohne QWeb-AssertionError gerendert.
