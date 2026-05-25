# Groundlift CleverReach Event Newsletter für Odoo 19 SH

Dieses Modul erzeugt aus Odoo-Veranstaltungen automatisch HTML-Newsletter für CleverReach.

## Funktionsumfang

1. Sobald eine Veranstaltung im Odoo-Veranstaltungsmodul in die Phase **„Angekündigt“** verschoben wird, legt das Modul sie in eine Warteschlange.
2. Am nächsten Morgen ab der konfigurierten lokalen Uhrzeit, standardmäßig 06:00 Uhr, wird aus allen neuen angekündigten Veranstaltungen ein Newsletter erzeugt.
3. Die Newsletter-HTML-Vorlage ist in Odoo austauschbar. Die Standardvorlage enthält den Platzhalter `{{EVENTS_BLOCK}}`.
4. Für neue Eventnewsletter gilt ein Mindestabstand von 7 Tagen.
5. Der Watchdog verhindert innerhalb der Odoo-geplanten Newsletter mehr als einen Versandtermin pro Kalendertag.
6. CleverReach wird nicht mehr als Terminierungs-System verwendet: Odoo plant den Versand und ruft CleverReach erst zum fälligen Zeitpunkt zum Sofortversand auf.
7. Geplante Newsletter können über den Button **Sofort versenden** manuell sofort ausgelöst werden.
8. Alle 14 Tage erzeugt das Modul einen Newsletter mit den nächsten Veranstaltungen.
7. Bei mehreren Führungen wird nur die Führung mit der niedrigsten Teilnehmerzahl angezeigt; zusätzlich wird der Hinweis „Wir freuen uns auf Ihren Besuch unserer anderen Führungen!“ eingefügt.
8. CleverReach-Listen können importiert und global als Empfängerliste gewählt werden.
10. Jeder geplante Newsletter wird zusätzlich als `calendar.event` in Odoo eingetragen.

## Installation in Odoo SH

### Variante A: über GitHub/Odoo SH

1. ZIP entpacken.
2. Den Ordner `gl_cleverreach_newsletter` in dein Odoo-SH-Repository unter `custom_addons/` oder direkt in den Addons-Pfad legen.
3. Committen und auf den gewünschten Branch pushen.
4. In Odoo Apps-Liste aktualisieren.
5. Nach **Groundlift CleverReach Event Newsletter** suchen und installieren.

### Variante B: manuell in einer Entwicklungsumgebung

1. ZIP entpacken.
2. Ordner in den Addons-Pfad kopieren.
3. Odoo neu starten.
4. Apps aktualisieren.
5. Modul installieren.

## CleverReach REST API für Dummies einrichten

### 1. OAuth-App in CleverReach erstellen

1. In CleverReach einloggen.
2. Zu **Account / Mein Account → Schnittstellen / Interfaces → REST API** gehen.
3. Neue OAuth-App erstellen.
4. REST API Version 3 verwenden.
5. Client ID und Client Secret kopieren.
6. Für dieses Modul reicht der OAuth-Flow **Client Credentials**, weil Odoo mit eurem eigenen CleverReach-Konto arbeitet.

### 2. Modul in Odoo konfigurieren

1. In Odoo zu **CleverReach Newsletter → Einstellungen** gehen.
2. Neue Konfiguration anlegen oder bestehende öffnen.
3. Client ID und Client Secret eintragen.
4. Absenderdaten eintragen:
   - Absendername: z. B. `Groundlift`
   - Absender-E-Mail: z. B. `info@groundlift.de`
   - Reply-To: z. B. `info@groundlift.de`
5. Auf **Verbindung testen** klicken.
6. Danach auf **Listen importieren** klicken.
7. Im Feld **Globale CleverReach-Empfängerliste** die gewünschte Liste auswählen.
8. Prüfen, ob die Phase in Odoo exakt **Angekündigt** heißt. Falls anders: Feld **announced_stage_name** anpassen.
9. Falls euer Eventbild nicht `image_1920`, sondern z. B. `x_studio_website_header` ist, im Feld **image_field_name** entsprechend ändern.
10. Konfiguration aktivieren.

## Vorlage austauschen

1. Zu **CleverReach Newsletter → Newsletter-Vorlagen** gehen.
2. Eine neue Vorlage anlegen oder die Standardvorlage öffnen.
3. HTML-Datei hochladen oder HTML direkt im Quelltextfeld einfügen.
4. Wichtig: Die Vorlage sollte den Platzhalter `{{EVENTS_BLOCK}}` enthalten.
5. Optional möglich:
   - `{{NEWSLETTER_HEADING}}`
   - `{{PREHEADER}}`
6. In den Einstellungen die gewünschte Vorlage auswählen.

Wenn eine hochgeladene CleverReach-Vorlage die Überschrift hart codiert enthält, ersetzt das Modul zusätzlich automatisch `UNSERE KOMMENDEN VERANSTALTUNGEN` durch die jeweilige Newsletter-Überschrift.

## Testablauf vor Livebetrieb

1. Konfiguration zunächst aktiv lassen, aber testweise eine interne Empfängerliste in CleverReach verwenden.
2. Ein Testevent in Odoo in die Phase **Angekündigt** verschieben.
3. Zu **CleverReach Newsletter → Angekündigte Events** gehen und prüfen, ob es in der Warteschlange steht.
4. In der Konfiguration **Neue Events jetzt prüfen** klicken.
5. In **Newsletter-Aufträge** den erzeugten Newsletter öffnen.
6. HTML prüfen.
7. Kalendereintrag prüfen.
8. In CleverReach prüfen, ob das Mailing als vorbereitet/Entwurf erscheint. Der Versandtermin bleibt in Odoo.
9. Danach erst die echte Empfängerliste auswählen.

## Wichtige Hinweise

- Die CleverReach API hat mit `setup_v2` Änderungen im neuen Editor. Das Modul versucht mehrere API-Payload-Varianten automatisch. Falls CleverReach bei eurem Account eine abweichende Payload verlangt, wird der vollständige Fehler im Newsletter-Auftrag gespeichert.
- CleverReach REST v3 verwendet für das tatsächliche Senden den Endpoint `POST /mailings/{id}/release`. Dieser Endpoint kann je nach CleverReach-App eine Sonderberechtigung beziehungsweise einen passenden Scope erfordern. Das Modul verwendet bewusst keinen `/send`-Endpoint, weil dieser für Mailings nicht dokumentiert ist.
- Das Modul nutzt CleverReach nicht mehr für geplanten Versand (`release` mit Zukunftszeitpunkt), sondern plant in Odoo. Ein Cronjob prüft alle 5 Minuten fällige Newsletter und löst dann den Sofortversand aus. Dadurch wird der API-Fehler `Forbidden: invalid scope` beim terminierten Release vermieden.
- Auf Odoo SH sollte das Python-Paket `requests` bereits verfügbar sein.
- Der Odoo-Server speichert Datumswerte in UTC. Das Modul rechnet über `timezone_name`, standardmäßig `Europe/Berlin`, in lokale Termine um.
- Der Watchdog schützt die vom Modul geplanten Newsletter. Fremde CleverReach-Mailings außerhalb von Odoo können nur dann sicher berücksichtigt werden, wenn deren geplante Versandzeiten über die CleverReach-API eindeutig geliefert werden.

## Relevante Felder für Groundlift

- Eventphase: `stage_id.name == "Angekündigt"`
- Kurzbeschreibung: bevorzugt `x_studio_event_kurzbeschreibung`, dann `subtitle`, dann `description`
- Eventbild: standardmäßig `image_1920`, ggf. auf `x_studio_website_header` ändern
- Ticketlink: versucht `x_studio_ticket_link`, `x_studio_event_ticketlink`, dann `website_url`
