# Groundlift Kino Dienstplan Anmeldung

Custom Odoo 19 SH Modul für die monatliche Abfrage der Kinovorführer:innen.

## Funktionsumfang

- erzeugt pro Zielmonat automatisch alle Kinotage von Donnerstag bis Sonntag
- findet Empfänger:innen über HR-Mitarbeiter:
  - Abteilung enthält `Kino`
  - Stelle/Stellenbezeichnung enthält `Kinovor`
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
6. Prüfen, dass Kinovorführer:innen als Mitarbeiter mit Arbeits-E-Mail gepflegt sind und Stelle/Stellenbezeichnung `Kinovorführer:in` oder zumindest `Kinovor...` enthält.

## Nutzung

- Menü: `Kino Dienstplan` → `Dienstpläne`
- Manuell testen:
  1. Neuen Dienstplan mit Monat anlegen, z. B. `01.06.2026`.
  2. `Kinotage erzeugen` klicken.
  3. `Anfrage senden` klicken.
- Automatik:
  - Cron `Kino Dienstplan: Monatsanfrage versenden` läuft täglich und sendet nur vom 1. bis 7. eines Monats für den Folgemonat.
  - Cron `Kino Dienstplan: Erinnerung offene Slots` läuft täglich und sendet nach 7 Tagen eine Erinnerung, falls noch Slots offen sind.

## Wichtige Hinweise

- Antworten wie „Ich kann am 16.“ werden nicht automatisch aus Freitext-Mails geparst. Das ist bewusst nicht enthalten, weil Freitext-Antworten fehleranfällig sind. Der sichere Workflow ist der persönliche Eintragelink.
- Die Statusseite ist nicht indexierbar (`sitemap=False`, `robots noindex`) und über Token geschützt, aber ohne Login erreichbar. Das ist absichtlich so, damit Kinovorführer:innen keinen Odoo-Login benötigen.
- Für eine spätere tiefe Integration in Odoo Planning kann bei erfolgreicher Eintragung zusätzlich ein `planning.slot` erzeugt werden.
