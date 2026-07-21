# Groundlift Stundenzettel-Prüfung – Odoo 19 SH

Eigenständige Odoo-App für die geschützte, zweistufige Prüfung der monatlichen
Stundenzettel von Minijobbern und geringfügig Beschäftigten.

## Modulordner

`gl_timesheet_approval`

## Funktionsumfang

- Geschütztes Prüfportal unter `/stundenzettel/pruefung`
- Zwei Anmeldearten je Prüfer:
  - bestehender Odoo-Benutzer mit dessen Odoo-Zugangsdaten
  - frei vergebener Benutzername und frei vergebenes Passwort
- Prüfer-Kategorien:
  - `1. Prüfer`
  - `2. Prüfer`
- Automatische Erstellung des Vormonats am 1. des Folgemonats
- Automatische E-Mail an alle aktiven 1. Prüfer:
  - „Die Stundenzettel von Groundlift von [Monat] sind online“
- Manueller Button zum Einlesen/Aktualisieren und zum erneuten E-Mail-Versand
- Datenquelle: abgeschlossene Einträge aus Odoo Anwesenheiten (`hr.attendance`)
- Es werden nur als Minijob oder geringfügig beschäftigt erkannte Mitarbeitende übernommen
- Mitarbeiter können alternativ im Mitarbeiterformular ausdrücklich eingeschlossen oder ausgeschlossen werden
- Stundenlohn als Mitarbeiter-Override oder automatische Übernahme eines als stündlich erkannten Vertrags-/Beschäftigungslohns
- Pro Mitarbeiter und Monat:
  - Bruttozeit
  - automatische Pausenzeit
  - abrechenbare Arbeitszeit
  - Stundenlohn
  - Gesamtlohn
  - Status `Nicht freigegeben`, `Abgelehnt` oder `Freigegeben`
  - monatlicher Status `Überwiesen`, ausschließlich durch Prüfer 2
  - zusätzlicher Gesamtmonat-Schalter, der alle vollständig freigegebenen Monatslöhne gemeinsam markiert
- Ausklappbare Mitarbeitenden-Karten mit allen Arbeitstagen
- Mehrere Anwesenheiten eines Tages werden sekundengenau zu einer Tageszeile zusammengefasst
- Bei mehr als sechs Stunden Bruttozeit werden automatisch 30 Minuten Pause angezeigt und abgezogen
- Beide Prüfstufen speichern pro Tag unabhängig:
  - `Geprüft und freigegeben`
  - `Nicht freigegeben`
  - optionale Bemerkung
- Ein Mitarbeiter ist erst grün freigegeben, wenn **alle Tage von Prüfer 1 und Prüfer 2 freigegeben** wurden
- Änderungen an Anwesenheitsdaten oder Stundenlohn setzen betroffene Freigaben und eine vorhandene Überwiesen-Markierung zurück
- Historie aller Vormonate sowie separate Prüfhistorie mit Zeitstempel und Prüfer
- Portal ist von Suchmaschinen ausgeschlossen und sendet `no-store`-Header
- Freie Passwörter werden nur als sicherer Hash gespeichert
- Nach fünf fehlerhaften freien Anmeldungen wird der Zugang 15 Minuten gesperrt

## Installation auf Odoo.sh

1. ZIP-Datei entpacken.
2. Den Ordner `gl_timesheet_approval` vollständig in das GitHub-/Odoo.sh-Repository kopieren.
3. Committen und auf den gewünschten Odoo.sh-Branch pushen.
4. Den Odoo.sh-Build abwarten.
5. In Odoo die Apps-Liste aktualisieren.
6. Nach **Groundlift Stundenzettel-Prüfung** suchen und die App installieren.
7. Geeigneten internen Benutzern unter Einstellungen die Gruppe
   **Stundenzettel-Prüfung: Verwaltung** zuweisen.

## Ersteinrichtung

### 1. Prüfer anlegen

Menü: `Stundenzettel-Prüfung → Prüfer`

Für jeden Prüfer:

1. Kategorie `1. Prüfer` oder `2. Prüfer` wählen.
2. Anmeldeart wählen:
   - **Bestehenden Odoo-Benutzer verwenden**: Benutzer auswählen.
   - **Freie Zugangsdaten**: Benutzername, neues Passwort und E-Mail eintragen.
3. Speichern.
4. Über `Prüfportal öffnen` testen.

Bei bestehendem Odoo-Benutzer erfolgt die Anmeldung über die normale Odoo-Loginseite.
Bei freien Zugangsdaten erfolgt die Anmeldung direkt auf der Portal-Loginseite.

### 2. Mitarbeitende konfigurieren

Menü: `Mitarbeiter → Mitarbeiter`, anschließend Reiter `Stundenzettel-Prüfung`.

- `Automatisch aus Beschäftigungs-/Vertragsart`: Das Modul sucht in den verfügbaren
  aktuellen Vertrags-/Beschäftigungsfeldern nach Begriffen wie `Minijob` oder `geringfügig`.
- `Minijob` oder `Geringfügig beschäftigt`: Mitarbeiter ausdrücklich einschließen.
- `Nicht ... anzeigen`: Mitarbeiter ausdrücklich ausschließen.
- `Stundenlohn für Stundenzettel`: Empfohlener, eindeutiger Stundenlohn-Override.

Da individuelle Odoo-Datenbanken und deutsche Payroll-Lokalisierungen unterschiedliche
Lohnfelder verwenden können, ist der explizite Stundenlohn am Mitarbeiter die zuverlässigste Einstellung.

### 3. Ersten Monat testen

1. `Stundenzettel-Prüfung → Prüfmonate` öffnen.
2. Einen neuen Datensatz mit dem ersten Tag des gewünschten Monats anlegen.
3. `Anwesenheiten einlesen / aktualisieren` klicken.
4. Ergebnis im Reiter `Mitarbeiter` kontrollieren.
5. `Prüfportal öffnen` testen.
6. Bei Bedarf `E-Mail an 1. Prüfer senden` klicken.

## Berechnungslogik

Für jede abgeschlossene Anwesenheit wird die exakte Differenz zwischen `check_in` und
`check_out` in ganzen Sekunden berechnet. Alle Anwesenheiten desselben Mitarbeiters am
selben lokalen Odoo-Anwesenheitsdatum werden summiert.

- Bruttozeit bis einschließlich `06:00:00`: keine automatische Pause
- Bruttozeit größer als `06:00:00`: `00:30:00` automatische Pause
- Arbeitszeit = Bruttozeit − automatische Pause
- Gesamtlohn = Arbeitszeit in Sekunden / 3600 × Stundenlohn

Die Werte werden als Monatssnapshot gespeichert. Dadurch bleiben vergangene Monate
auch dann nachvollziehbar, wenn sich spätere Anwesenheiten ändern.

## Automatik

Der Cronjob läuft täglich. Nur wenn im Firmen-Zeitraum der 1. eines Monats ist, wird:

1. der Vormonat angelegt oder aktualisiert,
2. die Anwesenheitsliste eingelesen,
3. die Benachrichtigung einmalig an alle aktiven 1. Prüfer versendet.

Der Firmen-/Kontakt-Zeitraum wird verwendet; ohne konfigurierte Zeitzone gilt
`Europe/Berlin`.

## Datenschutz und Sicherheit

Das Portal enthält personenbezogene Arbeitszeit- und Lohndaten. Daher:

- Prüferzugänge nur individuell vergeben.
- Keine gemeinsamen Passwörter verwenden.
- Odoo ausschließlich über HTTPS betreiben.
- Ausgeschiedene Prüfer sofort deaktivieren.
- Odoo-Benutzer und freie Prüfer regelmäßig kontrollieren.
- Keine öffentliche Weiterleitung oder Freigabe der Portal-URL einrichten.

## Technische Dateien

- `models/hr_employee.py`: Minijob-Auswahl und Stundenlohn
- `models/reviewer.py`: Prüfer, Anmeldearten und Passwort-Hash
- `models/timesheet_month.py`: Monats-, Mitarbeiter-, Tages- und Historienmodelle
- `controllers/portal.py`: Login, Portal, Freigabe und Überwiesen-Aktion
- `views/portal_templates.xml`: geschützte Website
- `views/timesheet_month_views.xml`: Backend-Prüfmonate
- `views/reviewer_views.xml`: Backend-Prüferverwaltung
- `data/ir_cron.xml`: automatische Monatsverarbeitung

## Version

`19.0.1.0.3`


## Sichtbarkeit auf dem Odoo-Desktop

Die App erscheint als **Stundenzettel-Prüfung** im App-Umschalter. Odoo-Systemadministratoren erhalten die erforderliche Verwaltungsgruppe automatisch. Weitere interne Benutzer können über die Odoo-Benutzerverwaltung der Gruppe **Stundenzettel-Prüfung: Verwaltung** zugeordnet werden.


## Importdiagnose ab Version 1.0.3

Nach `Anwesenheiten einlesen / aktualisieren` zeigt der Prüfmonat:

- Anzahl abgeschlossener Anwesenheitseinträge im Monat
- Anzahl der Mitarbeiter mit Anwesenheiten
- Anzahl der als Minijob/geringfügig erkannt und übernommenen Mitarbeiter
- Anzahl der nicht erkannten oder manuell ausgeschlossenen Mitarbeiter
- einen konkreten Hinweis mit den erkannten Beschäftigungswerten

Die automatische Erkennung berücksichtigt in Odoo 19 insbesondere die aktuelle
Mitarbeiterversion (`current_version_id`), `employee_type`, Vertragsarten,
Beschäftigungsarten, Mitarbeiter-Tags und entsprechend bezeichnete Studio-Felder.
Im Zweifel kann die Auswahl im Mitarbeiter-Reiter `Stundenzettel-Prüfung` ausdrücklich
auf `Minijob` oder `Geringfügig beschäftigt` gesetzt werden.
