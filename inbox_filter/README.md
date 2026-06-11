# Inbox Filter für Odoo 19 SH

Version: 19.0.1.0.4

## Zweck
GPT-gestützte Sortierung neuer CRM-Leads aus der Phase „Neu“ in:

- Qualifiziert
- SPAM
- Projekt/Veranstaltung
- ToDo für Mitarbeitende
- Kundensupport
- Zu prüfen

## Wichtige Änderung ab 19.0.1.0.4
Die OpenAI-Einstellungen werden nicht mehr über den transienten Odoo-Settings-Wizard `res.config.settings` gespeichert, sondern über einen echten persistenten Singleton-Datensatz `inbox.filter.settings`.

Dadurch bleibt der API-Token zuverlässig gespeichert und `Token prüfen` liest direkt aus dem echten Einstellungsdatensatz.

## Einrichtung

1. Modul installieren oder aktualisieren.
2. Inbox Filter > Einstellungen öffnen.
3. OpenAI API Token eintragen.
4. Speichern.
5. Danach Token prüfen anklicken.

## Hinweise

- Der Token wird zusätzlich nach `ir.config_parameter` gespiegelt, damit ältere Modulpfade und Upgrades kompatibel bleiben.
- SPAM/Projekt/VA/ToDo/Kundensupport werden zunächst sicher archiviert und in der Inbox-Filter-Historie protokolliert.
- Endgültiges Löschen erfolgt nur über „SPAM bestätigt“.


## Version 19.0.1.0.6

- Neuer Filter **Bandanfragen** mit eigenem Prompt, Tab, Historienkategorie und manueller Korrektur.
- Zutreffende Bandanfragen werden in die CRM-Phase **Bandanfragen** verschoben.
- Neue CRM-Datensätze, die in der Phase **Neu** eingehen, werden automatisch sortiert, sofern die Einstellung **Automatisch sortieren** aktiv ist.
- Die Automatik ist fehlertolerant: API-/Klassifizierungsfehler verhindern nicht das Erstellen des CRM-Datensatzes.
