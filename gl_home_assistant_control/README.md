# GROUNDLIFT Home Assistant Steuerung – Odoo 19 SH

Odoo-19-SH-App zur serverseitigen Verbindung mit Home Assistant. Das Modul liest Sensoren/Aktoren, zeigt konfigurierbare PC-Dashboards und Unterseiten, zeichnet Verläufe auf, erlaubt manuelle Steuerung und schaltet Beleuchtung anhand von Groundlift-Veranstaltungen bzw. Kino-Spielzeiten.

## Enthaltene Funktionen

- Verbindung Home Assistant ↔ Odoo über die offizielle Home-Assistant-REST-API.
- Authentifizierung mit **Long-Lived Access Token**; der Token wird nie an den Dashboard-Browser ausgeliefert.
- Automatische Entitätserkennung für u. a. `sensor`, `binary_sensor`, `switch`, `light`, `climate`, `fan`, `number`, `input_number`, `input_boolean`.
- Anzeige von Temperatur, Luftfeuchte, Helligkeit/Lux, Schaltzuständen, Thermostaten, Zu-/Abluft usw., sofern Home Assistant diese als Entitäten bereitstellt.
- Lokaler Verlauf in Odoo mit konfigurierbarer Aufbewahrung; optionaler Import der letzten 24 Stunden aus Home Assistant.
- Responsive Dark-Mode-Dashboard unter `/groundlift/ha/<slug>`.
- Mehrere Dashboards für unterschiedliche PCs/Anwendungsorte.
- **Explizite Auswahl**, welche Entitäten auf der Hauptseite sichtbar sind. Für bestehende Dashboards bleibt der globale Fallback zunächst aktiv; er kann abgeschaltet werden, damit eine leere Auswahl bewusst leer bleibt.
- **Trennung von aktiven Elementen und Sensoren**: Entitäten können automatisch oder manuell als „Aktives Element / Steuerung“ bzw. „Sensor / Messwert“ einsortiert werden.
- **Kompakte Sensordarstellung**, damit Messwerte nicht mehr dieselbe große Karte wie Schalter oder Thermostate belegen müssen.
- **Konfigurierbare Dashboard-Unterseiten** wie „Klima“, „Energie“, „Kino“ oder „Heizung“. Jede Unterseite besitzt eine eigene Entitätsauswahl, URL und Darstellung.
- Gruppierung nach Home-Assistant-Raum oder einer frei definierbaren **Dashboard-Gruppe** je Entität; Gruppierung kann pro Haupt-/Unterseite abgeschaltet werden.
- Statusleiste, Warnungen, Automatik-Zeitfenster, Entity IDs, „zuletzt gesehen“ und Verlaufsdiagramme lassen sich je Haupt-/Unterseite separat ein- oder ausblenden.
- Manuelle Schaltung von Schaltern/Lichtern/Lüftern sowie Sollwertänderung von Thermostaten und Reglern.
- Thermostate verwenden die von Home Assistant gemeldete Schrittweite; ohne Angabe wird **0,5 °C** verwendet.
- Manuelle Übersteuerung der Automatik mit konfigurierbarer Dauer; Button „Automatik“ hebt sie sofort auf.
- Warnungen bei `unavailable`/`unknown` bzw. verschwundenen Entitäten, auf Wunsch zusätzlich per E-Mail.
- Zeitfenster-Cache für Groundlift-Events und Kino – dadurch keine Cinetixx-Abfrage jede Minute.
- **Mehrfachauswahl in Automatikregeln:** Eine Regel kann mehrere Schalter/Lichter gleichzeitig steuern.
- **Mehrere optionale Messsensoren pro Regel:** Sensoren lassen sich mit „alle müssen zutreffen“ oder „mindestens einer muss zutreffen“ verknüpfen; Operator und Grenzwert gelten gemeinsam für die Auswahl.

## Kino-Automatik / Cinetixx – Tagesbetrieb

Die Kino-Automatik wird **tageweise zusammengefasst**:

1. Für jeden lokalen Kalendertag werden alle Cinetixx-Vorstellungen geladen.
2. Beginn des Kino-Zeitfensters = Beginn der **ersten** Vorstellung des Tages.
3. Ende des Kino-Zeitfensters = Ende der **letzten** Vorstellung des Tages.
4. Der in der Automatikregel eingestellte Vorlauf gilt nur vor der ersten Vorstellung.
5. Der Nachlauf gilt nur nach dem Ende der letzten Vorstellung.
6. Zwischen zwei Vorstellungen bleibt das Kino-Zeitfenster durchgehend aktiv.

Beispiel:

- Erste Vorstellung: 14:30 Uhr
- Letzte Vorstellung endet: 22:20 Uhr
- Vorlauf: 60 Minuten
- Nachlauf: 45 Minuten

Dann ist das Automatik-Zeitfenster für das Licht von **13:30 bis 23:05 Uhr** aktiv, auch wenn zwischen einzelnen Vorstellungen längere Pausen liegen.

Vorstellungen ohne gemeldetes Ende verwenden die in den Einstellungen konfigurierte Fallbackdauer.

## Mehrfachauswahl in Automatikregeln

Unter **Gebäudesteuerung → Automatikregeln** können im Feld **Zu schaltende Entitäten** mehrere Aktoren gleichzeitig ausgewählt werden. Eine einzige Regel kann damit beispielsweise Außenbeleuchtung, Girlande und Hausfassade gemeinsam schalten.

Auch **Optionale Messsensoren** sind eine Mehrfachauswahl. Für mehrere Sensoren gibt es zwei Verknüpfungen:

- **Alle Sensoren müssen zutreffen**: jeder verfügbare Messwert muss den gewählten Operator/Grenzwert erfüllen.
- **Mindestens ein Sensor muss zutreffen**: ein erfüllender Sensor reicht aus.

Operator und Grenzwert gelten für alle Sensoren dieser Regel. Bei nicht entscheidbaren Sensorzuständen (`unknown`/`unavailable`) wird sicherheitsorientiert mit einer dreiwertigen Logik gearbeitet: Ist das Ergebnis wegen des fehlenden Sensors tatsächlich offen, wird während eines aktiven Zeitfensters der aktuelle Schaltzustand gehalten statt blind ausgeschaltet.

Beim Update von Version 1.1.0 werden bestehende Einzel-Zielentitäten und Einzel-Sensorbedingungen automatisch in die neuen Mehrfachauswahlfelder übernommen.

## Veranstaltungsautomatik

Das Modul liest die Standardfelder `event.event.date_begin` und `event.event.date_end` aus Odoo Events; bei Odoo-19-Events mit mehreren Slots werden die einzelnen Slotzeiten verwendet. Als storniert markierte Veranstaltungen werden nicht in den Beleuchtungs-Cache übernommen. In den Einstellungen können zusätzlich bestimmte Veranstaltungsphasen ausgewählt werden.

Mehrere Regeln dürfen dasselbe Ziel haben. Das Modul verknüpft sie logisch mit ODER. Dadurch kann dieselbe Außenbeleuchtung sowohl bei Veranstaltungen als auch bei Kino-Spielzeiten aktiv sein, ohne dass eine zweite Regel sie fälschlich ausschaltet.

## Dashboard-Konfiguration

### 1. Entitäten vorbereiten

Unter **Gebäudesteuerung → Entitäten** kann jede Home-Assistant-Entität konfiguriert werden:

- **Raum/Gruppe**: aus Home Assistant übernommen bzw. manuell korrigierbar.
- **Dashboard-Gruppe**: frei definierbare Gruppe, z. B. „Außenklima“, „Energie Eingang“, „Sudhaus Lüftung“.
- **Darstellung im Dashboard**:
  - **Automatisch**: steuerbare Geräte werden als aktive Elemente, andere als Sensoren behandelt.
  - **Aktives Element / Steuerung**: erscheint im Steuerungsbereich.
  - **Sensor / Messwert**: erscheint im Sensorbereich und erhält dort keine Steuerbuttons.
- **Im Dashboard anzeigen**: globale Fallback-Freigabe; wird nur benötigt, wenn ein Dashboard „Globale Dashboard-Entitäten verwenden“ aktiviert hat.

### 2. Hauptseite eines Dashboards konfigurieren

Unter **Gebäudesteuerung → Dashboards**:

- Entitäten für die Hauptseite explizit auswählen.
- Optional „Globale Dashboard-Entitäten verwenden“ aktivieren.
- Steuerung und Sensoren trennen.
- Sensordarstellung „kompakt“ oder „große Karten“ wählen.
- Gruppierung wählen:
  - Dashboard-Gruppe, sonst Raum
  - nur Raum
  - keine Untergruppierung
- Spaltenzahl einstellen.
- Statusleiste, Warnungen und Zeitfenster ein-/ausblenden.
- Verlaufsdiagramme, technische Entity IDs und „zuletzt gesehen“ nur dort einschalten, wo sie tatsächlich benötigt werden.

### 3. Unterseiten anlegen

Im Dashboard-Reiter **Unterseiten** oder über **Gebäudesteuerung → Dashboard-Unterseiten** können eigene Seiten angelegt werden.

Beispiele:

- `Klima` → Temperatur + Luftfeuchte aller Räume
- `Energie` → Leistung, Stromstärke, Spannung, Verbrauch
- `Heizung` → Thermostate und Raumtemperaturen
- `Kino` → nur die für den Kinobetrieb relevanten Schalter/Sensoren

Jede Unterseite besitzt eine eigene URL:

`/groundlift/ha/<dashboard-slug>/<unterseiten-slug>`

und kann ihre Entitäten, Gruppierung und Darstellung unabhängig von der Hauptseite konfigurieren.

## Sehr wichtig bei Odoo.sh + Raspberry Pi

Odoo.sh läuft in der Cloud. Eine lokale Adresse wie `http://homeassistant.local` oder `http://192.168.x.x` ist vom Odoo.sh-Server normalerweise nicht erreichbar. Es wird deshalb eine von Odoo.sh erreichbare, abgesicherte HTTPS-Adresse für Home Assistant benötigt, z. B. eine Home-Assistant-Cloud-Remote-URL oder ein sicher konfigurierter Reverse Proxy/Tunnel.

## Installation / Update

1. Den Ordner `gl_home_assistant_control` in das Odoo.sh-Repository unter `addons/` kopieren bzw. die bestehende Version ersetzen.
2. Commit + Push auf den gewünschten Odoo.sh-Branch.
3. Apps-Liste aktualisieren.
4. Das Modul **GROUNDLIFT Home Assistant Steuerung** aktualisieren.
5. Danach einmal unter **Gebäudesteuerung → Einstellungen** auf **Zeitfenster aktualisieren** klicken, damit vorhandene einzelne Kino-Zeitfenster sofort durch die neuen Tagesfenster ersetzt werden.
6. Dashboard und Unterseiten konfigurieren.

## Cronjobs

- Home-Assistant-Zustände: jede Minute
- Event-/Kino-Zeitfenster: alle 15 Minuten
- Automatik-Auswertung: jede Minute
- Historienbereinigung: täglich

## Sicherheit

- Dashboard-Routen erfordern einen angemeldeten Odoo-Benutzer.
- Anzeige und Steuerung sind getrennte Benutzergruppen.
- Das Dashboard erhält niemals den Home-Assistant-Token.
- Der Token und optionale Proxy-Header sind nur für Home-Assistant-Administratoren in Odoo sichtbar.
- Eine als „Sensor / Messwert“ konfigurierte Entität kann über das Dashboard nicht geschaltet werden, selbst wenn sie technisch steuerbar wäre.
