# Groundlift Servicepersonal v19.0.2.0.12 – manuelle Absagen pro Schicht

**Neu:** Die Buttons `Service-Absagen` stehen im Backend auf der Serviceschicht und in den Formularen für Veranstaltung und Projekt. Sie öffnen eine Vorschau und lösen ohne Bestätigung noch keine E-Mail aus.

- Zugänglich für interne Odoo-Nutzer mit Schreibzugriff auf die Serviceschicht.
- Nur bei vollständig fest besetzter Schicht (`required_count > 0`, gebuchte Mitarbeiter >= Bedarf).
- Standard: nur noch als *Verfügbar* markierte, nicht gebuchte Personen.
- Die Absagen verwenden die bestehende Vorlage `mail_template_service_not_selected` sowie die bestehende Mail-Freigabe und die vorhandene `_close_full_staffing`-Logik.
- Frühere Absagen bleiben unangetastet. Ein bewusstes erneutes Anschreiben bereits als `not_selected` markierter Personen ist über ein standardmäßig deaktiviertes Kontrollkästchen möglich. Bei noch offenen Mail-Freigaben wird keine zusätzliche Absage angelegt.
- Ungebuchte, noch nicht antwortende Personen und fest gebuchte Personen werden nicht abgesagt. Ohne E-Mail-Adresse kann keine Mail verschickt werden.
- Die manuelle Aktion wird im Chatter der Schicht dokumentiert und meldet, wie viele Mails vorbereitet/ausgelöst wurden.

**Wichtig:** Bei eingeschalteter Mail-Freigabe heißt „Absagen auslösen“ **zur Freigabe vorbereiten**, nicht sofort versenden. Die technische Leitung kann unter Servicepersonal > Mail-Freigaben senden.

**Installation:** Den gesamten Ordner `gl_service_staff` im richtigen Git-Branch ersetzen, Commit/Build auf Odoo.sh kontrollieren und Modul aktualisieren. Erst auf Staging testen.
