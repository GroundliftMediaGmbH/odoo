# Groundlift Kino Dienstplan Anmeldung

Custom Odoo 19 SH Modul für die monatliche Abfrage der Filmvorführer:innen.

## Funktionsumfang

- erzeugt pro Zielmonat automatisch reguläre Kinotage nach Auswahl:
  - Donnerstag bis Sonntag
  - Dienstag bis Sonntag
- erlaubt manuelle Zusatztermine mit sichtbarer Notiz für Filmvorführer:innen, z. B. private Vermietung 11:00–18:00
- findet Empfänger:innen über HR-Mitarbeiter:
  - Abteilung enthält `Kino`
  - Stelle/Stellenbezeichnung enthält `Filmvor`
  - Arbeits-E-Mail ist gepflegt
- versendet in der ersten Woche des Monats eine Anfrage für den Folgemonat
- versendet nach 7 Tagen genau eine Erinnerung, sofern noch Slots offen sind oder Tauschanfragen laufen
- stellt eine öffentliche, aber tokenisierte Status-/Eintrageseite bereit
- persönliche Links erlauben die Eintragung in offene Kinotage
- verhindert unkontrolliertes Überschreiben durch Datenbanksperre auf Slot-Ebene
- benachrichtigt nach jeder fixen Eintragung die zuständige E-Mail-Adresse mit Füllstand und offenen Tagen

## Prioritäten / Ranking

Filmvorführer:innen können pro Termin eine Auswahl abgeben:

1. `will ich unbedingt machen`
2. `kann ich übernehmen`

Die automatische Besetzung folgt dieser Logik:

- `will ich unbedingt machen` hat Vorrang vor `kann ich übernehmen`.
- Bei gleicher Priorität zählt die zuerst gespeicherte Eintragung.
- `kann ich übernehmen` kann für beliebig viele Termine gewählt werden.
- `will ich unbedingt machen` ist pro Person limitiert.
- Die Quote wird aus `Anzahl Kinotage / Anzahl Filmvorführer:innen` berechnet und technisch aufgerundet, damit eine ganzzahlige Anzahl an priorisierbaren Schichten entsteht.
- Auf der persönlichen Website steht: `Du kannst noch xx Schichten priorisieren`.

## Tauschanfragen

- Hat eine Person einen Termin übernommen, erscheint auf der persönlichen Seite neben `Von dir übernommen` der Button `Tauschen`.
- Beim Klick erscheint die Browser-Bestätigung: `Kannst du an diesem Tag wirklich nicht?`
- Wird bestätigt, erhält der Slot den Status `Tauschanfrage`.
- Alle anderen Filmvorführer:innen erhalten eine E-Mail mit Ja-/Nein-Link.
- Klickt eine andere Person auf `Ja`, wird sie direkt für den Termin eingetragen, sofern die Tauschanfrage noch offen ist.
- Klickt eine Person auf `Nein`, wird nichts eingetragen und nur eine Rückmeldung angezeigt.
- Auf personalisierter Seite und Übersichtsseite wird der Slot währenddessen als `Tauschanfrage` angezeigt, nicht als fix besetzt.

## Installation auf Odoo SH

1. Ordner `groundlift_kino_shift_signup` in das Custom-Addons-Verzeichnis des Odoo-SH-Repositories kopieren.
2. Commit und Push in den gewünschten Branch.
3. In Odoo Apps-Liste aktualisieren.
4. App `Groundlift Kino Dienstplan Anmeldung` installieren oder aktualisieren.
5. Bei bestehenden Installationen zwingend die App upgraden, damit neue Felder, Datenbankspalten und XML-Views geladen werden.
6. Prüfen, dass die Abteilung `Kino` existiert und der/die Vorgesetzte dort gesetzt ist.
7. Prüfen, dass Filmvorführer:innen als Mitarbeiter mit Arbeits-E-Mail gepflegt sind und Stelle/Stellenbezeichnung `Filmvorführer:in` oder zumindest `Filmvor...` enthält.

## Nutzung

- Menü: `Kino Dienstplan` → `Dienstpläne`
- Manuell testen:
  1. Neuen Dienstplan mit Monat anlegen, z. B. `01.06.2026`.
  2. `Reguläre Spieltage` auswählen.
  3. `Kinotage erzeugen` klicken.
  4. Bei Bedarf manuelle Zusatztermine im Reiter `Kinotage` hinzufügen.
  5. `Anfrage senden` klicken.
- Automatik:
  - Cron `Kino Dienstplan: Monatsanfrage versenden` läuft täglich und sendet nur vom 1. bis 7. eines Monats für den Folgemonat.
  - Cron `Kino Dienstplan: Erinnerung offene Slots` läuft täglich und sendet nach 7 Tagen eine Erinnerung, falls noch Slots offen sind oder Tauschanfragen laufen.

## Wichtige Hinweise

- Antworten wie „Ich kann am 16.“ werden nicht automatisch aus Freitext-Mails geparst. Das ist bewusst nicht enthalten, weil Freitext-Antworten fehleranfällig sind. Der sichere Workflow ist der persönliche Eintragelink.
- Die Statusseite ist nicht indexierbar (`sitemap=False`, `robots noindex`) und über Token geschützt, aber ohne Login erreichbar. Das ist absichtlich so, damit Filmvorführer:innen keinen Odoo-Login benötigen.
- Für eine spätere tiefe Integration in Odoo Planning kann bei erfolgreicher Eintragung zusätzlich ein `planning.slot` erzeugt werden.
