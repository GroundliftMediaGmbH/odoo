# GROUNDLIFT Künstler- und Agenturportal – Odoo 19 SH

## Installation

1. Das Verzeichnis `gl_event_artist_portal` vollständig ins Odoo.sh-Addons-Repository legen und nach GitHub pushen.
2. Benötigt die bereits vorhandenen Module `gl_event_guestlist` und `groundlift_graphics` sowie `website` und `mail`.
3. In Odoo Apps aktualisieren, **Groundlift Künstler- & Agenturportal** aktualisieren.
4. Vor der produktiven Verwendung auf Odoo.sh **Staging** testen. Eine E-Mail wird **nicht** beim GitHub-Push aus diesem ZIP heraus verschickt; erst Odoo verarbeitet die Mail nach Installation und Phasenwechsel oder nach Klick auf den Testbutton.

## Ablauf

**Wichtig ab 19.0.2.0.2:** Der nachstehend beschriebene erweiterte Ablauf gilt ausschließlich für Veranstaltungen, die **nach der Installation dieses Updates** neu angelegt werden. Bereits bestehende Veranstaltungen behalten ausschließlich ihr bisheriges Portal für Ticketübersicht, Gästeliste und Abendkasse in der Phase „Angekündigt“. Siehe „Bestandsschutz / Stichtag Modulupdate“ am Ende dieser Datei.


- Veranstaltung wird erstmals nach **Gebucht** verschoben: genau eine Einladung pro Veranstaltung wird in die Odoo-E-Mail-Warteschlange gestellt. Die Einführung ist im Reiter **Info für Band/Agentur** individuell editierbar. Platzhalter: `{event}` und `{portal_url}`. Das Odoo-CRM-Kontaktfeld **Vertrag: Künstler / Agentur** erscheint in diesem Reiter und zusätzlich (sofern per Studio vorhanden) im Reiter **Vertragsdaten**.
- **Staging, Dev und unbekannte Umgebungen**: Versand nur an `julius@groundlift.de` (`[STAGING TEST]` im Betreff); Produktion: an `artist_portal_contract_contact_id.email`. Ein gezielter Testbutton sendet immer nur an Julius. Ohne SMTP-Konfiguration oder bei neutralisiertem Odoo.sh-Staging kann die Warteschlange den Versand nicht ausführen.
- Optional Systemparameter `gl_event_artist_portal.test_mode=1` erzwingt Testmodus; `gl_event_artist_portal.delivery_mode=production` erlaubt Produktivversand, falls `ODOO_STAGE` in eurem Production-Branch fehlt. Hat `ODOO_STAGE` den Wert `staging` oder `dev`, bleibt Testmodus unabhängig von `delivery_mode` erzwungen. Produktionsadresse nur aktivieren, nachdem ihr den Test geprüft habt.
- Button **Einladung erneut senden** für nachträglich hinterlegte Kontakte, ohne den automatischen Einmalversand zu verändern.
- Portal ist in **Gebucht** und **Angekündigt** erreichbar; Gästeliste/Abendkasse bleiben wie bislang ausschließlich in **Angekündigt** verfügbar. Ab Abrechnung/Beendet werden Gästeliste und Uploads gesperrt; stattdessen erscheint der GEMA-Link, sofern hinterlegt.
- Tech-/Hospitality-Rider schreiben direkt in `event.event.x_studio_tech_rider` bzw. `event.event.x_studio_hospitality_rider` (PDF/DOC/DOCX, je max. 20 MB).
- Pro Veranstaltung mehrere Fotos in **1:1**, **Querformat**, **Hochformat** (max. 20 je Format, je 12 MB). Das erste quadratische Foto wird unmittelbar ins Eventbild (`image_1920`, daraus abgeleitet `image_1024`) übernommen.
- Kurzer Pressetext → `x_studio_event_kurzbeschreibung`, langer Pressetext → `description` (Eventbeschreibung). HTML wird escaped, sodass eingesandte Texte keine HTML/Script-Injektion erlauben.
- Sobald eine dieser Textangaben intern in Odoo verändert wird, sperrt das Portal **das jeweilige Textfeld**, nicht zwingend das andere. Sobald das Eventbild intern oder die Grafik bearbeitet wurde, werden **alle Fotos** gesperrt. Die Sperren stehen im Backend und können durch Groundlift bewusst wieder aufgehoben werden.
- Wenn mindestens ein Foto **und beide Pressetexte** vorhanden sind, legt das Portal einen zugeordneten Datensatz `gl.graphics.poster` an und überträgt Bilddaten und Kurzbeschreibung in den Grafikeditor (Quadrat/Querformat auf passende Bildelemente). Hochformate bleiben als eigenständige Bilder in der Pressegalerie.

## Wichtige Grenze: erstes Rendering

**Der vorhandene Grafikeditor rendert ausschließlich im Browser via Canvas.** Dieses Add-on kann deshalb ohne zusätzlichen serverseitigen Renderer **noch kein fertiges Bild/alle Ausspielformate im Hintergrund berechnen**. Die Grafik ist automatisch vorbereitet, der tatsächliche erste Render erfolgt erst beim Öffnen und Speichern im Grafikeditor. Die App verspricht keine bereits gerenderten PNG/JPG-Dateien und überschreibt keine bestehenden, bereits bearbeiteten Grafiken. Für ein vollständig unbeaufsichtigtes erstes Rendering wäre eine gesonderte headless Browser-/serverseitige Renderlösung erforderlich.

## Datenschutz/Sicherheit

- Token-URL pro Veranstaltung; sämtliche Upload-/Lösch-/Bildrouten prüfen Token, Phase und Event-Zugehörigkeit erneut. Kein Zugriff über abweichende Event-/Foto-IDs.
- POST-Formulare nutzen Odoo-CSRF. Uploads werden per Byte-Signatur/Pillow validiert und größenbegrenzt. Nur interne Benutzer besitzen ACLs auf Pressebilder; öffentlich werden Fotos ausschließlich über den Eventtoken ausgeliefert.
- Bestehende Gästelistenregeln/Überbuchungsschutz bleiben erhalten.

## Feldnamen aus den gelieferten Screenshots

`x_studio_tech_rider` · `x_studio_hospitality_rider` · `x_studio_event_kurzbeschreibung` · `image_1024` / Basisbild `image_1920` · `description`. Sollten diese Studio-Felder auf einem anderen Branch anders heißen, bitte vor Installation/Abnahme die tatsächlichen technischen Feldnamen prüfen.


## Update 19.0.2.0.1
- Das quadratische Pressebild (1:1) wird nun als primäres Standardbild in die Grafik-App übernommen. Querformat und Hochformat bleiben zusätzlich formatbezogen verfügbar.


## Update 19.0.2.0.2 – Bestandsschutz / Stichtag Modulupdate

- **Bestehende Odoo-Veranstaltungen** (auch zukünftige Termine und bisherige Portal-Links)
  bleiben im **bisherigen Gästelistenportal**: nur bei `Angekündigt`, mit
  Ticketübersicht, Gästeliste und Abendkasse. Es gibt keine neuen Uploads,
  Pressetexte, Bild-/Grafikübergaben oder automatischen Einladungsmails.
- **Erst nach dem Update neu angelegte Veranstaltungen** (unabhängig vom
  Aufführungsdatum, auch beim Duplizieren) erhalten automatisch den erweiterten
  Portalmodus: bereits ab `Gebucht` mit Uploads / Einladung, ab
  `Angekündigt` zusätzlich Gästeliste und Ticketübersicht.
- Technisch: persistentes `artist_portal_extended_enabled` ist **default=False**
  für sämtliche vorhandenen Datensätze; nur `event.event.create()` setzt es bei
  neu angelegten Events auf True. Keine Datumsvergleiche, rückwirkenden
  Massenschreibungen oder Änderungen an bestehenden Eventdaten.
- Die bestehenden Links, Zugriffstokens und Gästelisteneinträge werden nicht
  gelöscht. Bereits von einer früheren Version importierte Pressebilder und
  Texte werden nicht gelöscht, aber im Bestandsportal nicht mehr angeboten.
- Die Backend-Registerkarte `Info für Band/Agentur` zeigt bei bestehenden
  Events nur den bisherigen Link/QR-Code und Portalstatus. Die zusätzlichen
  Bereiche sind nur bei neu angelegten Events sichtbar.
- **Prüfung nach Modulupdate in Staging:** ein bestehendes `Angekündigt`-Event
  und seinen alten Link öffnen (nur Gästeliste); bestehendes Event von
  `Neu` auf `Gebucht` bewegen (keine Mail); danach ein neues Event anlegen
  und auf `Gebucht` bewegen (Einladung nur an Julius im Testmodus, Medienbereich
  sichtbar); anschließend `Angekündigt` testen (beide Funktionsbereiche).


## Update 19.0.2.0.3 – Pressetext & Odoo-Benachrichtigungen

- Das Portal verwendet für **Pressetext lang** ausschließlich das neue interne Feld
  `artist_portal_press_long` (standardmäßig leer). Die Odoo-Vorlagenbeschreibung
  `description` wird **nicht** mehr in das Formular vorbefüllt.
- Erst wenn ein Künstler einen Langtext eingibt, geht er nach `description`;
  wenn nur der Kurztext gespeichert wird, bleibt die vorhandene Odoo-Beschreibung
  unverändert. Ein bereits eingereichter Langtext kann vom Künstler gelöscht
  werden, solange Groundlift ihn nicht bearbeitet/gesperrt hat.
- Der Automatikstart der Grafik-App verlangt nun ausdrücklich einen vom Künstler
  eingereichten Langtext, ein Bild und eine Kurzbeschreibung; Odoo-Vorlagentext
  alleine zählt nicht als Presseabgabe.
- Nach neu hochgeladenen Pressefotos **oder** eingereichten/geänderten Pressetexten:
  To-do-Aktivität und Live-Benachrichtigung für `event.event.user_id`.
- Techrider: an interne Odoo-Benutzer aus `x_studio_techn_leitung`;
  Hospitality Rider: aus `x_studio_organisation_service`.
  Unterstützt Studio-Felder, die interne `res.users`, deren `res.partner` oder
  `hr.employee` mit `user_id` referenzieren. Nicht zugeordnete Kontakte erhalten
  aus Datenschutzgründen **keine** externe E-Mail; im Serverlog steht ein Hinweis.
- Der Schalter **Odoo-Benachrichtigungen für Portal-Uploads** steht im Backend,
  Reiter „Info für Band/Agentur“. Standardmäßig für neue Events aktiv.
- **Push-Grenze:** Odoo-Toast live bei geöffneter Sitzung und dauerhaftes Odoo-To-do;
  keine Betriebssystem-/Mobil-Pushmeldung bei geschlossenem Browser.
- Bestehende Veranstaltungen behalten den Bestandsschutz aus 19.0.2.0.2.
- Bereits vor 19.0.2.0.3 über das Portal eingereichte Langtexte werden nicht
  automatisch von event.description nach artist_portal_press_long übernommen,
  da sich Vorlagentexte und Künstlerabgaben historisch nicht sicher unterscheiden lassen.


## Update 19.0.2.0.4 – Globale Standardwerte

Unter **Einstellungen → Allgemeine Einstellungen → GROUNDLIFT Künstlerportal** können
Administratoren nun folgende Werte zentral speichern:

- **Standard-E-Mail-Text** der Portal-Einladung inklusive `{event}` und `{portal_url}`.
- **Standard – Technische Leitung** (interner Odoo-Benutzer).
- **Standard – Organisation Service** (interner Odoo-Benutzer).

Die Defaults erscheinen bereits im **Neu anlegen**-Formular und werden **nur beim
erstmaligen Anlegen** einer Veranstaltung in deren individuelle Felder kopiert. Bestehende Veranstaltungen, ihre individuellen
Einladungstexte und Personenzuordnungen werden **nicht rückwirkend** geändert.
Bereits ausdrücklich im Erstellungsformular/über API übermittelte Werte, auch
eine bewusste Leerauswahl, werden nicht durch Standardwerte überschrieben.
Der Einladungstext bleibt im Reiter **Info für Band/Agentur** pro neuem Event
bearbeitbar. Die Platzhalter werden erst beim Versand ersetzt. Ohne `{portal_url}`
wird der persönliche Link weiterhin am Ende der E-Mail angefügt.

Die Standardpersonen werden in die vorhandenen Studio-Felder
`x_studio_techn_leitung` und `x_studio_organisation_service` geschrieben.
Unterstützt werden Many2one-/Many2many-Verknüpfungen zu `res.users`,
`res.partner` oder `hr.employee` (mit zugeordnetem Odoo-Benutzer).
Bei abweichenden Feldtypen / nicht zugeordneten Mitarbeitern wird nichts
Unpassendes eingetragen und der Serverlog nennt den Grund.

**Staging-Prüfung:** Im Einstellungsmenü Text und zwei Mitarbeiter setzen,
neues Event anlegen, im Reiter *Info für Band/Agentur* den Text prüfen,
Techn. Leitung und Organisation Service im Event prüfen, einen individuellen
Text/Mitarbeiter ändern und kontrollieren, dass eine nachfolgende Änderung
an den globalen Standards dieses Event nicht beeinflusst. Ein vor dem Update
angelegtes Event unverändert lassen. Testmail aus Odoo nur an Julius.


## Update 19.0.2.0.5 – Einstellungen unter Odoo 19 repariert

Das mehrzeilige Textfeld `gl_artist_default_introduction` wird nun ausdrücklich
über `get_values()` / `set_values()` in `ir.config_parameter` gespeichert. Odoo
19 erlaubt `config_parameter=` nicht direkt für `fields.Text`; dadurch hatte
das Öffnen der Einstellungen einen RPC_ERROR verursacht. Die beiden auswählbaren
Standardmitarbeiter bleiben als native Many2one-Konfigurationsfelder erhalten.
Das Update greift nicht in bestehende Veranstaltungsdaten ein.


## Update 19.0.2.0.6 – GEMA / selektive Alt-Events / Discuss-Benachrichtigungen

- Im Reiter **Info für Band/Agentur** das neue Feld **GEMA-Link für Künstler/Agentur** befüllen (vollständiges http(s)-URL). In **Abrechnung** und **Beendet** zeigt der bestehende Token-Link ausschließlich den GEMA-Abschnitt. Ohne URL erscheint der Hinweis, dass der Link noch fehlt. Gästeliste und Uploads sind ab Abrechnung gesperrt. Auch bisherige Veranstaltungen können den GEMA-Abschnitt nutzen.
- Jedes Event hat vier separate Freigaben (Bilder, Pressetext, Technical Rider, Hospitality Rider). **Standard** bewahrt das bisherige Verhalten: alte Events aus, neue Events an. **Anzeigen/Ausblenden** überschreibt die Freigabe nur für dieses Event. Alt-Events erhalten keine rückwirkenden Einladungsmails. Freigaben gelten auch serverseitig für alle POST- und Bildrouten. Uploads für Alt-Events bleiben in der gewohnten Phase **Angekündigt**.
- Upload-Benachrichtigungen werden jetzt als **Odoo-Discuss-Posteingangsbenachrichtigungen** mit `mail.message` / `mail.notification` an die jeweils verantwortlichen internen Nutzer gesendet, auch wenn der Nutzer als allgemeine Zustellpräferenz E-Mail hinterlegt hat; es werden für diesen Benachrichtigungstyp **keine SMTP-Mails** und **keine simple_notification-Popups** erzeugt. Die bestehende To-do-Aktivität je Event bleibt erhalten.
- Die zuerst hochgeladene quadratische Presseaufnahme bleibt das Standardbild für die Grafik-App; ansonsten wurde der Grafikeditor nicht verändert.
- **Staging-Prüfung:** Altes Event in Angekündigt: Bereiche einzeln auf Anzeigen stellen, alle nicht aktivierten Bereiche fehlen; im Backend GEMA-Link setzen und auf Abrechnung wechseln: nur GEMA. Beim neu angelegten Event weiterhin alle Medien in Gebucht/Angekündigt, danach ausschließlich GEMA. Upload von Foto/Text/Ridern -> Odoo-Nachrichtenmenü „Benachrichtigungen“ des passenden Mitarbeiters prüfen; kein Popup.


## Update 19.0.2.0.7 – Setliste und Rider-Bestätigungen

- Im bestehenden GEMA-Abschnitt des Künstlerportals (Phasen **Abrechnung**/**Beendet**, auch für Altveranstaltungen) gibt es „Setliste wurde eingereicht“ als erforderliches Häkchen und eine Bestätigungsschaltfläche. Das Setzen ist einmalig; eine wiederholte POST-Anfrage erzeugt **keine zweite Benachrichtigung**. Der Veranstaltungsverantwortliche (`user_id`) erhält dieselbe dauerhafte Odoo-Discuss-Benachrichtigung und To-do-Aktivität wie bei Presse-Uploads (sofern Event-Benachrichtigungen aktiviert sind). Der Status samt Datum ist im Backend sichtbar.
- Backend **Info für Band/Agentur → Rider-Bestätigungen**: getrennte Häkchen für Technical Rider und Hospitality Rider. Sobald Groundlift den jeweiligen **vorliegenden** Rider bestätigt, wird auf dem Künstlerportal „durch Groundlift bestätigt“ angezeigt und eine E-Mail aus der Odoo-Warteschlange an den Vertragskontakt vorbereitet. Ohne entsprechenden Upload oder (in Produktion) ohne E-Mail beim Vertragskontakt wird die Bestätigung mit einer hilfreichen Fehlermeldung zurückgewiesen. Ein ersetzter Rider setzt seine vorherige Bestätigung zurück; erst erneute Bestätigung verschickt wieder eine Mail.
- Unter **Einstellungen → Allgemeine Einstellungen → GROUNDLIFT Künstlerportal** stehen zwei unabhängig bearbeitbare mehrzeilige **globale Bestätigungsmail-Texte**. Platzhalter: `{event}`, `{rider}`, `{portal_url}`. Ist der Portal-Link-Platzhalter nicht vorhanden, hängt das System den Link an. Im Staging gehen E-Mails ausschließlich an `julius@groundlift.de`, nicht an Künstler/Agenturen; eine neutralisierte Odoo-Staging-Datenbank kann den tatsächlichen Versand unterbinden. Die Checkbox-/Benachrichtigungsfunktion bleibt davon unabhängig.
- Die bestehenden Portal-Abschnittsfreigaben für Altveranstaltungen bleiben unverändert. Die Rider-Bestätigung wird während der Upload-Phasen am jeweiligen Rider angezeigt; in „Abrechnung“/„Beendet“ erscheinen bestehende Bestätigungen zusätzlich schreibgeschützt im GEMA-/Setlisten-Abschnitt (keine Rider-Uploads). Bei einer Altveranstaltung mit einzeln freigeschaltetem Rider ist der Vertragskontakt im Backend editierbar, damit die Bestätigungsmail einen Empfänger hat.

**Staging-Test:** bestehende Veranstaltung in Abrechnung öffnen, Setlisten-Häkchen bestätigen und Odoo-Benachrichtigungen bei `Verantwortlich` prüfen; Häkchen erneut POSTen, keine Duplikate. Event mit Tech-/Hospitality-Rider öffnen, im Backend nacheinander bestätigen, Künstlerportalstatus und Mail-Warteschlange an Julius prüfen; Rider erneut hochladen und Status erneut prüfen. Neue globale Mail-Presets speichern und Odoo-Einstellungen erneut öffnen.
