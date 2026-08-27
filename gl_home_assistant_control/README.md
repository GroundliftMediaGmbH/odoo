# GROUNDLIFT Home Assistant Steuerung – Odoo 19 SH

Odoo-19-SH-App zur serverseitigen Verbindung mit Home Assistant. Das Modul liest Sensoren/Aktoren, zeigt mehrere PC-Dashboards, zeichnet Verläufe auf, erlaubt manuelle Steuerung und schaltet Beleuchtung anhand von Groundlift-Veranstaltungen bzw. Kino-Spielzeiten.

## Enthaltene Funktionen

- Verbindung Home Assistant ↔ Odoo über die offizielle Home-Assistant-REST-API.
- Authentifizierung mit **Long-Lived Access Token**; der Token wird nie an den Dashboard-Browser ausgeliefert.
- Automatische Entitätserkennung für u. a. `sensor`, `binary_sensor`, `switch`, `light`, `climate`, `fan`, `number`, `input_number`, `input_boolean`.
- Anzeige von Temperatur, Luftfeuchte, Helligkeit/Lux, Schaltzuständen, Thermostaten, Zu-/Abluft usw., sofern Home Assistant diese als Entitäten bereitstellt.
- Lokaler Verlauf in Odoo mit konfigurierbarer Aufbewahrung; optionaler Import der letzten 24 Stunden aus Home Assistant.
- Responsive Dark-Mode-Dashboard unter `/groundlift/ha/<slug>` mit Diagrammen ohne externe JavaScript-Bibliothek.
- Mehrere Dashboards für unterschiedliche PCs/Anwendungsorte mit jeweils eigener Entitätsauswahl.
- Manuelle Schaltung von Schaltern/Lichtern/Lüftern sowie Sollwertänderung von Thermostaten und Reglern.
- Thermostate verwenden die von Home Assistant gemeldete Schrittweite; ohne Angabe wird **0,5 °C** verwendet.
- Manuelle Übersteuerung der Automatik mit konfigurierbarer Dauer; Button „Automatik“ hebt sie sofort auf.
- Warnungen bei `unavailable`/`unknown` bzw. verschwundenen Entitäten, auf Wunsch zusätzlich per E-Mail. Fällt ein Lux-/Bedingungssensor während eines aktiven Zeitfensters aus, hält die Automatik den aktuellen Lichtzustand statt ungeprüft auszuschalten.
- Warnungen bei Home-Assistant-Verbindungsfehlern, Zeitplanfehlern und fehlgeschlagenen Automatik-Schaltbefehlen.
- Zeitfenster-Cache für Groundlift-Events und Kino – dadurch keine Cinetixx-Abfrage jede Minute.

## Veranstaltungsautomatik

Das Modul liest die Standardfelder `event.event.date_begin` und `event.event.date_end` aus Odoo Events; bei Odoo-19-Events mit mehreren Slots werden die einzelnen Slotzeiten verwendet. Als storniert markierte Veranstaltungen werden nicht in den Beleuchtungs-Cache übernommen. In den Einstellungen können zusätzlich bestimmte Veranstaltungsphasen ausgewählt werden (leer = alle aktiven, nicht stornierten). Pro Automatikregel sind Vor- und Nachlauf konfigurierbar, standardmäßig 60 Minuten.

Beispiel Außenbeleuchtung:

1. Ziel: `switch.aussenbeleuchtung`
2. Quelle: **Groundlift Veranstaltungen**
3. Vorlauf: `60` Minuten
4. Nachlauf: `60` Minuten
5. Sensorbedingung: `sensor.aussen_helligkeit`
6. Operator: `kleiner als`
7. Grenzwert: z. B. `50` Lux

Die Beleuchtung wird dann nur eingeschaltet, wenn ein Event-Zeitfenster aktiv **und** der Außenlichtwert unter dem Grenzwert liegt. Nach Ende des Zeitfensters wird ausgeschaltet.

Mehrere Regeln dürfen dasselbe Ziel haben. Das Modul verknüpft sie logisch mit ODER. Dadurch kann dieselbe Außenbeleuchtung sowohl bei Veranstaltungen als auch bei Kino-Spielzeiten aktiv sein, ohne dass eine zweite Regel sie fälschlich ausschaltet.

## Kino-Automatik / Cinetixx

Dieses Modul hat absichtlich die Abhängigkeit:

`gl_kino_newsletter_nl2go`

Es verwendet dessen vorhandene Cinetixx-Konfiguration und Parser für `SHOW_BEGINNING`/`SHOW_END`. Für Vorstellungen ohne Ende wird die konfigurierbare Fallbackdauer verwendet (standardmäßig 120 Minuten).

Für Kino-Licht wird eine zweite Regel mit Quelle **Kinovorstellungen** und denselben 60 Minuten Vor-/Nachlauf angelegt. Der gleiche Lux-Sensor kann wieder als Bedingung verwendet werden.

## Sehr wichtig bei Odoo.sh + Raspberry Pi

Odoo.sh läuft in der Cloud. Eine lokale Adresse wie

- `http://homeassistant.local`
- `http://192.168.x.x[:Port]`

ist vom Odoo.sh-Server **normalerweise nicht erreichbar**.

Es wird deshalb eine von Odoo.sh erreichbare, abgesicherte HTTPS-Adresse für Home Assistant benötigt, z. B. eine Home-Assistant-Cloud-Remote-URL oder ein sicher konfigurierter Reverse Proxy/Tunnel. Der Home-Assistant-Long-Lived-Token bleibt als API-Authentifizierung erforderlich.

Für vorgeschaltete Dienste unterstützt die App zusätzlich optionale HTTP-Header als JSON, z. B. für Service-Token eines Access-Proxys. Diese Header werden ausschließlich serverseitig gespeichert/verwendet.

## Installation

1. Den Ordner `gl_home_assistant_control` in das Odoo.sh-Repository unter `addons/` kopieren.
2. Sicherstellen, dass `gl_kino_newsletter_nl2go` im gleichen Odoo-System installiert/upgradefähig ist.
3. Commit + Push auf den gewünschten Odoo.sh-Branch.
4. Apps-Liste aktualisieren.
5. **GROUNDLIFT Home Assistant Steuerung** installieren.
6. Benutzergruppen vergeben:
   - **Home Assistant → Anzeige** – Dashboard ansehen
   - **Home Assistant → Steuerung** – zusätzlich manuell schalten
   - **Home Assistant → Administration** – Konfiguration, Entitäten, Regeln

## Erstkonfiguration

Unter **Gebäudesteuerung → Einstellungen**:

1. Erreichbare Home-Assistant-URL eintragen.
2. Long-Lived Access Token eintragen.
3. Ggf. SSL-Prüfung und optionale Proxy-Header konfigurieren.
4. **Verbindung testen**.
5. **Entitäten synchronisieren**.
6. Unter **Entitäten**:
   - Namen/Räume prüfen,
   - Dashboard-Sichtbarkeit festlegen,
   - Steuerbarkeit kontrollieren,
   - Verlauf/Warnungen konfigurieren.
7. Unter **Dashboards** pro PC/Anwendungsfall ein Dashboard anlegen und Entitäten zuordnen.
8. Unter **Automatikregeln** Event- und Kino-Regeln anlegen.
9. **Zeitfenster aktualisieren** und danach **Automatik jetzt prüfen**.
10. Optional **24h Verlauf importieren**.

## Cronjobs

- Home-Assistant-Zustände: jede Minute
- Event-/Kino-Zeitfenster: alle 15 Minuten
- Automatik-Auswertung: jede Minute
- Historienbereinigung: täglich

Die Odoo-Historie schreibt nicht zwingend jede Minute einen Messpunkt. Das Intervall ist standardmäßig 5 Minuten und in den Einstellungen veränderbar.

## Home-Assistant-Services

Die Steuerung verwendet echte Home-Assistant-Services, nicht nur das Setzen eines API-Zustands:

- `switch/light/fan/input_boolean`: `turn_on` / `turn_off`
- `climate`: `set_temperature`
- `number/input_number`: `set_value`

Damit werden die tatsächlichen Zigbee-Geräte über die in Home Assistant konfigurierte Integration angesteuert.

## Sicherheit

- Dashboard-Routen erfordern einen angemeldeten Odoo-Benutzer.
- Anzeige und Steuerung sind getrennte Benutzergruppen.
- Das Dashboard erhält niemals den Home-Assistant-Token.
- Der Token und optionale Proxy-Header sind nur für Home-Assistant-Administratoren in Odoo sichtbar.
- Für extern erreichbaren Home Assistant wird HTTPS dringend empfohlen.

## Hinweis zur ersten Inbetriebnahme

Die App kann nicht wissen, welche konkrete Home-Assistant-Entity-ID bei euch „Außenlicht“, „Zu-/Abluft“, „Thermostat Sudhaus“ usw. ist. Nach der ersten Synchronisierung werden diese Entitäten automatisch eingelesen; anschließend ordnet ihr sie in Odoo einmalig Räumen, Dashboards und Automatikregeln zu.
