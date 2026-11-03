# Groundlift Servicepersonal 19.0.2.0.14 – Absage-Mail bei manueller Statusänderung

## Neue Funktion
- Wenn eine Servicepersonal-Zuteilung in einer Veranstaltung, einem Projekt oder der Zuteilungsliste **direkt** auf **„Absage: Nicht eingeplant“** (`state = not_selected`) geändert wird, erstellt die App für den Mitarbeitenden die neutrale manuelle Absage-E-Mail.
- Die Erkennung erfolgt beim Speichern (`create` / `write`) auf `gl.service.shift.line`, nicht nur in einer einzelnen Ansicht. Sie greift daher auch in eingebetteten Schichtlisten.
- Wie bisher läuft die E-Mail bei aktivierter Option „Mail debugging“ zunächst über die Mail-Freigabe. Bei deaktivierter Mail-Freigabe erfolgt der unmittelbare Versand.
- Bereits auf „Absage: Nicht eingeplant“ stehende Einträge werden durch bloßes Speichern **nicht erneut angeschrieben**. Bei einem erneuten Wechsel von einem anderen Status zur Absage erfolgt eine neue Mail.
- Der Grund wird auf `manual` gesetzt, die Rolle auf `reserve` gestellt und das Antwort-Token gewechselt, um alte Antwortlinks zu entwerten. Offene ältere E-Mails zur selben Einteilung (Anfrage, Zeitänderung, Buchung, Vortagserinnerung oder Absage) werden aus der Freigabe entfernt.
- Ohne E-Mail-Adresse wird kein Versand ausgelöst und der fehlende Versand im Chatter der Zuteilung dokumentiert.

## Vermeidung doppelter E-Mails
- Der bereits vorhandene Button **„Absagen“** verschickt weiterhin wie bisher seine manuelle Absage-Mail und unterdrückt dabei den zusätzlichen Trigger.
- Die automatische Absage bei vollständig besetzter Schicht nutzt weiterhin die passende eigene Vorlage und unterdrückt den zusätzlichen Trigger.
- Ein Statuswechsel und eine gleichzeitige Zeitänderung lösen keine widersprüchliche Zeitbestätigungs-E-Mail für eine nicht mehr gebuchte Person aus.

## Installation
1. Modulordner `gl_service_staff` aus der ZIP im Odoo.sh-Repository gegen die vorhandene Version austauschen.
2. Auf **Staging** deployen und das Modul **Groundlift Servicepersonal** aktualisieren.
3. Test: Einen als verfügbar gemeldeten Mitarbeitenden per Statusfeld auf „Absage: Nicht eingeplant“ ändern. Im Menü **Mail-Freigabe** die neue Absage überprüfen bzw. bei deaktivierter Freigabe den direkten Versand testen.
4. Prüfen, dass ein erneutes Speichern desselben Status keine zweite E-Mail erzeugt und der vorhandene **„Absagen“**-Button genau eine E-Mail vorbereitet.

Die bestehenden Datensätze werden beim Modulupdate nicht nachträglich angeschrieben. Änderungen wirken nur für neue Statuswechsel nach dem Update.
