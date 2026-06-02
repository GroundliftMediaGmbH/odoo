# Groundlift Fonio Gästeliste 19.0.2.0.0

Dieses Odoo-19-SH-Modul verarbeitet ankommende Fonio-Reservierungswünsche aus Kundendiensttickets im Team **Kartenreservierung** und trägt sie automatisch als **VVK / Fonio** in die bestehende Groundlift-Gästeliste ein.

## Unterstützte Fonio-Beschreibungen

Das Modul verarbeitet z. B. diese Formate:

```text
Neue Fonio-Anfrage / Reservierungswunsch
ID: FONIO-20260602-211804-b0d3
Zeit: 02.06.2026 21:18:04

action: reservation_request
request_type: event_reservation_request
caller_name: Julius Drescher
caller_phone: 0-1-5-7-3-4-4-4-2-3-5-2
title: Z E P - A Tribute to LED Zeppelin
number_of_seats: 2
summary: Reservierung von 2 Karten für das Konzert Z E P - A Tribute to LED Zeppelin am 12. Juni 2026
```

```text
title: Mensch, Otto! - Zu Gast: Tijen Onaran
caller_phone: 0 157344 42352
```

```text
title: Martin Kälberer - RAUM hoch 2 am 26. Juni 2026 um 20 Uhr
```

## Was Version 2 verbessert

- Robuster Parser für Fonio-Felder, auch wenn Formatierung oder Zeilenumbrüche leicht variieren.
- Telefonnummern werden normalisiert, z. B. `0-1-5-7-...` → `0157...`.
- Veranstaltungssuche nutzt:
  - Titelzeile
  - Summary
  - Datum aus Titel oder Summary
  - bereinigten Titel ohne `am 26. Juni 2026 um 20 Uhr`
  - Token-Matching
  - phonetische Treffer, z. B. `Sepp`/`Sep`/`ZEP`
  - automatisch erzeugte Aliasnamen, z. B. `Z E P` → `ZEP`, `A Tribute to LED Zeppelin` → `LED Zeppelin`
- Keine manuelle Alias-Pflege nötig.
- Sichere Verarbeitung: Bei mehrdeutigen Treffern wird **kein falscher Gästelisteneintrag** erzeugt, sondern das Ticket auf Fehler gesetzt.
- Duplikatschutz über Fonio-ID und Ticket-ID.
- VVK-Zuordnung wird über den Systemparameter `groundlift_fonio_guestlist.guestlist_vvk_value` gesteuert.
- Optionaler OpenAI-Fallback, standardmäßig deaktiviert.

## Automatik

1. Ticket muss im Kundendienstteam `Kartenreservierung` liegen.
2. `action` muss `reservation_request` sein.
3. `request_type` muss `event_reservation_request` sein.
4. `caller_name`, `caller_phone`, `title`, `number_of_seats` und `ID` müssen vorhanden sein.
5. Die passende `event.event` wird robust gesucht.
6. Es wird ein Datensatz in `gl.event.guestlist.line` erzeugt:
   - Veranstaltung: erkannte Veranstaltung
   - Name: `caller_name`
   - Anzahl: `number_of_seats`
   - Kontaktdaten: normalisierte Telefonnummer
   - Eintragung: VVK, sofern das Gästelistenmodul ein passendes Auswahlfeld hat
   - Bemerkung: `Fonio / VVK` plus Summary und Fonio-ID
7. Das Ticket wird in die Phase `Gelöst` verschoben.

## Systemparameter

Unter **Einstellungen → Technisch → Systemparameter**:

```text
groundlift_fonio_guestlist.team_name = Kartenreservierung
groundlift_fonio_guestlist.solved_stage_name = Gelöst
groundlift_fonio_guestlist.timezone = Europe/Berlin
groundlift_fonio_guestlist.event_match_threshold = 0.70
groundlift_fonio_guestlist.event_match_ambiguity_delta = 0.08
groundlift_fonio_guestlist.allow_past_event_days = 1
groundlift_fonio_guestlist.max_auto_seats = 200
groundlift_fonio_guestlist.guestlist_vvk_value = VVK
groundlift_fonio_guestlist.guestlist_note = Fonio / VVK
```

Optionaler OpenAI-Fallback:

```text
groundlift_fonio_guestlist.openai_enabled = False
groundlift_fonio_guestlist.openai_api_key = 
groundlift_fonio_guestlist.openai_model = gpt-4.1-mini
groundlift_fonio_guestlist.openai_timeout_seconds = 6
groundlift_fonio_guestlist.openai_min_confidence = 0.78
```

OpenAI bitte erst aktivieren, wenn die lokale Verarbeitung läuft. Der API-Key gehört ausschließlich in die Odoo-Systemparameter, nicht in Git.

## Installation / Update auf Odoo SH

1. Ordner `groundlift_fonio_guestlist` in das Odoo-SH-Repository kopieren.
2. Commit + Push auf Staging.
3. Apps-Liste aktualisieren.
4. Modul **Groundlift Fonio Gästeliste** installieren oder aktualisieren.
5. Ein Testticket im Team `Kartenreservierung` anlegen.
6. Im Ticket prüfen:
   - Fonio-Status
   - erkannte Veranstaltung
   - Match-Score
   - Match-Begründung
   - Gästelisteneintrag

## Wichtiger Hinweis zu VVK

Das Modul versucht, den Wert `VVK` in einem vorhandenen Auswahlfeld des Gästelistenmoduls zu setzen. Standardmäßig wird zuerst `ordered_by` geprüft. Falls euer Gästelistenmodul einen anderen Feldnamen oder einen anderen Selection-Key nutzt, kann der Systemparameter `groundlift_fonio_guestlist.guestlist_vvk_value` angepasst werden.

Falls `VVK` als Auswahlwert im Gästelistenmodul noch nicht existiert, muss dieser dort vorhanden sein oder die Gästeliste muss einen Default-Wert haben.
