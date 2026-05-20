# Groundlift Kino Dienstplan Anmeldung

Custom Odoo 19 SH Modul für die monatliche Abfrage der Filmvorführer:innen.

## Funktionsumfang

- erzeugt pro Zielmonat automatisch die regulären Kinotage wahlweise von Donnerstag bis Sonntag oder von Dienstag bis Sonntag
- erlaubt manuelle Zusatztermine, z. B. private Vermietungen, mit sichtbarer Notiz für Filmvorführer:innen
- findet Empfänger:innen über HR-Mitarbeiter:
  - Abteilung enthält `Kino`
  - Stelle/Stellenbezeichnung enthält `Filmvor`
  - Arbeits-E-Mail ist gepflegt
- versendet in der ersten Woche des Monats eine Anfrage für den Folgemonat
- versendet nach 7 Tagen genau eine Erinnerung, sofern noch Slots offen sind
- stellt eine öffentliche, aber tokenisierte Status-/Eintrageseite bereit
- persönliche Links erlauben die Eintragung in offene Kinotage
- verhindert Überschreiben bereits belegter Slots
- benachrichtigt nach jeder Eintragung die zuständige E-Mail-Adresse mit Füllstand und offenen Tagen

## Installation auf Odoo SH

1. Ordner `groundlift_kino_shift_signup` in das Custom-Addons-Verzeichnis des Odoo-SH-Repositories kopieren.
2. Commit und Push in den gewünschten Branch.
3. In Odoo Apps-Liste aktualisieren.
4. App `Groundlift Kino Dienstplan Anmeldung` installieren.
5. Prüfen, dass die Abteilung `Kino` existiert und der/die Vorgesetzte dort gesetzt ist.
6. Prüfen, dass Filmvorführer:innen als Mitarbeiter mit Arbeits-E-Mail gepflegt sind und Stelle/Stellenbezeichnung `Filmvorführer:in` oder zumindest `Filmvor...` enthält.

## Nutzung

- Menü: `Kino Dienstplan` → `Dienstpläne`
- Manuell testen:
  1. Neuen Dienstplan mit Monat anlegen, z. B. `01.06.2026`.
  2. Unter `Reguläre Spieltage` auswählen, ob der Monat von `Donnerstag bis Sonntag` oder von `Dienstag bis Sonntag` gespielt wird.
  3. `Kinotage erzeugen` klicken.
  4. Optional im Reiter `Kinotage` manuelle Zusatztermine ergänzen und im Feld `Notiz für Filmvorführer:innen` z. B. `Private Vermietung 11:00–18:00` eintragen.
  5. `Anfrage senden` klicken.
- Automatik:
  - Cron `Kino Dienstplan: Monatsanfrage versenden` läuft täglich und sendet nur vom 1. bis 7. eines Monats für den Folgemonat.
  - Cron `Kino Dienstplan: Erinnerung offene Slots` läuft täglich und sendet nach 7 Tagen eine Erinnerung, falls noch Slots offen sind.

## Wichtige Hinweise

- Antworten wie „Ich kann am 16.“ werden nicht automatisch aus Freitext-Mails geparst. Das ist bewusst nicht enthalten, weil Freitext-Antworten fehleranfällig sind. Der sichere Workflow ist der persönliche Eintragelink.
- Die Statusseite ist nicht indexierbar (`sitemap=False`, `robots noindex`) und über Token geschützt, aber ohne Login erreichbar. Das ist absichtlich so, damit Filmvorführer:innen keinen Odoo-Login benötigen.
- Für eine spätere tiefe Integration in Odoo Planning kann bei erfolgreicher Eintragung zusätzlich ein `planning.slot` erzeugt werden.

## Änderungen in Version 19.0.1.1.0

- Neues Feld `Reguläre Spieltage` auf dem Dienstplan: `Donnerstag bis Sonntag` oder `Dienstag bis Sonntag`.
- `Kinotage erzeugen` legt je nach Auswahl die passenden Tage an und löscht keine bereits vorhandenen oder manuell ergänzten Tage.
- Im Reiter `Kinotage` können Zusatztermine manuell angelegt werden. Neue manuelle Zeilen werden als `Manuell` vorbelegt.
- Jeder Kinotag hat ein Feld `Notiz für Filmvorführer:innen`; die Notiz erscheint auf der öffentlichen Eintrageseite und in den E-Mail-Listen der offenen Tage.

## Update-Hinweis für diese Version

Nach Commit/Push auf Odoo SH reicht ein Neustart bzw. neuer Build nicht aus, damit neue Felder und XML-Views sichtbar werden. Bitte danach in Odoo:

1. Apps öffnen.
2. App-Liste aktualisieren.
3. `Groundlift Kino Dienstplan Anmeldung` suchen.
4. `Upgrade` / `Aktualisieren` ausführen.

Erst beim Modul-Upgrade legt Odoo die neuen Datenbankfelder `day_mode`, `is_manual` und `note` an und lädt die aktualisierten Backend- und Website-Views.

## Neue Funktionen ab 19.0.1.2.0

- Auswahl `Reguläre Spieltage`: Donnerstag bis Sonntag oder Dienstag bis Sonntag.
- Wechsel der Auswahl ergänzt fehlende reguläre Tage automatisch beim Speichern.
- Manuelle Zusatztermine können im Reiter `Kinotage` über `Zeile hinzufügen` angelegt werden.
- Manuelle Termine haben ein sichtbares Feld `Notiz für Filmvorführer:innen`.
- Notizen erscheinen auf der öffentlichen Dienstplanseite sowie in Anfrage-, Erinnerungs- und Manager-E-Mails.
