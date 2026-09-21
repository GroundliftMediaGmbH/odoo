# GROUNDLIFT Kino Spielbereitschaft – Odoo 19 SH

Native Odoo-App für das Kinoprogramm und die Spielbereitschaft des Kino Alte Brauerei Stegen.

## Funktionen

- Lädt das aktuelle Kinoprogramm über die Cinetixx-XML-API.
- Erstellt Kino-Spielwochen im Rhythmus Donnerstag bis Mittwoch.
- Zeigt pro Spielwoche eindeutig an:
  - **KINO SPIELBEREIT**
  - **KINO NOCH NICHT SPIELBEREIT**
  - **Noch kein Programm geladen**
- Zeigt Filme standardmäßig zusammengefasst je **Film + Version + Kinosaal + Spielwoche** (frühester Termin und Anzahl der Termine). Über „Identische Filme zusammenfassen“ lassen sich jederzeit alle einzelnen Vorstellungen anzeigen. Diese Einstellung wird pro Spielwoche gespeichert.
- Ein Klick auf **OK** hakt **KDM und DCP gleichzeitig** ab (bzw. beim Entfernen beide ab). Über die vorhandene Gruppensynchronisierung gilt dies für alle Vorstellungen desselben Films und derselben Version im gleichen Saal der Spielwoche.
- Zeigt bei ausgeschalteter Zusammenfassung alle Vorstellungen mit Kino/Saal, Datum/Uhrzeit, Film, Version, KDM und DCP.
- KDM-/DCP-Haken werden wie im Projektmanagement-Kinotab pro Film + Kino + Spielwoche synchronisiert.
- Button „Fehlende KDM an Dispo“ sendet alle fehlenden KDMs an die konfigurierte Dispo-Mailadresse.
- Button „Fehlende DCP an Dispo“ sendet alle fehlenden DCPs an die konfigurierte Dispo-Mailadresse.
- Dispo-Mailadresse ist in den App-Einstellungen änderbar. Standard: `dispo@neokinos.de`.
- Automatischer Scheduler:
  - Montag 17:00 Uhr: aktuelles Kinoprogramm laden.
  - Dienstag 18:00 Uhr: definierter Mitarbeiter wird erinnert, falls nicht alles abgehakt ist.
  - Mittwoch 12:00 Uhr: weitere definierte Mitarbeiter werden eskaliert erinnert, falls das Kino noch nicht spielbereit ist.
- Erinnerungen werden als Odoo-Chatter-Nachricht und Aktivität erstellt.

## Installation in Odoo SH

1. Den Ordner `gl_kino_readiness` in dein Odoo-SH-Repository unter `addons/` oder in den Custom-Addons-Pfad kopieren.
2. Änderungen committen und in die gewünschte Odoo-SH-Branch pushen.
3. In Odoo Apps-Liste aktualisieren.
4. App **GROUNDLIFT Kino Spielbereitschaft** neu installieren oder bei vorhandener Installation **aktualisieren** (App-Upgrade nach GitHub-Deployment).
5. Menü **Kino Spielbereitschaft → Kino-Einstellungen** öffnen und prüfen:
   - Cinetixx-API-URL
   - Dispo-Mailadresse
   - Mitarbeiter für Dienstagabend-Erinnerung
   - Mitarbeiter für Mittwochmittag-Eskalation
6. Menü **Kino Spielbereitschaft → Aktuelles Programm laden** ausführen oder eine Spielwoche öffnen und dort den Button nutzen.

## Technische Hinweise

- Der interne Cron läuft alle 15 Minuten und prüft selbst die Berliner Zeitfenster. Dadurch sind Sommer-/Winterzeitwechsel robuster als bei festem UTC-`nextcall`.
- Montag bis Mittwoch wird operativ die kommende Spielwoche ab Donnerstag geprüft. Ab Donnerstag gilt die laufende Spielwoche.
- Alte Vorstellungen, die bei einem neuen API-Lauf nicht mehr geliefert werden, werden archiviert statt gelöscht.

## Version 19.0.1.1.0

- Neue Standardansicht „Identische Filme zusammenfassen“, jederzeit umschaltbar.
- Die Datensätze werden **nur in der Anzeige** zusammengefasst und nicht gelöscht. Film/Version in verschiedenen Sälen bleiben getrennt, da KDMs saalbezogen sein können.
- Die OK-Checkbox ist direkt anklickbar und setzt KDM und DCP zusammen.
