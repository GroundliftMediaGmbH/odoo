# Groundlift AI Video Teaser – Odoo 19 SH

Automatisierte 20-Sekunden-Eventteaser aus Odoo Events mit OpenAI, Runway, ElevenLabs und Creatomate.

## Pipeline

1. Odoo liest Eventdaten und priorisierte Assets.
2. OpenAI erzeugt strukturiert Voiceover, Hook, CTA, Musikrichtung und Szenenplan.
3. ElevenLabs rendert Voiceover und optional ein 20-Sekunden-Musikbett.
4. Runway Gen-4.5 animiert ausgewählte Bilder bzw. erzeugt fehlende B-Roll.
5. Creatomate rendert 16:9 und 9:16 mit deterministischen Texten, Logo und Groundlift-Outro.
6. Die fertigen Videos liegen in Odoo zur Vorschau und Freigabe. Bei Freigabe kann ein Webhook an die bestehende Social-Automation gesendet werden.

## Installation

Den Ordner `groundlift_ai_video_teaser` in das Odoo-SH-GitHub-Repository unter den Custom-Addons legen, committen/pushen, im gewünschten Branch Apps aktualisieren und **Groundlift AI Video Teaser** installieren.

Abhängigkeiten: `event`, `website_event`, `mail`. Python verwendet ausschließlich Bibliotheken, die in Odoo bereits vorhanden sind (`requests`).

## Konfiguration

Unter **Einstellungen → Groundlift AI Video**:

- OpenAI API-Key, Modell und Reasoning-Stufe
- Runway API-Key, Modell, maximale KI-Clips und optionale separate 9:16-Erzeugung
- ElevenLabs API-Key, Voice-ID, TTS-Modell, Musikmodell und Musiklautstärke
- Creatomate API-Key sowie optional je eine Master-Template-ID für 16:9 und 9:16
- Groundlift Brandname, Claim, CTA, Footer, Ortsphrase, Hook-Template und Farben
- Odoo-Feldzuordnung für Kurzbeschreibung, Kategorie, Ticket-URL und Eventbild
- optionaler Freigabe-Webhook für die bestehende Social-Automation

### Empfohlene Hook-Klammer

`Am {date} {location} …`

OpenAI ersetzt Datum und Ort natürlich im deutschen Voiceover. Das finale Logo-/CTA-Outro bleibt deterministisch und wird nicht durch ein Bildmodell generiert.

## Event-Workflow

Im Event erscheint der Tab **AI Video**.

1. Assets prüfen/hinzufügen. Echte Videos bekommen die höchste Priorität.
2. **Neuen 20s-Teaser anlegen**.
3. Style und Ausgabeformate wählen.
4. **Teaser generieren**.
5. Die Odoo-Cron verarbeitet die Jobkette schrittweise.
6. Nach dem Rendering beide Formate in Odoo prüfen.
7. **Freigeben**. Die URLs stehen dann auch direkt am Event zur Verfügung.

## Asset-Priorität

`echtes Video → KI-Bewegung aus vorhandenem Bild → statisches Bild → generische KI-B-Roll`

Bei einem Bild-Prompt wird Runway ausdrücklich angewiesen, Identität/Gesicht nicht zu verändern und keinen Text oder Logos zu erfinden.

## Creatomate: zwei Betriebsarten

### 1. Eingebautes RenderScript

Wenn **Templates verwenden** deaktiviert ist oder keine Template-ID vorliegt, baut die App selbst ein vollständiges RenderScript. Das reicht für einen sofortigen Funktionstest.

### 2. Groundlift Mastertemplates – empfohlen

Für die endgültige CI zwei Creatomate-Templates anlegen. Folgende Elementnamen werden automatisch befüllt:

- `Event-Title`
- `Event-Date`
- `Hook`
- `CTA`
- `Footer`
- `Brand`
- `Claim`
- `Logo`
- `Voiceover`
- `Music`
- `Scene-1` bis `Scene-5`
- `Scene-1-Headline` bis `Scene-5-Headline`
- `Scene-1-Subline` bis `Scene-5-Subline`

So kann das Motion Design komplett im Creatomate-Editor gestaltet werden, während Odoo nur die Inhalte ersetzt.

## Öffentliche Medien-URLs

Runway und Creatomate müssen Odoo-Uploads per HTTPS abrufen können. `web.base.url` muss deshalb auf eine von außen erreichbare HTTPS-Domain zeigen. Die App veröffentlicht Medien über lange zufällige Tokens und nicht über frei erratbare Dateipfade.

Runway-Ausgaben werden nach Fertigstellung sofort nach Odoo kopiert, damit temporäre Provider-URLs später nicht auslaufen. Finale Creatomate-Videos werden standardmäßig ebenfalls in Odoo gespeichert.

## Social-Automation

Bei Freigabe eines Videos kann die App einen JSON-POST an den konfigurierten Webhook senden:

```json
{
  "event_id": 123,
  "event_name": "Beispiel",
  "job_id": 456,
  "state": "approved",
  "video_16_9_url": "https://...",
  "video_9_16_url": "https://...",
  "approved_at": "..."
}
```

Zusätzlich stehen am Event die Felder `gl_video_teaser_16_9_url` und `gl_video_teaser_9_16_url` zur Verfügung, sodass ein bestehendes Social-Modul diese direkt lesen kann.

## Hinweise für Staging

Auf einer Odoo-SH-Staging-Domain mit vorgeschaltetem Login/HTTP-Schutz können externe KI-Dienste die Asset-URLs eventuell nicht abrufen. Dann entweder eine öffentlich erreichbare Testdomain verwenden oder die Assets als externe HTTPS-URLs eintragen.

## Technische Validierung

Das Paket wurde statisch auf Python-Syntax und XML-Wohlgeformtheit geprüft. Ein echter Install-/Render-Test benötigt eine laufende Odoo-19-SH-Datenbank plus die vier Provider-Zugänge.

## 19.0.1.0.1
- Odoo-19-Kompatibilitätsfix für die Search-View `gl.video.teaser.job.search`: Das `group`-Element enthält keine in Odoo 19 unzulässigen `expand`-/`string`-Attribute mehr.


## 19.0.1.0.2
- Eigener Menüpunkt **AI Video → Einstellungen** hinzugefügt.
- Dedizierte Konfigurationsseite für OpenAI, Runway, ElevenLabs, Creatomate, Groundlift-CI und Odoo/Social-Integration.
- Einstellungen bleiben zusätzlich in den allgemeinen Odoo-Einstellungen verfügbar.
- Deutsche, lesbare Feldbezeichnungen ergänzt.
