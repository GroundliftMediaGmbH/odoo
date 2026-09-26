# Groundlift Servicepersonal – Odoo 19 SH

Version **19.0.2.0.0** ist ein Rework der bestehenden Servicepersonal-App. Bestehende Schichten und bereits gebuchtes Personal werden nicht gelöscht oder neu verteilt.

## Neuer Ablauf

- **Veranstaltungen:** Beim erstmaligen Wechsel in die Phase `Angekündigt` wird eine Serviceschicht erzeugt und an alle aktiven Service-Mitarbeiter eine Verfügbarkeitsanfrage vorbereitet/versendet. Eine Anfrage kann zusätzlich manuell über die Veranstaltung oder die Schicht ausgelöst werden.
- **Projekte:** Neues Feld `Anzahl Servicepersonal`. Beim erstmaligen Wechsel in `Vorbereitung` und Bedarf > 0 wird eine Serviceschicht angelegt und die Verfügbarkeit angefragt.
- **Antwort „Ich bin verfügbar“:** setzt nur den Status `Verfügbar`; es ist noch keine Buchung.
- **Feste Buchung:** Die in den Einstellungen hinterlegte verantwortliche Person wählt verfügbare Mitarbeiter aus und bucht sie fest. Erst dann wird der bisherige technische Status `accepted` gesetzt, damit bestehende Groundlift-Kosten-/Auswertungslogik kompatibel bleibt.
- **Sternebewertung:** aus Mitarbeiter-, Schicht- und Portaloberflächen entfernt; technische Legacy-Felder bleiben nur zur Upgrade-Kompatibilität in der Datenbank/Registry.

## Zeiten

- Veranstaltung standardmäßig: **2 h vor Beginn bis 1 h nach Ende**.
- Die beiden Event-Zusatzzeiten sind global in `Servicepersonal → Einstellungen` editierbar und können pro Veranstaltung überschrieben werden.
- Projekt: Homeautomation-`Startzeit` minus 1 h bis Homeautomation-`Endzeit` plus 1 h.
- Die Groundlift-Homeautomation verwendet auf `project.project` die technischen Felder `ha_start_at` (Startzeit) und `ha_end_at` (Endzeit). Diese sind jetzt die Standardfelder der Servicepersonal-App; die Feldnamen bleiben in den Einstellungen überschreibbar.
- Neu automatisch erzeugte Schichten bleiben an ihre Quellzeit gekoppelt, bis die Standard-Anfangs- oder Endzeit in der Schicht manuell geändert wird. Bestehende Schichten bleiben unverändert.

## Bestandsschutz

Für Schichten, die vor dem Rework bereits existieren, wird **keine automatische Verfügbarkeitsmail** ausgelöst. Bereits als Wunschpersonal (`role=desired`) zugesagte/gebuchte Mitarbeiter bleiben gebucht. Alte Zusagen im Reserve-Status bleiben als Altbestand erhalten und werden nicht als feste Buchung gezählt. Die neue Verfügbarkeitsanfrage für solche Schichten wird bewusst manuell ausgelöst.

## Monatsmail

Am 1. jedes Monats erhält jeder aktive Mitarbeiter mit E-Mail-Adresse eine Übersicht seiner für den aktuellen Monat **fest gebuchten** Einsätze. Der Mitarbeiter kann die Monatsmail über einen persönlichen Link abbestellen. Verfügbarkeitsanfragen und Buchungsbestätigungen werden dadurch nicht abbestellt.

## Mail debugging

`Mail debugging` ist standardmäßig aktiv, solange kein anderer Wert gespeichert wurde. Ist es aktiv, werden **alle von dieser App erzeugten Mails** in `Servicepersonal → Einstellungen → Mail-Freigaben` zurückgehalten. Die konfigurierte technische Leitung kann Betreff, Empfänger und gerenderten HTML-Inhalt prüfen und die Mail anschließend freigeben oder verwerfen.

## Upgrade

1. Ordner `gl_service_staff` auf GitHub durch diese Version ersetzen.
2. Auf Odoo SH pushen und Build abwarten.
3. App `Groundlift Servicepersonal` aktualisieren.
4. `Servicepersonal → Einstellungen` öffnen und mindestens **Verantwortliche Person** sowie **Technische Leitung** setzen.
5. Die Projektfelder stehen standardmäßig auf `ha_start_at` / `ha_end_at`; bei abweichenden Homeautomation-Feldern können sie in den Einstellungen überschrieben werden.
6. Für bestehende unbesetzte Schichten die Verfügbarkeitsanfrage manuell versenden.

## Hinweis zu Daten

Es gibt keine Lösch-/Reset-Migration. Die bestehenden Modelle `gl.service.staff.member`, `gl.service.shift` und `gl.service.shift.line` sowie die bisherigen Zustände `accepted`, `declined`, `invited` bleiben erhalten. `accepted` + `role=desired` gilt im neuen Ablauf als **Gebucht**; ältere `accepted`-Reserveeinträge bleiben unangetastet und werden als Altbestand behandelt.

## 19.0.2.0.2
- E-Mail-Layouts auf robuste, table-basierte HTML-Mails mit festem hellem Hintergrund und expliziten Textfarben umgestellt; dadurch bleiben sie auch in Odoo-Darkmode, Outlook, Gmail, Apple Mail und mobilen Clients lesbar.
- Verfügbarkeitsmails verwenden vor dem Rendern immer den aktuellen Service-Zeitraum aus der Quelle. Bei Veranstaltungen werden die globalen bzw. individuellen Zusatzstunden vor Beginn und nach Ende berücksichtigt.
- Legacy-Schichten werden bei einer neuen Verfügbarkeitsanfrage auf den korrekten Standard-Zeitraum aktualisiert, ohne bereits fest gebuchte Mitarbeiter oder bewusst individualisierte Personalzeiten zu verändern.
- Datum/Uhrzeit in Mails wird kompakt als `TT.MM.JJJJ HH:MM Uhr` ausgegeben.

## Upgrade 19.0.2.0.3 – bestehende Veranstaltungszeiten

Beim Update auf 19.0.2.0.3 werden alle bestehenden, noch nicht beendeten
veranstaltungsgebundenen Serviceschichten einmalig neu berechnet:

- Anfang = Veranstaltungsbeginn minus konfigurierte Vorlaufstunden
- Ende = Veranstaltungsende plus konfigurierte Nachlaufstunden
- individuelle Zusatzstunden einer Veranstaltung haben Vorrang vor den globalen Werten
- Mitarbeiterzeiten, die noch dem bisherigen Standard entsprachen, werden mitgezogen
- individuell abweichende Mitarbeiterzeiten bleiben unverändert
- bestehende Buchungs-/Verfügbarkeitsstatus bleiben unverändert
- durch diese Upgrade-Korrektur werden keine E-Mails erzeugt

Nach der Korrektur folgen diese Veranstaltungsschichten wieder automatisch der Quelle.
Eine spätere manuelle Änderung der Schicht-Anfangs- oder Endzeit löst die Kopplung wie gewohnt.



## 19.0.2.0.5
- Fix: `Mail debugging` speichert nun explizit `1`/`0` in `ir.config_parameter`, damit ein deaktivierter Haken nicht durch den Standardwert wieder aktiviert wird.
