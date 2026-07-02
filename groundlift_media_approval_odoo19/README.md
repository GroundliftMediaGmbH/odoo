# Groundlift Medienfreigabe — Odoo 19 SH Modul

Version: 19.0.1.0.8

## Änderungen in v6

- Bewerter pro Unterordner werden jetzt über eine echte editierbare Tabelle gepflegt.
- In der Tabelle können Name, 6-stellige PIN, E-Mail und Aktiv direkt eingetragen werden.
- Alternativ kann eine bestehende Person ausgewählt werden.
- Beim Speichern werden die Personen automatisch angelegt bzw. synchronisiert.
- Der Upload nutzt für große Dateien weiterhin Chunking, schreibt die Chunks aber nicht mehr per Append-Modus, sondern an konkrete Byte-Offsets.
- Das behebt typische Hetzner/SFTP/FTP-Probleme wie `[Errno 13] Permission denied`, wenn der Server Append verbietet.
- Der Button „Remote-Ordner anlegen“ führt jetzt zusätzlich einen Schreibtest mit `.odoo_write_test` aus.
- Fehlermeldungen bei Schreibrechten zeigen nun den betroffenen Remote-Pfad an.

## Installation / Update

1. ZIP entpacken.
2. Den Modulordner `groundlift_media_approval` vollständig in Odoo.sh/GitHub ersetzen.
3. Commit + Push.
4. Odoo.sh Build abwarten.
5. In Odoo Apps-Liste aktualisieren.
6. Modul aktualisieren.
7. Browser hart neu laden: Strg + F5.

## Nutzung

1. Medienfreigabe → Konfiguration → Hetzner-Verbindungen: Zugangsdaten und Basisordner setzen.
2. Medienfreigabe → Unterordner: Ordner anlegen.
3. Im Reiter „Bewertende Personen“ Name + 6-stellige PIN eintragen.
4. Button „Remote-Ordner anlegen“ drücken. Dieser prüft nun auch Schreibrechte.
5. „Dateien hochladen“ öffnen und Upload starten.

## Hinweis zu Hetzner-Pfaden

Der Basisordner muss dort liegen, wo der FTP/SFTP-Benutzer schreiben darf, z. B. `/public_html/medienfreigabe`. Wenn der Schreibtest fehlschlägt, ist der Pfad oder die Berechtigung des Hetzner-Benutzers falsch.


## Version 19.0.1.0.7 - schnelle Video-Vorschau

Für schnelle Video-Wiedergabe kann in der Hetzner-Verbindung die **Öffentliche Vorschau-Basis-URL** hinterlegt werden, z. B. `https://www.deinedomain.de/medienfreigabe`, wenn der FTP/SFTP-Basisordner `/public_html/medienfreigabe` ist.

Dann prüft Odoo weiterhin zuerst die PIN-Session und leitet die Vorschau danach an den Hetzner-Webserver weiter. Dadurch streamt der Browser Videos direkt vom Webserver mit nativer Byte-Range-Unterstützung, statt große Dateien langsam über Odoo/FTP/SFTP zu ziehen.

Beispiel:
- Basisordner auf Server: `/public_html/medienfreigabe`
- Öffentliche Vorschau-Basis-URL: `https://www.deinedomain.de/medienfreigabe`
- Unterordner: `Sandra Hunke`
- Datei: `clip.mp4`
- Vorschau-URL nach PIN-Prüfung: `https://www.deinedomain.de/medienfreigabe/Sandra%20Hunke/clip.mp4`

Hinweis: Wer die technische Vorschau-URL aus dem Browser-Netzwerkmonitor kopiert, kann die Datei direkt aufrufen. Das war bei der Odoo-Proxy-Vorschau theoretisch ebenfalls als Originalvorschau sichtbar, ist aber bei öffentlicher Hetzner-Auslieferung leichter kopierbar. Für maximale Vertraulichkeit das Feld leer lassen; dann bleibt der geschützte Odoo-Proxy aktiv, ist bei großen Videos aber langsamer.


## Version 19.0.1.0.8 - Fix Video-Vorschau über Hetzner

- Die Website-Vorschau erkennt Bilder/Videos jetzt robust anhand des Dateinamens, auch wenn der Browser beim Upload nur `application/octet-stream` liefert. Dadurch werden bestehende MP4/MOV/WebM-Dateien nicht mehr fälschlich als „Datei ohne Vorschau“ behandelt.
- Die Vorschau verwendet bei aktivierter Option direkt die öffentliche Hetzner-URL im `<video>`/`<img>`-Element.
- Falls die öffentliche URL nicht erreichbar ist oder nicht auf denselben Ordner zeigt, schaltet die Website automatisch auf die geschützte Odoo-Proxy-Vorschau zurück. Damit bleibt die Vorschau sichtbar, auch wenn die Hetzner-Mapping-Einstellung noch falsch ist.
- Die Odoo-Proxy-Vorschau kann nun gezielt mit `?proxy=1` erzwungen werden; ohne diesen Parameter darf weiterhin auf Hetzner umgeleitet werden.
- In „Hetzner Verbindungen“ gibt es nun den Button **Öffentliche URL testen**. Dieser schreibt eine kleine Testdatei in den Basisordner und prüft, ob sie unter der öffentlichen Vorschau-Basis-URL wirklich erreichbar ist.

Nach dem Update bitte in der Hetzner-Verbindung einmal **Öffentliche URL testen** drücken. Wenn dieser Test fehlschlägt, ist nicht die Video-Datei das Problem, sondern die Zuordnung zwischen `Basisordner auf Server` und `Öffentliche Vorschau-Basis-URL`.
