# Groundlift Kino Social Automation

Eigenständige Odoo SH 19 App für automatische Social-Media-Posts des Kinos Alte Brauerei Stegen aus der Cinetixx API.

## Was die App macht

- prüft montags ab der konfigurierten Uhrzeit, standardmäßig 14:00 Uhr Europe/Berlin, ob in der aktuellen Woche Filme geplant sind
- lädt die Vorstellungen aus der Cinetixx API
- erstellt einen Wochenpost mit Standardbild, konfigurierbarer Überschrift, ChatGPT-Zusammenfassung und Programmliste nach Tagen/Filmen
- erstellt pro Vorstellung einen Tages-/Film-Post mit Film-Artwork aus der Cinetixx API, automatisch eingesetzter Uhrzeit, ChatGPT-Kurzzusammenfassung, Ticketlink und Abschlusszeile
- plant Tagesposts je Tag ab 10:00 Uhr mit 5 Minuten Abstand
- verhindert Dubletten über Cinetixx-Show-Schlüssel
- nutzt eigene Kino-Felder auf `social.post`, damit die App getrennt von `groundlift_event_social_auto` bleibt
- übernimmt den Sicherheitsmechanismus aus der Event-Social-App: zukünftige Posts werden beim Freigeben nur geplant und nicht sofort veröffentlicht

## Einrichtung

1. Modulordner `groundlift_kino_social_auto` in den Odoo.sh Addons-Branch legen.
2. Apps aktualisieren und `Groundlift Kino Social Automation` installieren.
3. Menü `Kino Social Automation > Einstellungen` öffnen.
4. Facebook-/Instagram-Kanäle auswählen, z. B. Kanal `Kino Alte Brauerei Stegen`.
5. OpenAI API Key eintragen.
6. Standardbild für den Wochenpost hinterlegen.
7. Bei Bedarf `Posts ohne manuelle Freigabe automatisch planen` aktivieren.

## Wichtige Hinweise

Standardmäßig ist die automatische Freigabe deaktiviert. Die App erzeugt dann Posts als freigabepflichtige Entwürfe. Erst mit `Kino freigeben & geplant lassen` oder mit aktivierter Auto-Freigabe werden die Posts in den geplanten Zustand gesetzt.

Der Cron läuft alle 30 Minuten, erledigt die Montagsprüfung aber nur einmal pro Montag nach Erreichen der konfigurierten Uhrzeit.
