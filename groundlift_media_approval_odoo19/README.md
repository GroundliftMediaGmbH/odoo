# Groundlift Medienfreigabe für Odoo 19 / Odoo.sh

Version: 19.0.1.0.3

Diese Version behebt den PIN-Zugriffsfehler und nutzt im Backend eine einfache sechsstellige PIN pro Freigabe-Person.

## Wichtige Änderungen in 19.0.1.0.3

- Das Feld `pin_hash` ist nicht mehr gruppenbeschränkt und wird nicht mehr in der Ansicht verwendet.
- Neue einfache PIN-Vergabe über das Feld `6-stellige PIN` auf der Freigabe-Person.
- PIN muss genau sechs Ziffern haben.
- PINs aktiver Personen müssen eindeutig sein.
- Alte, gehashte PINs bleiben als Legacy-Fallback lesbar, damit bestehende Testdaten kein Update blockieren.
- Upload-Snapshot berücksichtigt Personen mit neuer `pin_code`-PIN und alte Legacy-PINs.

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
5. Über `Dateien hochladen` Fotos/Videos hochladen.
6. Externe Personen öffnen `/media-approval` oder `/medienfreigabe` und melden sich nur per PIN an.

## Technischer Hinweis

Die Freigabe-Personen werden beim Upload als fester Snapshot an jede Datei geschrieben. Später hinzugefügte Personen gelten nur für danach hochgeladene Dateien.
