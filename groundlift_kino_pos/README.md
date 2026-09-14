# Kino POS – Odoo 19 SH

## Funktionen

- Gerätegebundene öffentliche Kino-POS-Homepage mit derselben kryptografischen Browserbindung wie `gl_home_assistant_control` (P-256, IndexedDB, signierte JSON-RPC-Aufrufe, HttpOnly-Cookie).
- Liest offene `helpdesk.ticket`-Datensätze, deren Beschreibung `request_type: cinema_reservation_request` enthält.
- Übersetzt die Fonio-Felder auf der POS-Seite in NAME, TELEFONNUMMER, FILMTITEL, PLÄTZE, EMPFANGSBESTÄTIGUNG ERWÜNSCHT, BESTÄTIGEN VIA und ZUSAMMENFASSUNG.
- Verschiebt Reservierungen per Button in die konfigurierte Phase „Gelöst“; danach verschwinden sie aus der POS-Übersicht.
- „Was gibt's zu tun“-Liste mit Frequenzen: jede Kinoschicht, 1× wöchentlich, 2× monatlich und 1× monatlich. Erledigungen werden serverseitig gespeichert.
- Begrüßung aus `gl.kino.shift.slot.employee_id` für das jeweils aktuelle Datum; automatischer Refresh sorgt auch nach einem Tageswechsel für den richtigen Namen.
- Konfigurierbarer Sprung auf ein Home-Assistant-Dashboard; optional direkt über einen bereits im selben Browser gebundenen HA-Gerätezugang.
- Lokaler Geldzähler für alle Euro-Münzen und -Scheine von 1 Cent bis 500 Euro, inklusive +/−, Eingabefeld, Summe und Reset. Der aktuelle Zählstand bleibt im Browser gespeichert, bis Reset gedrückt wird.

## Nach der Installation

1. Unter **Kino POS → Einstellungen** die Helpdesk-Phase „Gelöst“ und das gewünschte Home-Assistant-Dashboard auswählen. Für einen öffentlichen Kassenrechner zusätzlich den passenden HA-Gerätezugang auswählen und diesen einmalig im selben Browser binden.
2. Unter **Kino POS → Was gibt's zu tun** die gewünschten Aufgaben und Frequenzen anlegen.
3. Unter **Kino POS → Gerätezugänge** einen Kassenrechner anlegen.
4. Den dort erzeugten Einrichtungslink direkt auf dem Kassenrechner öffnen und **Diesen Rechner jetzt binden** anklicken.
5. Anschließend kann die im Gerätezugang angezeigte **Kino POS Homepage** dauerhaft auf diesem Rechner verwendet werden.

## Abhängigkeiten

- `helpdesk`
- `hr`
- `website`
- `groundlift_kino_shift_signup`
- `gl_home_assistant_control`

## Interner Odoo-Zugang

Zusätzlich zur Computerbindung kann jeder angemeldete interne Odoo-Benutzer das Dashboard direkt über **Kino POS → Live Dashboard** oder `/kino-pos` öffnen. Für diesen Zugang ist keine Gerätebindung nötig. Die gerätegebundene Variante unter `/kino-pos/device/...` bleibt für öffentliche Kassen-PCs unverändert bestehen.

## 19.0.1.2.0 – Backend als App-Einstieg

- Ein Klick auf die App **Kino POS** öffnet wieder das Odoo-Backend (Einstellungen) statt sofort das Live-Dashboard.
- Im Backend steht oben der Button **Dashboard öffnen** zur Verfügung.
- Das Dashboard bleibt zusätzlich als eigener Menüpunkt erreichbar.
- Angemeldete Odoo-Benutzer benötigen weiterhin keine Gerätebindung für das interne Dashboard.

## Reservierungsphasen

Unter **Kino POS → Backend / Einstellungen → Kundentickets** kann über **„Reservierungen aus Phasen“** festgelegt werden, aus welchen Helpdesk-Phasen Kinoreservierungen auf dem Dashboard erscheinen. Mehrere Phasen können gleichzeitig ausgewählt werden. Ist keine Phase ausgewählt, gilt aus Gründen der Rückwärtskompatibilität weiterhin: alle noch nicht gelösten Kinoreservierungen anzeigen.
