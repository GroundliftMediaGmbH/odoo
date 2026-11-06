# Groundlift – Weiterleitung abgelaufener Veranstaltungslinks

Odoo 19.sh | `gl_past_event_redirect` | Version `19.0.1.0.1`

## Warum das Modul nötig ist

In eurer Produktivversion von `groundlift_event_sync` wird eine Veranstaltung
am Tag nach ihrem Ende **ab 06:00 Uhr (Europe/Berlin)** von der externen
Eventübersicht entfernt. Die Veranstaltung wechselt in **Abrechnung** und
`website_published` wird auf `False` gesetzt.

Odoo beantwortet anschließend den bisherigen Eventlink ggf. mit **404**.
Das neue Modul fängt genau diese URLs **vor Odoos Prüfung des Zugriffs
auf unveröffentlichte Event-Datensätze** ab und liefert eine echte serverseitige
**HTTP-301-Weiterleitung** nach:

`https://groundlift.de/public-events.php`

### Betroffene URLs (Beispiele)

- `/event/mein-konzert-123`
- `/event/mein-konzert-123/register`
- `/event/mein-konzert-123/page/agenda`
- Auch numerische Event-URLs, früher verwendete Slugs und sprachpräfixierte
  Odoo-URLs funktionieren, solange der Event-Datensatz **noch existiert**.

### Nur dann wird weitergeleitet

1. Es handelt sich um einen öffentlichen Seitenaufruf mit **GET/HEAD**.
2. Das zugehörige Event ist in Odoo **nicht mehr veröffentlicht**.
3. Die Groundlift-Ablaufzeit wurde erreicht **oder** das Event ist bereits
   in **Abrechnung/Beendet**.
4. Es gehört zur aufgerufenen Odoo-Website (oder besitzt keine explizite
   Websitezuordnung).

**Unverändert bleiben:** aktuelle und zukünftige öffentliche Events, noch
nicht veröffentlichte zukünftige Events, Eventübersicht (`/event`), Buchung,
Checkout, POST/JSON-RPC, Registrierungsbestätigungen, Künstlerportal, Odoo
Backend, Website-Bearbeitungsmodus. Es wird **nichts** an euren Events, deren
Phasen, den bestehenden Redirect-Modulen oder Cronjobs verändert.

**Wichtig:** Eine **gelöschte** (physisch entfernte) Veranstaltung lässt sich
nicht mehr sicher einer Event-ID zuordnen; die Weiterleitung gilt für weiterhin
vorhandene, auch archivierte Datensätze. Bitte vergangene Events in Odoo
behalten statt löschen.

## Installation in Odoo.sh

1. Den Ordner `gl_past_event_redirect` direkt in die oberste Ebene eures
   Odoo-Custom-Addon-Repositories kopieren (auf gleicher Ebene wie
   `groundlift_event_sync` und `groundlift_event_redirect`).
2. Committen und zunächst auf **Staging** pushen.
3. Unter **Apps** → **App-Liste aktualisieren** nach
   `Groundlift` oder `gl_past_event_redirect` suchen (Filter **Apps** ggf.
   entfernen) und installieren.
4. In einem privaten Browserfenster prüfen:
   - Altes Event: HTTP **301** → `https://groundlift.de/public-events.php`
   - Noch angekündigtes Event: normale Eventseite/Registrierung
   - `/event` → wie bisher euer separates Übersichts-Redirect-Modul
   - Checkout und Ticketbuchung bleiben unverändert.
5. Erst nach erfolgreichem Test nach **Production** übernehmen.

Auf Staging verweist der Redirect absichtlich ebenfalls auf die **Live**-
Groundlift-Übersicht. Das Modul verändert die SFTP-Exports nicht.

## Hinweise zu SEO und Browsercache

HTTP **301** signalisiert Suchmaschinen eine dauerhafte Weiterleitung und ist
für dauerhaft abgelaufene Event-URLs passend. Browser können 301-Antworten
zwischenspeichern. Deshalb bitte für Tests ein Inkognito-Fenster oder
`curl -I` benutzen. Google entscheidet selbst, wie lange frühere
Suchergebnisse angezeigt werden. Ein Redirect ist **keine Garantie**, dass
bereits indexierte Eventseiten weiter unter ihrem alten Titel sichtbar bleiben.

## Technischer Ansatz

- Erweitert ausschließlich `ir.http._pre_dispatch`.
- Prüft nur die drei offiziellen Odoo-19-Website-Event-Seitenrouten.
- Verwendet `groundlift_event_sync`-Methoden `_groundlift_is_due_for_billing`
  und `_groundlift_is_billing_stage`, statt eine zweite Zeit-/Phasenlogik
  einzuführen.
- Keine neuen Datenbankfelder, Scheduler, Abhängigkeiten von externen
  Python-Paketen oder Anpassungen vorhandener Module.

## Hotfix 19.0.1.0.1: ungültige Browser-Sprachcodes

Ein Besucher kann im Session-Kontext eine Sprache wie `de_AT` oder `es_ES`
mitbringen, die für die aktuelle Odoo-Website nicht aktiviert ist. Der
Redirect-Hook untersucht Event-Daten bereits vor Odoos normaler
Sprachvalidierung und konnte so `Invalid language code` auslösen, auch für
aktive Veranstaltungen.

Jetzt wird **ausschließlich auf den relevanten Eventseiten** die von Odoo
beim URL-Routing bereits ermittelte, gültige `request.lang.code` in den
Request-Kontext übernommen, bevor das Modul Event-Felder liest.

Die Weiterleitung bleibt unverändert: abgelaufene, unveröffentlichte
Events → HTTP 301; aktuelle Events → Standard-Odoo; sonstige Routen
und Checkout-Aktionen → unverändert. Keine Datenbankmigration nötig.

Nach Installation/Upgrade bitte testen:

- `/event/pulse-12/register` mit frischem privaten Browserfenster
- Aktuelle vs. abgelaufene Veranstaltungslinks
- Website-Editor (Iframe), Ticketwahl und Checkout
- Website-Sprachen und Besucher mit `de_AT` bzw. `es_ES` als Browserlocale
