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

## Veröffentlichung als Story oder regulärer Post

Unter `Kino Social Automation > Einstellungen` in den Reitern `Montag & Wochenpost` und `Tages-/Film-Posts` das **Standardformat Wochenpost** bzw. **Standardformat Tages-/Film-Posts** auf `Regulärer Post` oder `Story` einstellen und speichern, **bevor** neue Posts erzeugt werden. Bestehende Posts und gespeicherte Wochen werden dadurch nicht verändert. Beide Felder stehen nach dem Update standardmäßig auf `Regulärer Post` (bisheriges Verhalten). Jeder neue Social-Eintrag erhält sein Format als `gl_kino_publish_format`; bei unterstützten Story-Feldern der installierten Social-Erweiterung wird zusätzlich das native Format auf Story gesetzt.

**Wichtig:** Odoos Feld `post_method` unterscheidet nur sofortige vs. zeitgesteuerte Veröffentlichung und ist KEIN Story-Schalter. Ob die installierte Odoo-Social-App Stories an Instagram/Facebook tatsächlich veröffentlichen kann, hängt von ihrem Story-Backend ab. Fehlt ein kompatibles natives Story-Feld, werden neue Storys **nur als Entwurf** angelegt, auch wenn die automatische Freigabe eingeschaltet ist. Das Freigeben als gewöhnlicher Feed-Post wird blockiert. Dies ist keine eigenständige Meta-Story-API-Integration; ohne Story-Backend findet keine Story-Veröffentlichung statt. Bitte den Story-Ablauf zunächst in Staging mit einem Testbeitrag überprüfen.
