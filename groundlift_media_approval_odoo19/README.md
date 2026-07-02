# Groundlift Medienfreigabe für Odoo 19 / Odoo.sh

Version: 19.0.1.0.5

Diese Version erweitert die Medienfreigabe um Ordner-spezifische Bewerter, einen direkten Homepage-Button und einen Mehrfach-Upload für große Foto-/Videodateien.

## Wichtige Änderungen in 19.0.1.0.5

- In der Unterordner-Liste gibt es im Header den Button `Homepage aufrufen`.
- In der Unterordner-Form gibt es ebenfalls den Button `Homepage aufrufen`.
- Der Menüpunkt `Freigabe > Dateien hochladen` öffnet jetzt eine eigene Upload-Seite.
- Der Upload nutzt nicht mehr den alten Base64-Anhangsweg als Hauptworkflow, sondern eine eigene Mehrfach-Dateiauswahl.
- Bis zu 50 Dateien pro Durchlauf, serverseitig begrenzt auf 200 MB pro Datei.
- Zwei Dateien werden parallel übertragen; dadurch ist der Upload schneller, ohne Hetzner/Odoo.sh unnötig zu überlasten.
- Die Datei wird nach dem Browser-Upload direkt per FTP/SFTP/FTPS auf den Hetzner-Ordner geschrieben.
- Pro Unterordner können jetzt `Bewertende Personen` ausgewählt werden.
- Beim Upload wird pro Datei ein fester Personen-Snapshot aus den Bewertern des Ordners gespeichert.
- Später hinzugefügte Personen sehen und bewerten nur danach hochgeladene Dateien.
- Bereits bestehende Dateien behalten ihren ursprünglichen Freigabe-Kreis.

- Uploads laufen jetzt in kleinen Chunks von 5 MB. Dadurch wird der vorherige HTTP-413-Fehler bei größeren Dateien vermieden, sofern Odoo.sh normale kleine Requests akzeptiert.
- Die Upload-Seite blockiert den Upload mit einer verständlichen Meldung, wenn im Unterordner noch keine bewertende Person hinterlegt ist.
- Der Reiter `Bewertende Personen` zeigt nun eine editierbare Liste. Dort können Name, PIN und E-Mail direkt im Unterordner eingetragen oder bestehende Personen ausgewählt werden.
- Das Feld `Unterordnername auf Server` heißt jetzt klarer `Unterordnername`.

## Installation / Update auf Odoo.sh

1. ZIP entpacken.
2. Den Ordner `groundlift_media_approval` in dein Odoo.sh-Git-Repository legen bzw. den alten Ordner vollständig ersetzen.
3. Commit und Push ausführen.
4. Odoo.sh Build abwarten.
5. In Odoo: Apps-Liste aktualisieren.
6. App `Groundlift Medienfreigabe` aktualisieren oder installieren.
7. Browser hart neu laden (`Strg + F5`).

## Benutzung

1. App `Medienfreigabe` öffnen.
2. Unter `Konfiguration > Personen / PINs` Personen anlegen und je Person eine sechsstellige PIN vergeben.
3. Unter `Konfiguration > Hetzner Verbindungen` FTP/SFTP-Zugang hinterlegen.
4. Unter `Freigabe > Unterordner` Zielordner anlegen.
5. Im Unterordner im Reiter `Bewertende Personen` auswählen, wer diesen Ordner bewerten darf.
6. Über `Dateien hochladen` oder den Button im Unterordner Fotos/Videos hochladen.
7. Externe Personen öffnen `/media-approval` oder `/medienfreigabe` und melden sich nur per PIN an.

## Technischer Hinweis

Die App vermeidet beim neuen Upload den Base64-Mehrfachanhang als Hauptweg. Große Dateien werden im Browser in 5-MB-Blöcke geschnitten. Jeder Block läuft einzeln durch Odoo.sh und wird serverseitig an die Zieldatei auf Hetzner angehängt. Dadurch wird ein großer 200-MB-Request vermieden.
