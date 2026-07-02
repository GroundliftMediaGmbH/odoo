# Groundlift Medienfreigabe – Odoo 19 / Odoo.sh

Dieses ZIP enthält ein Odoo-Modul `groundlift_media_approval` plus eine `requirements.txt` für Odoo.sh.

## Funktionen

- Backend-App „Medienfreigabe“
- Hetzner-Verbindung per SFTP, FTP oder FTPS hinterlegbar
- Remote-Unterordner in Odoo erstellbar
- Upload von Fotos/Videos vom PC über Odoo-Backend auf den Hetzner-Server
- PIN-geschützte Website ohne Odoo-Login
- Ordnerauswahl auf der Homepage
- Datei-Liste links, Vorschau rechts
- Foto-/Video-Vorschau über Odoo-Controller
- Buttons „Freigeben“, „Nicht freigeben“, „Download“
- Download erst aktiv, wenn alle beim Upload gültigen Personen freigegeben haben
- Statusfarben:
  - Grün: alle haben freigegeben
  - Orange: noch nicht abgeschlossen
  - Rot: alle haben abgestimmt und mindestens eine Person hat abgelehnt
- Jede Datei speichert beim Upload den damaligen Personen-Kreis als Snapshot
- Später hinzugefügte Personen gelten nur für danach hochgeladene Dateien
- Cron löscht nach 3 Monaten abgelehnte, vollständig bewertete Dateien vom Hetzner-Server

## Installation auf Odoo.sh

1. Den Ordner `groundlift_media_approval` in dein Odoo.sh GitHub-Repository kopieren.
2. Die Datei `requirements.txt` in die Root-Ebene des Repositories kopieren. Wichtig: Odoo.sh installiert Python-Abhängigkeiten normalerweise aus der Root-`requirements.txt`.
3. Committen und auf Odoo.sh deployen.
4. In Odoo die App-Liste aktualisieren.
5. App „Groundlift Medienfreigabe“ installieren.
6. Dem zuständigen internen Benutzer die Gruppe „Medienfreigabe Manager“ geben.

## Einrichtung

1. Medienfreigabe → Konfiguration → Hetzner Verbindungen
   - Protokoll wählen: SFTP empfohlen
   - Host, Port, Benutzer, Passwort und Basisordner hinterlegen
   - „Verbindung testen“ klicken
2. Medienfreigabe → Konfiguration → Personen / PINs
   - Personen anlegen
   - Je Person eine eindeutige PIN mit 4 bis 12 Ziffern setzen
3. Medienfreigabe → Freigabe → Unterordner
   - Unterordner anlegen
   - „Remote-Ordner anlegen“ klicken
   - „Dateien hochladen“ klicken und Medien auswählen
4. Externe Freigabeseite öffnen:
   - `/media-approval`
   - alternativ deutsch: `/medienfreigabe`

## Wichtige Hinweise

- Für SFTP nutzt das Modul `paramiko`; deshalb liegt die Root-`requirements.txt` bei.
- Die Dateien werden nicht dauerhaft in Odoo gespeichert, wenn im Upload-Wizard „Lokale Odoo-Anhänge nach Transfer löschen“ aktiv bleibt.
- Die Vorschau und Downloads laufen über Odoo. Sehr große Videos können je nach Odoo.sh-Timeout und Dateigröße langsamer laden.
- PINs werden gehasht gespeichert, nicht im Klartext.
- FTP ist technisch möglich, SFTP ist für Hetzner Storage Box in der Regel die bessere Wahl.


## Patch 19.0.1.0.1

- Odoo-19-Security-Struktur korrigiert: `res.groups.category_id` durch `res.groups.privilege` + `res.groups.privilege_id` ersetzt.
- Dadurch wird der Installationsfehler `Invalid field 'category_id' in 'res.groups'` behoben.
