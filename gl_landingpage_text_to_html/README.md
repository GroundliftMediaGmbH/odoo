# Landingpage Text_to_HTML — Groundlift / Odoo 19 SH

## Fix 19.0.1.2.0: Fett-/Link-Formatierung von Backend zur Odoo-Eventseite

Fehler in 1.1: Die Synchronisierung zur **nativen** Odoo-Webseitenbeschreibung
`event.event.description` wurde zusammen mit dem optionalen Studio-Klartextfeld
vollständig übersprungen, sobald dessen technischer Name nicht eindeutig erkannt
wurde. Zudem verhinderte eine strikte Textvergleichslogik bei unterschiedlichen
HTML-Absatzformaten das erstmalige automatische Verknüpfen.

Die Version 1.2 koppelt das bestehende Rich-Text-Feld
`event.event.gl_landingpage_html` mit dem nativen HTML-Feld
`event.event.description` **unabhängig davon**, ob das Studio-Quellfeld erkannt
wird. Bei einem reinen Fettschrift-Wechsel wird weiterhin das HTML mit
`<strong>...</strong>` übernommen. Das alte Studio-Feld wird weder umbenannt
noch im Datentyp geändert. Bestehende HTML-Formatierungen bleiben beim Upgrade
erhalten.

Wenn sich die bisherige native Webseitenbeschreibung INHALTLICH vom
Groundlift-HTML unterscheidet, wird sie aus Sicherheitsgründen nicht
automatisch überschrieben. In der Veranstaltung im Reiter **Landingpage HTML**
steht dafür nun immer (sofern HTML vorhanden) die Aktion
**„HTML jetzt auf Odoo-Webseite übernehmen“** bereit. Die vorherige native
Beschreibung wird vor dem ersten Ersetzen für Administratoren gesichert.

### Installation

1. Das **vollständige Verzeichnis** `gl_landingpage_text_to_html` aus dem ZIP
   über das bestehende Verzeichnis im GitHub-Repository kopieren.
2. Staging-Branch pushen und grünen Odoo.sh-Build abwarten.
3. Odoo: Apps → App-Liste aktualisieren → **Landingpage Text_to_HTML** →
   **Aktualisieren (Upgrade)**. Ein bloßer Git-Push lädt die XML-/Migrationsdaten
   nicht notwendigerweise neu.
4. Veranstaltung Nr. **60** im Backend öffnen → Reiter **Landingpage HTML**.
   Die Zeichenfolge `Charmante Erzählkunst, die berührt` muss im HTML-Feld
   tatsächlich fett formatiert sein. **Website-Status** kontrollieren.
5. Wenn der Status nicht „HTML und native Odoo-Webseitenbeschreibung sind
   identisch“ lautet: den Button **HTML jetzt auf Odoo-Webseite übernehmen**
   drücken. Der Button ist absichtlich AUCH bei bereits „verbundenen“
   Datensätzen verfügbar, um auseinander gelaufene Inhalte reparieren zu können.
6. Mit **Zur Website** die wirkliche Odoo-Eventseite öffnen, Browser neu laden
   (bei Bedarf Strg+F5) und prüfen. Die Backend-URL
   `/odoo/events/60/website` ist nicht zwingend die öffentlich gerenderte
   Veranstaltungsvorlage.
7. Website → **Bearbeiten** → markierten Text fett formatieren → **Speichern**;
   danach im Backend prüfen, ob die Änderung im HTML-Feld übernommen wurde.

### Kontrollstelle für die native Odoo-Webseitenbeschreibung

Im technischen Feld `event.event.description` steht nach dem Abgleich
beispielsweise:

```html
<p><strong>Charmante Erzählkunst, die berührt</strong></p>
```

Die Ausgabe als HTML in der Standard-Eventvorlage erfolgt über `t-field`.
Sichtbares `&lt;strong&gt;` würde auf einen separaten Renderer hinweisen, der HTML
nochmals escaped. Fehlt `<strong>` im Seitenquelltext vollständig, verwendet
die konkrete Seite höchstwahrscheinlich ein anderes Feld oder ein überschreibendes
QWeb-/Studio-Template.

### Grenzen / wenn die Seite nach dem Upgrade weiterhin keine Fettung zeigt

Der genannte Odoo.sh-Link ist ein **anmeldepflichtiger Backend-Link** und kann
von außen nicht untersucht werden. Die Modulansicht erbt die Standardvorlage
`website_event.event_description_full`. Wurde die betroffene Detailseite
bei Groundlift in einer **eigenen Website-/Studio-Ansicht** umgesetzt, die
weiterhin `x_studio_…` (Klartext) statt `event.description` oder
`event.gl_landingpage_html` rendert, kann dieses Modul deren individuelle
XPath-Position nicht verlässlich erraten. In diesem Fall ist der **XML-Quelltext
der aktiven Website-Ansicht** erforderlich; bitte keinesfalls eine automatische
Manipulation aller gerenderten Seiten per JavaScript als Ersatz einsetzen.

Die externe, PHP-gehostete Seite `groundlift.de` ist davon zu unterscheiden:
Ihr PHP-Template muss weiterhin bewusst den HTML-Endpunkt aus diesem Modul
aufrufen; ein Odoo-Modul kann keine externe PHP-Datei überschreiben.

### Weitere technische Details

- Zwei Eingänge: HTML im Backend und direkt die native Beschreibung im
  Odoo-Webeditor. Das bestehende Studio-Textfeld bleibt als Klartext erhalten.
- Änderung des alten Studio-Feldes: erzeugt wie bisher HTML aus Klartext neu;
  bestehende Formatierung kann durch diese **ausdrückliche** Bearbeitung verloren
  gehen.
- Quellfeld ist nicht eindeutig: Website-HTML-Sync arbeitet trotzdem, nur
  Rückschreiben des Klartextes bleibt deaktiviert (fail closed).
- Der Migrationslauf 19.0.1.2.0 füllt **nur leere** Rich-Text-Felder aus Klartext
  und verknüpft native Website-Felder nur bei Leere oder Textgleichheit.
- Es gibt keinen Eingriff in bestehende andere Event-Apps oder den technischen
  Namen bzw. Datentyp des Studio-Feldes.
- Weitere Endpunkt- und Sicherungsdetails stehen im Vorgängermodul 1.1;
  Controller und Sicherungsfeld bleiben in dieser ZIP vollständig erhalten.
