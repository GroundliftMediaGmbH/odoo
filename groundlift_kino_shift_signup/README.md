# Groundlift Kino Dienstplan Anmeldung

Custom Odoo 19 SH Modul für die monatliche Abfrage und Verwaltung der Filmvorführer:innen-Schichten.

## Version 19.0.1.7.0

Diese Version erweitert die bestehende Schichtlogik um sechs Punkte:

1. **Eintragungsfrist / Prioritäten-Sperre**
   - Die Priorisierungsphase endet zwei Wochen vor der ersten Schicht des Dienstplans.
   - Bis einschließlich Fristdatum können Filmvorführer:innen Prioritäten setzen.
   - Ab dem Folgetag sind keine neuen Prioritäten und keine Wunsch-Übernahmen bereits besetzter Termine mehr möglich.
   - Nach Ablauf der Frist können nur noch freie Termine direkt übernommen oder bestehende Termine per Tauschanfrage geändert werden.

2. **Automatische Anfragekette für Zusatztermine**
   - Wird in einem bereits geöffneten Dienstplan ein manueller Zusatztermin angelegt, z. B. private Kinovermietung, erhalten alle aktiven Filmvorführer:innen eine Info-Mail.
   - Danach fragt das System automatisch jeweils die Person mit der geringsten Anzahl bereits übernommener Schichten an.
   - Klickt diese Person auf „Nein, ich kann nicht“, wird automatisch die nächste geeignete Person mit der nächsthöheren bzw. nächstpassenden Schichtanzahl angeschrieben.
   - Klickt die angefragte Person auf „Ja, ich übernehme“, wird der Zusatztermin direkt fix besetzt.
   - Ist der Zusatztermin eine Woche vorher noch unbesetzt, sendet ein täglicher Cron eine Erinnerung an alle Filmvorführer:innen und eine separate Mail an die hinterlegte Vorgesetzten-Adresse.

3. **Backend-Teamliste für Filmvorführer:innen**
   - Neues Menü: `Kino Dienstplan` → `Filmvorführer:innen`.
   - Über „Neu“ / „Hinzufügen“ kann jede aktive Mitarbeiter:in des Unternehmens in das Kino-Schichtsystem aufgenommen werden.
   - Die gepflegte Teamliste ist maßgeblich für Einladungen, Erinnerungen und Zusatztermin-Anfragen.
   - Falls noch keine Teamliste gepflegt ist, verwendet das Modul aus Kompatibilitätsgründen weiterhin den bisherigen Fallback: Abteilung/Stelle enthält `Kino` bzw. `Filmvor...` und Arbeits-E-Mail ist gesetzt.

4. **Monatslimit für Schichten**
   - Pro Dienstplan gibt es das neue Feld `Max. Schichten pro Person/Monat`.
   - Standardwert: `6`.
   - Die persönliche Anmeldeseite zeigt sichtbar an, wie viele Schichten die Person bereits übernommen hat und wie viele noch möglich sind.
   - Das Limit wird bei normalen Eintragungen, freien Terminen nach Fristablauf, Tauschen, Übergabe-Annahmen und Zusatztermin-Anfragen serverseitig geprüft.

5. **Robuste Zusatztermin-Ablehnung**
   - Klickt die einzeln angefragte Person auf `Nein, ich kann nicht`, wird die nächste geeignete Person sofort neu ermittelt.
   - Die Reihenfolge ist: wenigste bereits übernommene Schichten, bei Gleichstand alphabetisch nach Name.
   - Der abgelehnte Anfrage-Datensatz kann die Kette nicht mehr als vermeintlich offene Anfrage blockieren.

6. **24-Stunden-Korrektur eigener Eintragungen**
   - Nach einer erfolgreichen Eintragung erscheint innerhalb der laufenden Eintragungsfrist für 24 Stunden der Button `Korrigieren`.
   - Die Korrektur nimmt die eigene Eintragung zurück; danach wird der Termin wieder offen oder anhand vorhandener Prioritäten neu vergeben.

## Grundfunktionen

- erzeugt pro Zielmonat automatisch reguläre Kinotage nach Auswahl:
  - Donnerstag bis Sonntag
  - Dienstag bis Sonntag
- erlaubt manuelle Zusatztermine mit sichtbarer Notiz für Filmvorführer:innen, z. B. private Vermietung 11:00–18:00
- versendet in der ersten Woche des Monats eine Anfrage für den Folgemonat
- versendet nach 7 Tagen genau eine Erinnerung, sofern noch Slots offen sind oder Tauschanfragen laufen
- stellt eine öffentliche, aber tokenisierte Status-/Eintrageseite bereit
- persönliche Links erlauben die Eintragung in offene Kinotage
- verhindert unkontrolliertes Überschreiben durch Datenbanksperre auf Slot-Ebene
- benachrichtigt nach jeder fixen Eintragung die zuständige E-Mail-Adresse mit Füllstand und offenen Tagen

## Prioritäten / Ranking

Filmvorführer:innen können während der Priorisierungsphase pro Termin eine Auswahl abgeben:

1. `will ich unbedingt machen`
2. `kann ich übernehmen`

Die automatische Besetzung folgt dieser Logik:

- `will ich unbedingt machen` hat Vorrang vor `kann ich übernehmen`, solange der Termin noch nicht fix besetzt ist.
- Bei gleicher Priorität zählt die zuerst gespeicherte Eintragung.
- `will ich unbedingt machen` ist pro Person limitiert.
- Die Quote wird aus `Anzahl Kinotage / Anzahl Filmvorführer:innen` berechnet und technisch aufgerundet.
- Bereits fix besetzte Termine werden nicht automatisch überschrieben. Vor der Eintragungsfrist kann nur eine Übergabeanfrage an die aktuell eingetragene Person ausgelöst werden.
- Nach Ablauf der Eintragungsfrist kann kein `kann ich übernehmen` mehr durch `will ich unbedingt machen` verdrängt werden.

## Tauschanfragen

- Hat eine Person einen Termin übernommen, erscheint auf der persönlichen Seite neben `Von dir übernommen` der Button `Tauschen`.
- Beim Klick erscheint die Browser-Bestätigung: `Kannst du an diesem Tag wirklich nicht?`
- Wird bestätigt, erhält der Slot den Status `Tauschanfrage`.
- Alle anderen Filmvorführer:innen erhalten eine E-Mail mit Ja-/Nein-Link.
- Klickt eine andere Person auf `Ja`, wird sie direkt für den Termin eingetragen, sofern die Tauschanfrage noch offen ist und das Monatslimit nicht überschritten wird.
- Klickt eine Person auf `Nein`, wird nichts eingetragen und nur eine Rückmeldung angezeigt.

## Zusatztermin-Workflow

Ein Zusatztermin ist ein manuell angelegter Kinotag (`Manuell = aktiv`). Wird er in einem bereits geöffneten Dienstplan ohne Besetzung angelegt, läuft automatisch:

1. Info-Mail an alle Filmvorführer:innen.
2. Einzelanfrage an die Person mit der geringsten bisherigen Schichtanzahl.
3. Bei Ablehnung automatische Anfrage an die nächste geeignete Person.
4. Bei Annahme direkte fixe Besetzung.
5. Eine Woche vor dem Termin: Erinnerung an alle und Meldung an die Vorgesetzten-Adresse, falls der Termin noch offen ist.

Im Backend ist der Verlauf im Reiter `Kinotage` → Datensatz öffnen → `Automatische Zusatztermin-Anfragen` sichtbar. Zusätzlich gibt es das Menü `Zusatztermin-Anfragen`.

## Installation auf Odoo SH

1. Ordner `groundlift_kino_shift_signup` in das Custom-Addons-Verzeichnis des Odoo-SH-Repositories kopieren.
2. Commit und Push in den gewünschten Branch.
3. In Odoo Apps-Liste aktualisieren.
4. App `Groundlift Kino Dienstplan Anmeldung` installieren oder aktualisieren.
5. Bei bestehenden Installationen zwingend die App upgraden, damit neue Felder, Datenbankspalten, Views, Cronjobs und Zugriffsrechte geladen werden.
6. Menü `Kino Dienstplan` → `Filmvorführer:innen` öffnen und das Team pflegen.
7. Prüfen, dass bei den ausgewählten Mitarbeiter:innen eine Arbeits-E-Mail gepflegt ist.

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
  - Cron `Kino Dienstplan: Zusatztermin 1-Woche-Erinnerung` läuft täglich und prüft offene Zusatztermine innerhalb der nächsten 7 Tage.

## Wichtige Hinweise

- Antworten wie „Ich kann am 16.“ werden nicht automatisch aus Freitext-Mails geparst. Der sichere Workflow ist der persönliche Eintragelink.
- Die Statusseite ist nicht indexierbar (`sitemap=False`, `robots noindex`) und über Token geschützt, aber ohne Login erreichbar.
- Für eine spätere tiefe Integration in Odoo Planning kann bei erfolgreicher Eintragung zusätzlich ein `planning.slot` erzeugt werden.
