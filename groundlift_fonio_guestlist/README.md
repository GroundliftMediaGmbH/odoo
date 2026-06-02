# Groundlift Fonio Gästeliste

Odoo 19 SH Modul für die automatische Verarbeitung von Fonio-Kartenreservierungen aus Kundendiensttickets.

## Zweck

Wenn Fonio per E-Mail ein Kundendienstticket im Team **Kartenreservierung** erzeugt, liest das Modul die strukturierte Ticketbeschreibung aus, sucht die passende Veranstaltung und trägt die gewünschte Anzahl Plätze in die bestehende Groundlift-Gästeliste ein.

Beispiel-Fonio-Daten:

```text
action: reservation_request
request_type: event_reservation_request
caller_name: Julius Drescher
caller_phone: 015734442352
title: Martin Kälberer - RAUM hoch 2 am 26. Juni 2026 um 20 Uhr
number_of_seats: 2
```

## Automatik

1. Ticket muss im Kundendienstteam **Kartenreservierung** liegen.
2. `action` muss `reservation_request` sein.
3. `request_type` muss `event_reservation_request` sein.
4. Aus `title` wird die Veranstaltung erkannt. Datums- und Uhrzeit-Zusätze wie `am 26. Juni 2026 um 20 Uhr` werden für die Suche berücksichtigt, stören aber den Namensvergleich nicht.
5. Es wird ein Datensatz in `gl.event.guestlist.line` erzeugt:
   - Veranstaltung: erkannte Veranstaltung
   - Vor-/Nachname: `caller_name`
   - Anzahl: `number_of_seats`
   - Bestellt per: Telefon
   - Kontaktdaten: `caller_phone`
   - Bemerkung: `Fonio`
6. Danach wird das Ticket in die Phase **Gelöst** verschoben.

## Duplikatschutz

Das Modul speichert die Fonio-ID sowohl am Ticket als auch am Gästelisteneintrag. Wenn dasselbe Fonio-Ticket erneut verarbeitet wird, wird kein zweiter Gästelisteneintrag erzeugt.

## Fallback-Cron

Zusätzlich zu `create`/`write` läuft alle 5 Minuten ein Cronjob, der unverarbeitete Fonio-Tickets im Team **Kartenreservierung** nachzieht. Das ist wichtig, falls E-Mail-Inhalt oder Team-Zuordnung erst nachträglich am Ticket gesetzt werden.

## Konfigurationsparameter

Unter Technisch → Systemparameter können diese Werte angepasst werden:

- `groundlift_fonio_guestlist.team_name` = `Kartenreservierung`
- `groundlift_fonio_guestlist.solved_stage_name` = `Gelöst`
- `groundlift_fonio_guestlist.timezone` = `Europe/Berlin`
- `groundlift_fonio_guestlist.event_match_threshold` = `0.62`

## Installation auf Odoo SH

1. Den Ordner `groundlift_fonio_guestlist` in den Addons-Pfad bzw. das Odoo-SH-Repository legen.
2. Sicherstellen, dass das vorhandene Modul `gl_event_guestlist` installiert ist.
3. Commit + Push auf Staging.
4. Apps-Liste aktualisieren.
5. Modul **Groundlift Fonio Gästeliste** installieren.
6. Ein Testticket mit Fonio-Inhalt im Team **Kartenreservierung** erstellen oder eine echte Fonio-Mail abwarten.

## Abhängigkeiten

- `helpdesk`
- `gl_event_guestlist`

Das Modul erstellt bewusst kein eigenes App-Menü und kein Desktop-Icon.
