# Groundlift Servicepersonal für Odoo 19 SH

Dieses Modul legt eine neue Odoo-App **Servicepersonal** an.

## Enthaltene Funktionen


### Update 19.0.1.4.0

- Mitarbeiterportal zeigt die Arbeitszeit nun kompakt als `TT.MM.JJJJ HH:MM Uhr bis TT.MM.JJJJ HH:MM Uhr`, ohne doppelte Datumszeile.
- Die Servicepersonal-Web-Übersicht zeigt bei jeder Person zusätzlich die individuell gebuchte Arbeitszeit.
- Wenn bei bereits zugesagtem Servicepersonal die individuelle Anfangs- oder Endzeit geändert wird, wird automatisch eine Bestätigungsmail für die Zeitänderung versendet.
- Bestätigung einer Zeitänderung zeigt öffentlich: „Danke für deine Flexibilität.“
- Ablehnung einer Zeitänderung zeigt öffentlich: „Vielen Dank für Deine Rückmeldung.“
- Nicht bestätigte oder abgelehnte Zeitänderungen werden im Backend in der Zuteilung sichtbar als Warnung markiert.

### Update 19.0.1.3.0

- Auf den Mitarbeiter-Homepages werden keine internen Bewertungen, Sterne-Wertungen oder Reserve-/Wunschpersonal-Einteilungen mehr angezeigt.
- Die öffentliche Übersicht bleibt wertungsfrei und zeigt weiterhin nur die relevanten Schichtinformationen.

### Update 19.0.1.2.0

- Spontane Schichten innerhalb der 3-Wochen-Frist verwenden jetzt eine eigene Erst-Anfrage mit passender Tonalität statt „Letzte Rückfrage“.
- Bei spontanen Schichten werden automatisch `Benötigtes Servicepersonal + 2` Personen aus dem Ranking angefragt. Die zusätzlichen Personen bleiben Reservepersonal.
- Automatisch erzeugte Schichtnamen enthalten keinen Präfix „Veranstaltung:“ oder „Projekt:“ mehr.
- Sternebewertungen werden in der Oberfläche per Dropdown ausgewählt.

### Update 19.0.1.1.0

- Button-Reihenfolge in Schichten geändert: **Personalliste erzeugen** vor **Servicepersonal buchen**.
- Der Button **Nach Sternen zuteilen** wurde aus der Oberfläche entfernt; die Bewertung bleibt die Standardlogik.
- Im Schichtformular gibt es unten nur noch den Tab **Servicekräfte**.
- **Personalliste erzeugen** erzeugt alle aktiven Servicekräfte und setzt exakt `Benötigtes Servicepersonal` als Wunschpersonal; alle übrigen bleiben Reservepersonal.
- Bei Absage oder Fristablauf wird die bisherige Person wieder Reservepersonal und der nächste Kandidat wird Wunschpersonal/Nachrücker.
- Mitarbeiter-Webseiten sind im Backend über **Servicepersonal → Mitarbeiter → Webseite öffnen** erreichbar.
- Die allgemeine Web-Übersicht ist im Backend über **Servicepersonal → Web-Übersicht** erreichbar.


- Servicepersonal-Liste auf Basis von `hr.employee` mit 1–5-Sterne-Bewertung und PIN-Code.
- Automatische Schichterzeugung für:
  - `project.project`, wenn `stage_id.name == "In Bearbeitung"` und `date_start` gesetzt ist.
  - `event.event`, wenn `stage_id.name == "Angekündigt"` und `date_begin` gesetzt ist.
- Manuelles Einholen bereits bestehender passender Projekte/Veranstaltungen über Menüpunkt und Button.
- Pro Schicht:
  - benötigte Anzahl Servicepersonal,
  - Standard-Anfangs-/Endzeit,
  - individuelle Anfangs-/Endzeit pro Person,
  - Wunschpersonal / Reservepersonal,
  - schichtbezogene Sternebewertung als Override,
  - manuelles Tauschen, Eintragen und Austragen über Odoo.
- Button **Servicepersonal buchen** zum Versenden von Einladungen.
- E-Mail-Buttons:
  - **Ich bin gerne dabei**
  - **Ich kann leider nicht**
- Automatische Statuslogik mit grünem Haken, sobald genügend Personen zugesagt haben.
- Automatischer Cron stündlich:
  - 4 Wochen vorher Erinnerung,
  - 3 Wochen vorher letzte Erinnerung mit 6h-Frist,
  - automatische Nachrücker bei Absage oder Fristversäumnis,
  - Nachrücker wegen 6h-Frist erhalten 3 Tage Antwortfrist,
  - Vortagserinnerung mit Arbeitszeiten.
- Mitarbeiterportal unter `/servicepersonal` mit PIN-Login.
- Öffentliche Gesamtübersicht unter `/servicepersonal/overview`.

## Installation auf Odoo SH

1. Ordner `gl_service_staff` in das Custom-Addons-Repository kopieren.
2. Auf den gewünschten Odoo-SH-Branch committen und pushen.
3. Odoo SH bauen lassen.
4. Apps-Liste aktualisieren.
5. App **Groundlift Servicepersonal** installieren.
6. Unter **Servicepersonal → Mitarbeiter** die Servicekräfte aus `hr.employee` auswählen und bewerten.
7. Unter **Servicepersonal → Bestehende Events/Projekte einholen** vorhandene Projekte/Events synchronisieren.

## Technische Felder

- Projekte: `project.project.date_start`
- Veranstaltungen: `event.event.date_begin`

## Hinweis

Die automatische Synchronisierung reagiert auf `create()` und `write()` von `project.project` und `event.event`, wenn die Stage oder das Datum geändert wird. Die Stage-Namen müssen exakt zu den deutschen Bezeichnungen passen:

- Projekt: `In Bearbeitung`
- Veranstaltung: `Angekündigt`

Falls eure Stage intern anders heißt, müssen die beiden Methoden in `models/project_project.py` und `models/event_event.py` angepasst werden.
