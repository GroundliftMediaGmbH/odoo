# Groundlift Medienfreigabe


## Version 19.0.1.0.17

- „Nicht freigeben“ löscht die betroffene Datei sofort vom FTP/SFTP-Server und blendet sie unmittelbar aus der Website-Liste aus.
- Der Odoo-Datensatz bleibt archiviert als Prüf- und Notizhistorie erhalten.
- Scheitert die Löschung auf dem Server, bleibt die Datei sichtbar und die Website zeigt eine verständliche Fehlermeldung.
- Nach „Freigeben“ wird automatisch die nächste Datei geöffnet.
- Die Scrollposition der linken Dateiliste bleibt zwischen den Seitenaufrufen erhalten; der aktive Eintrag wird sichtbar gehalten.

## Version 19.0.1.0.15

- Website-Oberfläche dauerhaft auf ein geräteunabhängiges Dark-Mode-Design umgestellt.
- Sämtliche Texte, Metadaten, Formularfelder, Karten, Hinweise und Buttons kontrastreich hell dargestellt.
- Dark-Mode-Styling bleibt auf die Medienfreigabe-Seiten begrenzt und verändert die übrige Odoo-Website nicht.
 — Odoo 19 SH Modul

Version: 19.0.1.0.9

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


## Version 19.0.1.0.9 - schneller Direkt-Download über Hetzner

- Der grüne Download-Button lädt freigegebene Dateien jetzt standardmäßig direkt von der öffentlichen Hetzner-URL.
- Odoo prüft weiterhin Login/PIN, Freigabe-Kreis und Status „freigegeben“, zieht die Datei danach aber nicht mehr komplett per FTP/SFTP durch Odoo.
- In „Hetzner Verbindungen“ gibt es die neue Option **Downloads direkt über Hetzner ausliefern**. Sie ist standardmäßig aktiv.
- Falls die öffentliche URL leer ist oder die Option deaktiviert wird, bleibt der bisherige geschützte Odoo-Download als Fallback erhalten.
- Technischer Fallback: `/media-approval/download/<ID>?proxy=1` erzwingt den alten Odoo-Proxy-Download.

Hinweis: Für echte Browser-Downloads statt Öffnen im Player setzt die Website zusätzlich das HTML-Attribut `download`. Falls ein Browser das bei einer fremden Domain ignoriert, muss Hetzner/Apache optional per Header `Content-Disposition: attachment` konfiguriert werden. Die Geschwindigkeit ist trotzdem bereits direkt Hetzner → Browser.


## Version 19.0.1.0.11 – erzwungener echter Hetzner-Download

Der Download-Button bleibt jetzt auf der Odoo-Route, damit Odoo vor dem Download weiterhin PIN, Personenzuordnung und finalen Freigabestatus prüfen kann. Danach erfolgt ein schneller 302-Redirect direkt zur Hetzner-Datei. Die Datei selbst läuft also nicht über Odoo/FTP/SFTP.

Damit MP4/MOV-Dateien browser- und mobilfreundlich wirklich als Datei-Download behandelt werden, kann die App im öffentlichen Medienordner eine markierte `.htaccess`-Regel installieren. Diese sendet für URLs mit `?download=1` den Header `Content-Disposition: attachment`. Die Vorschau-URL ohne `?download=1` bleibt inline abspielbar.

Nach dem Modul-Update:

1. In **Medienfreigabe → Konfiguration → Hetzner Verbindungen** öffnen.
2. **Öffentliche URL testen** ausführen.
3. **Download erzwingen testen** ausführen.
4. Browser hart neu laden.

Falls der Test mit HTTP 500 scheitert, erlaubt der Webspace wahrscheinlich eine der `.htaccess`-Direktiven nicht oder `mod_headers` ist nicht aktiv. Dann muss die Header-Regel serverseitig bei Hetzner/Apache gesetzt werden.

### 19.0.1.0.11
- Download-Button robuster gemacht: Das HTML-`download`-Attribut wurde entfernt, weil Browser bei Redirects auf eine andere Domain sehr unterschiedlich reagieren.
- `?download=1` wird nur noch verwendet, wenn der Hetzner-Download-Header-Test wirklich erfolgreich war.
- Falls eine erzwungene Download-URL nicht erreichbar ist, fällt Odoo automatisch auf die normale schnelle Hetzner-URL zurück, statt Chrome/Mobile mit „Datei ist auf der Website nicht verfügbar“ abbrechen zu lassen.


## 19.0.1.0.13

- Fix: RPC_ERROR im Button „Download erzwingen testen“ behoben. Ursache war eine lokale Variable `_`, die die Odoo-Übersetzungsfunktion überschrieben hat.
- .htaccess Download-Erkennung robuster gemacht: `download=1` wird zusätzlich über `THE_REQUEST` geprüft.


## Version 19.0.1.0.13

Download-Erzwingen robuster gemacht:

- Wenn Hetzner zwar `.htaccess` erlaubt, aber keinen `Content-Disposition: attachment` Header sendet, installiert die App automatisch einen kleinen signierten PHP-Download-Helfer (`glma_download.php`) im öffentlichen Medienfreigabe-Ordner.
- Die Berechtigung bleibt in Odoo: PIN, Person und Freigabe-Status werden zuerst geprüft.
- Danach leitet Odoo auf eine kurzzeitig signierte Hetzner-URL weiter.
- Die große Datei läuft weiterhin direkt von Hetzner zum Browser; Odoo holt sie nicht per FTP/SFTP.
- Der PHP-Helfer setzt serverseitig `Content-Disposition: attachment`, unterstützt Range-Requests und blockiert abgelaufene, manipulierte oder pfadfremde Download-Links.


## Version 19.0.1.0.16
- Notizbereich pro Video auf der PIN-geschützten Website.
- Jede Notiz speichert Verfasser und Zeitpunkt unveränderlich mit.
- Alle für das Video eingetragenen Personen sehen die Notizen.
- Odoo-Backend-Übersicht „Video-Notizen“.
