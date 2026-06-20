# Groundlift Event Social Automation

Version: 19.0.1.0.17

Dieses Odoo-19-SH-Modul erzeugt automatisch bearbeitbare Social-Marketing-Posts aus Veranstaltungen.

## Hauptfunktionen

- Trigger: Veranstaltung erreicht die konfigurierbare Phase `Angekündigt`.
- Erstpost am Folgetag zur konfigurierten Uhrzeit, aber spätestens mit konfigurierbarem Mindestabstand vor der Veranstaltung; Standard: mindestens 7 Tage vorher.
- Reminder-Post vor der Veranstaltung.
- Eventtag-Post am Veranstaltungstag.
- Ausverkauft-Post mit Anpassung/Entfernung künftiger Werbeposts.
- Nachbericht-Post, wenn die Veranstaltung die konfigurierbare Abschlussphase erreicht.
- Alle Texte/Headlines sind in der App konfigurierbar; Event-Headlines können zusätzlich per ChatGPT API variantenreich generiert werden.
- Button `Alle Events laden`: erzeugt Posts für alle bereits angekündigten künftigen Veranstaltungen sowie wöchentliche Werbeposts und Lückenfüller im Planungshorizont.
- Kollisionsschutz: pro Kalendertag wird nur ein automatisch erzeugter Groundlift-Post geplant.
- Prioritäten: Eventtag/Ausverkauft/Nachbericht/Reminder haben Vorrang vor Werbeposts; Werbeposts/Lückenfüller haben Vorrang vor Erstankündigungen. Erstankündigungen werden rechtzeitig nachgeholt, solange die Deadline eingehalten werden kann.
- ChatGPT/OpenAI API kann automatisch zusätzliche, veranstaltungsbezogene Hashtags und abwechslungsreiche Headlines erzeugen.
- Wöchentliche Werbeposts: Standardmäßig wird pro Woche ein werbender Post aus Homepage-Bild + Homepage-Kontext geplant, sofern an diesem Tag kein höher priorisierter Eventpost liegt.
- Optionale zusätzliche Lückenfüller-Posts: Wenn in einem Zeitraum keine Eventposts geplant sind, wird ein werbender Post aus Homepage-Bild + Homepage-Kontext erzeugt.

## Bildlogik

Für Eventposts wird ausschließlich `event.event.x_studio_website_header` verwendet.
Es gibt keinen Fallback auf andere Bildfelder.

Lückenfüller-Posts verwenden Bilder von der konfigurierten Homepage, standardmäßig `https://www.groundlift.de`.

## Konfiguration

Nach Installation:

1. Event Social Automation → Einstellungen öffnen.
2. Facebook-/Instagram-Social-Accounts auswählen.
3. OpenAI API Key hinterlegen, falls KI-Hashtags/Lückenfüller genutzt werden sollen.
4. Textbausteine prüfen.
5. Freigabe-Automatik anfangs deaktiviert lassen.
6. Optional: Lückenfüller-Posts aktivieren.

## OpenAI / ChatGPT API

Die App nutzt serverseitig die Chat Completions API unter `https://api.openai.com/v1/chat/completions`.
Ohne API Key läuft das Modul weiter, nutzt dann aber nur lokale/standardisierte Hashtags und Fallback-Texte.

## Hinweise

- Social Posts bleiben normale `social.post`-Datensätze und können in Odoo Social Marketing bearbeitet werden.
- Bei aktivierter Freigabe-Automatik werden Posts direkt in Odoo geplant.
- Wenn manuelle Freigabe aktiv ist, bleiben Posts als Entwurf/Freigabe erforderlich stehen.
- Bitte zuerst auf Staging installieren und testen.


## Änderungen in 19.0.1.0.5

- Erstankündigungen werden nicht mehr über die Deadline `Veranstaltungsdatum minus X Tage` hinaus verschoben. Standard: 7 Tage.
- Neuer wöchentlicher Werbepost mit eigenem Wochentag, Uhrzeit und Planungshorizont.
- Hashtag-Logik filtert unpassende Ticket-/Stehplatz-Hashtags und verwendet #livemusik/#konzert nur bei erkennbarem Musikbezug.
- OpenAI-Prompt für Hashtags wurde auf eventbezogene, nicht generische Hashtags verschärft.


## Änderungen in 19.0.1.0.6

- Event-Headlines werden optional per ChatGPT API erzeugt; die bisherigen konfigurierbaren Überschriften bleiben Fallback.
- Der Ticketlink steht bei Event-Werbeposts direkt unter der Überschrift.
- `Alle Events laden` erzeugt nun zusätzlich wöchentliche Werbeposts und Lückenfüller im Planungshorizont.
- Werbeposts und Lückenfüller haben Vorrang vor Erstankündigungen; Erstankündigungen werden innerhalb der Deadline nachgeholt.
- Hashtag-Kontext filtert interne Ticket-/Produktkategorien stärker, damit z. B. Kabarettabende keine Stehplatz-/Ticket-Hashtags erhalten.


## Änderungen in 19.0.1.0.7

- Ticketlink steht jetzt technisch als eigener Zeilenumbruch direkt unter der Überschrift, ohne Eventtitel/Datum dazwischen.
- Homepage-/Bild-Kontext für wöchentliche Werbeposts und Lückenfüller wird stärker bereinigt: Bilddateinamen, HTML-Attribute, CSS-Klassen, URLs und abgeschnittene Fragmente werden entfernt.
- Wöchentliche Werbeposts haben ein zusätzliches Sicherheitsnetz: Falls in den nächsten 7 Tagen noch kein wöchentlicher Werbepost existiert, wird die nächste passende Gelegenheit innerhalb dieses Fensters gesucht.
- Die Wochenlogik berücksichtigt jetzt auch den heutigen Tag, wenn die konfigurierte Uhrzeit noch nicht vorbei ist.


## 19.0.1.0.8

- Groundlift-Freigabe löst keine native Sofortveröffentlichung mehr aus.
- Native Social-Marketing-Aktionen wie `action_post` werden für zukünftige automatisch erzeugte Groundlift-Posts abgefangen und auf geplante Veröffentlichung gesetzt.
- Buttontexte wurden klarer benannt: Groundlift freigeben & geplant lassen.


## 19.0.1.0.9

- API-Headlines werden stärker randomisiert: Das Modul fordert mehrere Varianten an, arbeitet mit höherer Temperatur und vermeidet zuletzt verwendete Headlines sowie häufige Einstiege wie „Erlebe“/„Entdecke“.
- Eventbeschreibung aus `x_studio_html_field_eventbeschreibung` behält sinnvolle Absätze. Falls die HTML-Beschreibung zu einem einzigen Absatz zusammenfällt, setzt das Modul automatisch einen Absatz nach einem kurzen Teaser/Satz.
- Ticketlink bleibt direkt unter der Headline.


## Version 19.0.1.0.11
- Synchronisiert `social.post.media_ids` strikt mit den Medien der ausgewählten Social Accounts.
- Behebt den Odoo-Fehler `KeyError` in `_compute_live_posts_by_media`.
- `media_ids` wird nicht mehr fälschlich als Bild-/Attachment-Feld behandelt.
- Repariert beim Modulupdate automatisch bestehende Groundlift-Posts und bietet zusätzlich den Button „Social Posts reparieren“.


## Einzelne Plattform direkt erneut posten

Auf dem normalen Social-Post-Formular stehen zwei zusätzliche Aktionen bereit:

- **Direkt erneut auf Instagram posten**
- **Direkt erneut auf Facebook posten**

Die Aktion erzeugt bewusst eine separate Kopie des Beitrags, die ausschließlich das
gewählte Plattformkonto enthält, und löst danach Odoos native Sofortveröffentlichung
aus. Dadurch wird beispielsweise bei einem erfolgreichen Facebook-Post und einem
fehlgeschlagenen Instagram-Post nur Instagram erneut angesprochen; Facebook wird
nicht doppelt veröffentlicht.

Der Wiederholungs-Post erhält einen Verweis auf den ursprünglichen Social-Post und
wird nicht von der Event-Planungsautomatik erneut verschoben oder verarbeitet.


## Änderungen in 19.0.1.0.16

- Odoo.sh-Build-Bereinigung: alle verbliebenen Bild-API-/Generative-Fill-Methoden wurden entfernt.
- ZIPs werden ohne `__pycache__` erzeugt.


## Änderungen in 19.0.1.0.17

- Hotfix für Odoo.sh/OwlError: `openai_image_model` wird als deaktiviertes Kompatibilitätsfeld beibehalten, damit stale Views aus älteren Builds nicht mehr crashen.
- `gl_adjust_image_generative_fill` wird ebenfalls nur noch als deaktiviertes Kompatibilitätsfeld beibehalten.
- Generatives Füllen bleibt funktional entfernt: keine UI-Option und keine Ausführung.
