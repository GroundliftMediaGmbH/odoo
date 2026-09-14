# Inbox Filter für Odoo 19 SH

Version: 19.0.1.1.1

## Zweck
GPT-gestützte Sortierung neuer CRM-Leads aus der Phase „Neu“ in:

- Qualifiziert
- Bandanfragen
- SPAM
- Newsletter
- Kino Lieferung/Report
- Rechnungen
- Versand / Paketverfolgung
- Kartenbestellungen
- Projekt/Veranstaltung
- Softbounces / Auto-Antworten
- ToDo für Mitarbeitende
- Kundensupport
- Zu prüfen

## Änderungen in 19.0.1.1.1

- Die direkte Mail-Voransicht liest den vollständigen E-Mail-Body nun zusätzlich aus dem CRM-Chatter (`mail.message`), nicht nur aus `crm.lead.description`. Dadurch erscheinen auch Inhalte, die Odoo bei eingehenden Mails nur im Chatter gespeichert hat.
- Die GPT-Klassifizierung, die Historie und die Kundensupport-Übergabe verwenden dieselbe vollständige Originalmail inklusive Betreff, Absender und Nachrichtentext.
- Die Registerkarte „Originalinhalt“ zeigt nun ebenfalls die angereicherte vollständige Mail.

## Änderungen in 19.0.1.1.0

- SPAM und Newsletter sind vollständig getrennte Kategorien mit eigenen Prompts, Tabs, Suchfiltern und manuellen Korrekturbuttons.
- Neue Kategorien: Rechnungen, Versand/Paketverfolgung, Kartenbestellungen und Softbounces/Auto-Antworten.
- Historie hat den Haken „Perfekt erkannt“. Gesperrte Datensätze können nicht mehr verschoben, rückgängig gemacht oder neu einsortiert werden.
- Jeder Historien-Datensatz hat „Neu erkennen“.
- Im Workspace und in der Historie gibt es „Alle neu einsortieren“ für alle nicht perfekt erkannten Datensätze.
- Manuelle Korrekturen erzeugen nun balancierte Lernregeln: Der Zielprompt wird verbessert und andere Prompts werden bei Verwechslungsgefahr mit Ausschlussregeln nachgeschärft.
- Die Historie zeigt direkt beim Öffnen eine Mail-Voransicht mit Originaltext.
- Kundensupport-Tickets erhalten die Originalnachricht zusätzlich als Mail im Chatter. Unter „Originaltext“ stehen Betreff und vollständige Nachricht.
- Qualifizierte CRM-Einträge, Kundensupport-Tickets und Kartenbestellungen erzeugen eine Benachrichtigung mit Handlungsbedarf.

## Einrichtung

1. Modul installieren oder aktualisieren.
2. Inbox Filter > Einstellungen öffnen.
3. OpenAI API Token eintragen.
4. Speichern.
5. Danach Token prüfen anklicken.

## Hinweise

- Der Token wird zusätzlich nach `ir.config_parameter` gespiegelt, damit ältere Modulpfade und Upgrades kompatibel bleiben.
- Archivkategorien entfernen Datensätze nur aus CRM „Neu“ und speichern sie vollständig in der Inbox-Filter-Historie.
- Endgültiges Löschen gibt es weiterhin nur bewusst über „SPAM bestätigt / löschen“.
- Der alte SPAM/Newsletter-Prompt wird beim Zugriff automatisch auf den neuen SPAM-Prompt umgestellt, damit Newsletter künftig separat gelernt werden.


## 19.0.1.1.3
- Direkte Historien-Voransicht für weitergeleitete Leads korrigiert: reine Odoo-Systemmeldungen wie „Ein neuer Lead wurde … erstellt“ werden nicht mehr als eigentlicher Mailinhalt gewertet.
- Bei mehreren Quellen wird nun der qualitativ beste Originaltext gewählt: gespeicherter Snapshot, aktueller CRM-Chatter oder Historien-Chatter.
- Dadurch erscheinen auch bei Weiterleitungen von Jana/office@groundlift direkt in der Historie die eigentlichen Nachrichteninhalte statt nur der Weiterleitungs-/Lead-Hinweis.

## 19.0.1.1.2

- Neuer Button **Alle Prompts neu generieren** im Inbox-Filter-Arbeitsbereich.
- Analysiert alle Historien-Datensätze mit gesetztem Haken **Perfekt erkannt**.
- Generiert für jede Filterkategorie einen neuen ausführlichen Standardprompt.
- Öffnet anschließend einen Vergleichsdialog: alter Prompt links, neuer Prompt rechts.
- Über **Neuen Prompt als Standard** werden alle neuen Prompts übernommen; die bisherigen Live-Lernbeispiele werden dabei konsolidiert und zurückgesetzt.
- Über **Alten Prompt behalten** wird der Dialog geschlossen, ohne bestehende Prompts zu verändern.


## Version 19.0.1.2.0

- Neuer Button **Alle mit Fehler neu einsortieren**: verarbeitet nur Historien-Vorgänge mit Status Fehler, die nicht als **Perfekt erkannt** gesperrt sind.
- **Alle neu einsortieren** und der neue Fehlerlauf arbeiten als Batch mit sichtbarem Live-Fortschritt.
- OpenAI-Rate-Limit-Schutz: konservatives lokales TPM-Budget, Sicherheitsreserve, Mindestabstand, Auswertung von Rate-Limit-Headern/429-Reset und automatische Fortsetzung statt Retry-Spam.
- Klassifizierungen erhalten ein begrenztes `max_completion_tokens`, um unnötige TPM-Reservierung zu vermeiden.
- Fehlerhafte Sortierungen werden alle 15 Minuten auf fällige Wiederholungsversuche geprüft; dauerhafte Fehler erhalten exponentiell größere Retry-Abstände.
- Begonnene Batch-Jobs laufen per Cron weiter, wenn die Fortschrittsseite geschlossen wird.
