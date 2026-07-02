# Groundlift Medienfreigabe — Odoo 19 SH Modul

Version: 19.0.1.0.6

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
