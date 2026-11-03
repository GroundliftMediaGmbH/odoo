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
- Stromkosten-Prüfung: alle 5 Minuten (fachliches Intervall einstellbar)
- Historienbereinigung: täglich

## Sicherheit

- Dashboard-Routen erfordern einen angemeldeten Odoo-Benutzer.
- Anzeige und Steuerung sind getrennte Benutzergruppen.
- Das Dashboard erhält niemals den Home-Assistant-Token.
- Der Token und optionale Proxy-Header sind nur für Home-Assistant-Administratoren in Odoo sichtbar.
- Eine als „Sensor / Messwert“ konfigurierte Entität kann über das Dashboard nicht geschaltet werden, selbst wenn sie technisch steuerbar wäre.


## Version 1.1.2
- Automatik-Zeitfenster im Frontend als kompakte Liste statt Kacheln.
- Eine Hauptzeile pro Kalendertag und geschalteter Entität mit effektiver AN-/AUS-Zeit (inkl. Vor-/Nachlauf).
- Hauptzeilen sind aufklappbar; darunter erscheinen die beitragenden Kino-/Event-Zeitfenster einzeln.
- Überlappende Regeln werden zu Schaltphasen zusammengeführt; getrennte Phasen werden kenntlich gemacht.


## Neu in 19.0.1.1.3 – tägliche Zeitprogramme

Automatikregeln können zusätzlich die Zeitquelle **„Tägliches Zeitprogramm“** verwenden. Damit lassen sich Geräte unabhängig von Kino- oder Odoo-Veranstaltungen zu festen Uhrzeiten schalten, z. B. eine Lüftung täglich von 08:00 bis 08:30.

- Ein- und Ausschaltzeit werden als lokale Uhrzeit in der unter Einstellungen konfigurierten Zeitzone ausgewertet.
- Standardmäßig sind Montag bis Sonntag aktiv; einzelne Wochentage können abgewählt werden.
- Mehrere Ziel-Entitäten und die optionalen Mehrfach-Sensorbedingungen funktionieren auch für Zeitprogramme.
- Mehrere Laufzeiten pro Tag werden durch mehrere Regeln für dasselbe Gerät abgebildet. Die Automatik verknüpft aktive Regeln logisch mit ODER.
- Zeitfenster über Mitternacht werden unterstützt, z. B. 23:00 bis 01:00.
- Die geplanten Zeitprogramme erscheinen zusammen mit Kino- und Event-Automatiken in der aufklappbaren Automatik-Liste des Live-Dashboards.

## Projekt-Automationen (v1.1.4)

Automatikregeln können jetzt direkt an ein Odoo-Projekt gebunden werden. In der Regel wird das Projekt ausgewählt und der für die Gebäudesteuerung relevante Projektbeginn sowie das Projektende manuell eingetragen. Vor- und Nachlauf funktionieren wie bei Kino und Veranstaltungen. Projektzeiträume dürfen über Mitternacht laufen; das Ende wird dann mit dem Folgedatum eingetragen.

Unter **Gebäudesteuerung → Projekt-Vorlagen** lassen sich wiederverwendbare Vorlagen anlegen. Eine Vorlage speichert die zu schaltenden Entitäten, Vor-/Nachlauf sowie optionale Sensorbedingungen. Beim Auswählen der Vorlage in einer Projektregel werden diese Werte kopiert und können anschließend projektspezifisch verändert werden. Bestehende Regeln werden durch spätere Änderungen an der Vorlage nicht rückwirkend verändert.

Alle Automatikquellen werden pro Zielentität logisch ODER-verknüpft. Endet eine Projektregel, während für dieselbe Entität noch Kino-, Veranstaltungs- oder Zeitautomatik aktiv ist, bleibt das Gerät eingeschaltet und wird erst ausgeschaltet, wenn keine Regel mehr EIN verlangt.


## Wetter- und Sonnenautomation (v1.2.0)

- Drei virtuelle optionale Messsensoren: **Wetter: Sonnenaufgang**, **Wetter: Sonnenuntergang** und **Wetter: Bewölkung**.
- Wetter-Ort in den Einstellungen frei änderbar; Standard: **82266 Inning am Ammersee, Deutschland**.
- Der Ort wird automatisch geokodiert, die ermittelten Koordinaten werden in Odoo gespeichert.
- Sonnenaufgang/-untergang und stündliche Bewölkung werden über Open-Meteo geladen und lokal gecacht.
- Bei Auswahl von Sonnenaufgang oder Sonnenuntergang wird die Sonnenzeit zu einem dynamischen Einschalt-Anker. Die tatsächliche Einschaltzeit ist die spätere Zeit aus normalem Regel-Vorlauf und Sonnen-Trigger.
- Wird zusätzlich **Wetter: Bewölkung** ausgewählt, können getrennte Vorläufe für wenig Bewölkung und Bewölkung konfiguriert werden, z. B. 60 bzw. 90 Minuten vor Sonnenuntergang. Der Bewölkungsgrenzwert ist je Regel frei einstellbar.
- Die Bewölkungsentscheidung verwendet die Prognose zur Sonnenzeit. Sobald der Sonnen-Trigger für ein konkretes Betriebsfenster erreicht wurde, wird er bis zum Ende dieses Fensters eingerastet; spätere Prognoseänderungen können das Licht dadurch nicht wieder ausschalten.
- Bei fehlenden Wetterdaten wird innerhalb eines grundsätzlich aktiven Zeitfensters der aktuelle Schaltzustand gehalten, statt blind zu schalten.

Hinweis: Die Wetterdaten stammen standardmäßig von Open-Meteo. Für den konkreten betrieblichen Einsatz sind deren jeweils aktuelle Nutzungsbedingungen zu beachten.

## Stromkosten je Veranstaltung (v1.3.0)

Die App kann mehrere Home-Assistant-Stromzähler gemeinsam auswerten und die daraus entstehenden Stromkosten direkt in Odoo-Veranstaltungsfelder schreiben.

### Einrichtung

Unter **Gebäudesteuerung → Einstellungen → Stromkosten**:

1. **Stromkosten-Ermittlung aktiv** einschalten.
2. Einen oder mehrere Home-Assistant-Sensoren als **Stromzähler-Entitäten** auswählen. Mehrere Sensoren werden addiert.
3. Den **Strompreis je kWh** eintragen.
4. Messfenster festlegen. Standard ist **07:00 Uhr am Veranstaltungstag bis 05:00 Uhr am Folgetag**.
5. Anzahl der Veranstaltungen für den SOLL-Mittelwert einstellen; Standard: **20**.
6. Technische Odoo-Felder festlegen. Standard:
   - IST: `x_studio_event_kalk_ist_sonstige_kosten`
   - SOLL: `x_studio_event_kalk_soll_sonstige_kosten`

Die Feldnamen können später z. B. auf eigene Stromkostenfelder umgestellt werden. Die App prüft vor dem Schreiben, ob das konfigurierte Feld auf `event.event` existiert und numerisch ist.

### Verbrauchslogik

- Unterstützte Energieeinheiten: **Wh, kWh, MWh**.
- Unterstützte Leistungseinheiten: **W, kW, MW**. Bei Leistungssensoren wird der Verbrauch über die Zeit integriert; echte Energiezähler werden für die Abrechnung empfohlen.
- Mehrere ausgewählte Zähler werden zu einem Gesamtverbrauch addiert.
- Gibt es an einem Kalendertag genau eine Veranstaltung, erhält sie die gesamten Kosten des Messfensters.
- Gibt es mehrere Veranstaltungen mit Beginn am selben Kalendertag, werden die Gesamtkosten gleichmäßig durch die Zahl dieser Veranstaltungen geteilt.
- Während das Messfenster läuft, wird der IST-Wert regelmäßig aktualisiert. Nach dem konfigurierten Messende am Folgetag wird der Tageswert als abgeschlossen gespeichert.
- Ist ein ausgewählter Zähler während einer laufenden Berechnung nicht erreichbar oder fehlt ausreichende Home-Assistant-Historie, wird kein unvollständiger Null-/Teilwert in das Event geschrieben; stattdessen entsteht eine Warnung.

### SOLL-Wert

Der SOLL-Wert wird aus den Stromkosten der letzten abgeschlossenen Veranstaltungen gebildet. Bei mehreren Veranstaltungen an einem Tag zählt jede Veranstaltung mit ihrem anteiligen Tageswert als eigene Stichprobe. Solange weniger als die konfigurierte Zahl historischer Veranstaltungen vorliegt, wird aus den verfügbaren abgeschlossenen Veranstaltungen gemittelt.

Mit **„Stromkosten-Historie neu berechnen“** können nach der Ersteinrichtung die Tage hinter den letzten N Veranstaltungen aus der Home-Assistant-Historie nachberechnet werden. Das ist insbesondere sinnvoll, damit der SOLL-Mittelwert sofort mit historischen Daten gefüllt werden kann.

### Cronjob

Der technische Stromkosten-Cron läuft alle 5 Minuten. Das in den Einstellungen gewählte Aktualisierungsintervall (Standard 15 Minuten) bestimmt, wann tatsächlich neu gerechnet wird. Abgeschlossene Tage werden im Regelbetrieb nicht erneut von Home Assistant geladen; fehlende Abschlusswerte der letzten Tage werden automatisch nachgeholt.

## Fix in 19.0.1.3.1 – Dashboard-Entitäten bei bestehenden Installationen

- Repariert bestehende Dashboards, bei denen nach einem Modul-Update eine leere explizite Entitätsauswahl zusammen mit einem unbeabsichtigt deaktivierten globalen Fallback dazu führte, dass keine Entitäten mehr angezeigt wurden.
- Der Reparaturschritt wird über einen eigenen Migrationsmarker nur einmal ausgeführt und überschreibt spätere bewusste Einstellungen nicht erneut.
- Im Dashboard-Formular zeigt das Feld **„Entitäten auf der Hauptseite“** jetzt die tatsächlich wirksamen Entitäten: entweder die explizit gewählte Liste oder – bei leerer Auswahl und aktivem globalen Fallback – die global freigegebenen Dashboard-Entitäten.
- Die eigentliche Auswahl- und Dashboard-Logik bleibt unverändert: eine explizite Auswahl hat weiterhin Vorrang; der globale Fallback greift nur bei leerer expliziter Auswahl.


## Fix in 19.0.1.3.2 – Entitätsauswahl im Dashboard-Formular sichtbar und bearbeitbar

- Das Backend verwendet für „Entitäten auf der Hauptseite“ wieder direkt das Standard-Odoo-Many2many-Feld `entity_ids`. Dadurch ist die Auswahl zuverlässig anklickbar und bearbeitbar.
- Dashboards, die bislang den globalen Fallback verwendet haben, spiegeln die tatsächlich im Live-Dashboard angezeigten Entitäten automatisch in dieses Feld. Dadurch sind die vorhandenen Entitäten sofort als Tags sichtbar.
- Der Spiegelmodus bleibt dynamisch: Änderungen an „Im Dashboard anzeigen“ bzw. am Aktiv-Status einer Entität werden nachgeführt.
- Sobald die Entitätsauswahl im Dashboard manuell geändert wird, wird sie wie bisher zu einer expliziten Auswahl. Wird bei aktivem globalem Fallback alles entfernt, wird wieder die globale Auswahl verwendet.
- Das Live-Dashboard-Verhalten bleibt damit unverändert; behoben wird ausschließlich die leere/nicht bedienbare Auswahl im Odoo-Backend.

## Externer, gerätegebundener Dashboard-Zugriff (ab 19.0.1.4.0)

Unter **Gebäudesteuerung → Gerätezugänge** kann ein externer Zugriff ohne Odoo-Benutzerkonto angelegt werden.

- Pro Gerätezugang wird ein Dashboard festgelegt.
- Hauptseite und erlaubte Unterseiten sind separat freigebbar.
- Der Gerätezugang kann nur lesend oder mit Steuerungsrecht konfiguriert werden.
- Odoo erzeugt einen 24 Stunden gültigen Einrichtungslink.
- Dieser Link wird **einmalig direkt auf dem Zielrechner** geöffnet.
- Der Browser erzeugt dort einen P-256-ECDSA-Schlüssel. Der private Schlüssel wird als nicht exportierbarer WebCrypto-Key im lokalen Browserprofil gespeichert; Odoo speichert nur den öffentlichen Schlüssel.
- Zusätzlich wird ein HttpOnly-/Secure-Gerätecookie gesetzt. Cookie oder URL allein reichen nicht aus: Datenabrufe und Steuerbefehle müssen mit dem lokalen privaten Geräteschlüssel signiert sein.
- Mit **Gerät neu binden** wird die bisherige Bindung sofort ungültig und ein neuer Einrichtungslink erzeugt.
- Wird das Browserprofil gelöscht/gewechselt, muss das Gerät erneut gebunden werden.

Hinweis: Dies ist eine starke Browserprofil-/Gerätebindung ohne übertragbares Passwort. Für eine explizite TPM-/Secure-Enclave-Hardwareattestierung wäre zusätzlich WebAuthn/Windows Hello/Touch ID erforderlich.


## Version 19.0.1.4.1

- Geräte-Einrichtungslinks verwenden im Odoo-Webclient nun bevorzugt den Host der aktuellen HTTP-Anfrage.
- Dadurch funktionieren Einrichtungslinks auch auf Odoo.sh-Staging-Datenbanken zuverlässig, selbst wenn `web.base.url` noch auf Produktion zeigt oder eingefroren ist.
- Außerhalb einer HTTP-Anfrage bleibt `web.base.url` der sichere Fallback.

## Version 19.0.1.4.2

- Verlaufsdiagramme mit beschrifteter Y-Achse (Messwerte inklusive Einheit)
- X-Achse zeigt Beginn, Mitte und Ende des tatsächlichen Zeitverlaufs
- Bei 6/24 Stunden werden Uhrzeiten, bei 7/30 Tagen Datumswerte angezeigt
- Diagrammlinie wird jetzt anhand der tatsächlichen Zeitstempel positioniert
- Responsive Reduktion der X-Beschriftung bei sehr schmalen Karten

## Version 19.0.1.6.0 – Hysterese, Klima-Gruppen und Behaglichkeitsdiagramm

- Automatikregeln unterstützen neben dem einfachen Grenzwert jetzt **Einschaltschwelle + Hysterese**. Bei „kleiner als“, 250 Lux Einschaltschwelle und 50 Lux Hysterese wird unter 250 Lux eingeschaltet und erst ab 300 Lux wieder ausgeschaltet. Nach Ende des Zeitfensters wird der Hysterese-Zustand zurückgesetzt.
- Projekt-Vorlagen übernehmen die neue Grenzwert-Logik vollständig.
- Unter **Einstellungen → Klima & Behaglichkeit** können Temperatur- und Luftfeuchte-Entitäten manuell zu einem Raum/Messpunkt gruppiert werden. Sind beide Entitäten auf einer Dashboard-Seite sichtbar, werden sie als **eine gemeinsame Klima-Kachel** dargestellt.
- Die Schimmelrisiko-Prüfung kann pro Klima-Gruppe aktiviert werden; die bisherige Sensor-Auswahl bleibt aus Kompatibilitätsgründen zusätzlich erhalten.
- Hauptseiten und Unterseiten können ein responsives **Behaglichkeitsdiagramm** aktivieren. Ausgewählte Klima-Gruppen erscheinen darin als beschriftete Punkte im Temperatur-/Feuchte-Koordinatensystem; die Punktfarben entsprechen den Kachelfarben Behaglich / noch behaglich / außerhalb / Schimmelrisiko.
- Das Diagramm verwendet getrennte Layout-Geometrien für Hoch- und Querformat, damit Achsen, Beschriftungen und Punkte korrekt skalieren.

## Version 19.0.1.7.0 – Taupunkt-Trocknung und Projekt-Raumautomation

### Taupunkt-Trocknung

Unter **Gebäudesteuerung → Automatikregeln** steht die neue Quelle **„Taupunkt-Trocknung“** zur Verfügung.

- Außen- und Innen-Taupunktsensor werden direkt ausgewählt.
- Die Trocknung startet, wenn `Taupunkt innen − Taupunkt außen` mindestens die konfigurierte Differenz erreicht.
- Es können mehrere Lüftungs-/Schaltentitäten als Ziel ausgewählt werden.
- Mindest- und Maximallaufzeit werden über einen persistenten Regelzustand eingehalten.
- Nach Erreichen der Maximallaufzeit bleibt der Trocknungszyklus gesperrt, bis die Taupunktdifferenz einmal wieder unter die Einschaltschwelle gefallen ist.
- Veranstaltungs-, Kino- und Projektbetrieb können einzeln als Blocker aktiviert werden. Ein aktiver Betriebsblocker beendet die Trocknung sofort, auch wenn die Mindestlaufzeit noch nicht erreicht ist.
- Bei nicht verfügbaren Taupunktsensoren wird während eines laufenden Zyklus der aktuelle Schaltzustand gehalten; die Maximallaufzeit bleibt dennoch wirksam.

### Projekt-App / Räume

`project.project` erhält vier neue Felder:

- **Startzeit**
- **Endzeit**
- **Räume** (Mehrfachauswahl: Kino 1, Kino 2, Theater, Lounge, Podcaststudio)
- **Gebäude-Automation**

Bei aktivierter Gebäude-Automation werden die Projektzeiten direkt in den HA-Zeitfenster-Cache gespiegelt. Änderungen an Zeiten, Räumen, Projektname, Aktivstatus oder Checkbox werden unmittelbar nach dem Speichern nachgeführt.

Die Raumlogik ist:

- **Kino 1 / Kino 2** → zählt für bestehende Regeln mit Quelle **Kinovorstellungen** wie Kinobetrieb.
- **Theater** → zählt für bestehende Regeln mit Quelle **Groundlift Veranstaltungen** wie Veranstaltungsbetrieb.
- **Lounge** → neue Regelquelle **Projekt Lounge**.
- **Podcaststudio** → neue Regelquelle **Projekt Podcaststudio**.

Damit können Lounge und Podcaststudio jeweils eigene Automatikregeln mit eigenen Zielgeräten, Vor-/Nachläufen und optionalen Sensorbedingungen erhalten, während Kino und Theater die bereits vorhandenen Automatikregeln wiederverwenden.

## 19.0.1.8.0 – Raumthermostate / gemeinsame Heizungspumpe

- Neue Modelle **Heizsysteme** und **Raumthermostate**.
- Ein Heizsystem besitzt eine gemeinsame Pumpen-Entität; die Pumpe wird nur angefordert, wenn mindestens eine aktive Zone Wärmebedarf hat.
- Pro Zone: Ist-Temperatursensor, Heizkreis-/Thermostat-Relais, optionale Lüftung, Grundtemperatur, Hysterese und Dashboard-Schrittweite.
- Die optionale Lüftung wird bei Heizbedarf als zusätzliche EIN-Anforderung in die bestehende OR-Automatik aufgenommen. Event-/Kino-/Taupunktregeln können sie deshalb weiterhin eingeschaltet halten.
- Solltemperaturprofile können mit Event-, Kino- und Projekt-Zeitfenstern verbunden werden. Raumfilter (Kino 1, Kino 2, Theater, Lounge, Podcaststudio), Vorlauf und Nachlauf sind möglich.
- Kinofenster bleiben global wie bisher vorhanden; zusätzlich werden, sofern Cinetixx den Saal liefert, raumbezogene Fenster für Kino 1/2 erzeugt.
- Dashboards und Unterseiten können ausgewählte Raumthermostate als Soll-/Ist-Kachel mit +/- Steuerung anzeigen. Standard-Schrittweite: 0,5 °C. Eine manuelle Änderung nutzt die globale Dauer für manuelle Übersteuerungen und kann mit „Automatik“ beendet werden.

Nach dem Update einmal **Zeitfenster aktualisieren**, damit bestehende Kino-/Projekt-Caches die neuen Raumcodes erhalten.
