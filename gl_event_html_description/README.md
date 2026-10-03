# Groundlift Event HTML Description – Odoo 19

Dieses Modul fügt im Veranstaltungs-Backend den Tab **Website HTML** hinzu.

## Funktionsweise

- Bestehende Veranstaltungsbeschreibungen werden bei der Installation in das HTML-Codefeld übernommen.
- Änderungen im Tab **Website HTML** werden direkt mit Odoos Standardfeld `event.event.description` synchronisiert.
- Die öffentliche Eventseite bleibt vollständig bei Odoos Standard-QWeb-Template und zeigt dadurch den gespeicherten HTML-Inhalt an.
- Änderungen, die über Odoos Website-Editor oder andere Standardwege am Feld `description` vorgenommen werden, werden zurück in das HTML-Codefeld gespiegelt.
- Es gibt bewusst **keine** Vererbung von `website_event.event_description_full`. Damit hängt das Modul nicht von der konkreten HTML-Struktur der Odoo-19-Websitevorlage ab.

## Installation

1. Ordner `gl_event_html_description` in das Custom-Addons-Repository legen.
2. In Odoo die App-Liste aktualisieren.
3. **Groundlift Event HTML Description** installieren.
4. Veranstaltung öffnen → Tab **Website HTML**.

Version: `19.0.1.1.0`
