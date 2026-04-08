# Groundlift Event Sync für Odoo SH 19

Dieses Modul tut drei Dinge:

1. Sobald eine Veranstaltung in die Odoo-Stufe **Announced / Angekündigt** geschoben wird, wird die externe Groundlift-Eventliste neu exportiert.
2. Sobald eine angekündigte Veranstaltung abgelaufen ist, verschwindet sie **am Folgetag ab 06:00 Uhr** aus dem Export.
3. Gleichzeitig wird sie automatisch in die Odoo-Stufe **Abrechnung** verschoben. Wenn diese Stufe noch nicht existiert, legt das Modul sie selbst an.

## Was exportiert wird

Das Modul exportiert zwei Dateien per SFTP auf Hetzner:

- `events-public-snippet.html` → SEO-freundlicher HTML-Snippet mit echten Event-Karten
- `events-cache.json` → JSON-Fallback / Debug-Datei

## Wichtiger Hinweis zu Odoo.sh

Odoo dokumentiert selbst, dass `ir.cron` auf Odoo.sh **nicht sekundengenau** läuft und generell nur auf **Best-Effort-Basis** ausgeführt wird. Erwartet also bitte nicht exakt 06:00:00, sondern eher **ca. 06:00 bis 06:05**. Deshalb läuft der Cron alle 5 Minuten. Das ist auf Odoo.sh der sinnvolle Weg.

## Manuell anzulegende Systemparameter

Die folgenden Werte bitte in **Einstellungen → Technisch → Parameter → Systemparameter** anlegen:

- `groundlift_event_sync.enabled` = `True`
- `groundlift_event_sync.timezone` = `Europe/Berlin`
- `groundlift_event_sync.expire_hour` = `6`
- `groundlift_event_sync.sftp_host` = `BEISPIELSERVER`
- `groundlift_event_sync.sftp_port` = `BEISPIELPORT`
- `groundlift_event_sync.sftp_username` = `BEISPIELBENUTZERNAME`
- `groundlift_event_sync.sftp_password` = `BEISPIELPASSWORT`
- `groundlift_event_sync.remote_snippet_path` = `/public_html/includes/events-public-snippet.html`
- `groundlift_event_sync.remote_json_path` = `/public_html/events-cache.json`
- `groundlift_event_sync.booked_stage_aliases` = `Booked|Gebucht`
- `groundlift_event_sync.announced_stage_aliases` = `Announced|Angekündigt`
- `groundlift_event_sync.billing_stage_aliases` = `Abrechnung|Billing`

## Python-Abhängigkeit

Im Root eures Custom-Repositories braucht ihr zusätzlich eine `requirements.txt` mit:

```txt
paramiko>=3.4,<4
```

## Felder auf der Veranstaltung

Das Modul ergänzt jede Veranstaltung um einen Tab **Groundlift Website** mit:

- Auf Groundlift-Website anzeigen
- Externes Eventbild
- Externe Ticket-URL
- Kategorie
- Filterkategorie
- Venue-Text
- Export-Reihenfolge
- Nutzung des bestehenden Studio-Felds `x_studio_event_kurzbeschreibung` als Kurzbeschreibung auf der Event-Kachel (zwischen Beginn und Überschrift)

## SEO-Empfehlung

Nicht mehr per JavaScript im Browser nachladen, sondern auf Hetzner **serverseitig** den exportierten HTML-Snippet in die Seite einbinden. Dafür gibt es in diesem Paket eine vorbereitete `public-events.php`.

