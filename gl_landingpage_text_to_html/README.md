# Landingpage Text_to_HTML — Groundlift / Odoo 19 SH

## Fix 19.0.1.3.0 — HTML-Reiter ist jetzt die führende Quelle

In v1.2 gab es noch zwei Schutzmechanismen, die bei bestehenden Veranstaltungen
zu genau dem beobachteten Effekt führen konnten: Das HTML im Backend war korrekt,
aber `event.event.description` konnte absichtlich auf einem älteren Stand bleiben,
wenn dessen Inhalt abwich. Außerdem läuft ein `post_init_hook` bei einer normalen
Modul-Aktualisierung nicht als allgemeine Upgrade-Migration für bereits vorhandene
Datensätze.

Ab v1.3 gilt deshalb eindeutig:

- Sobald **Landingpage HTML** Inhalt hat, ist dieses Feld die führende Quelle.
- Beim Speichern wird das HTML **1:1** in Odoos natives HTML-Feld
  `event.event.description` gespiegelt. Fettungen, Links, Listen, Überschriften
  usw. bleiben dadurch erhalten.
- Eine abweichende alte native Beschreibung wird vor dem ersten Überschreiben
  einmal in `gl_landingpage_native_backup` gesichert.
- Ein echtes Upgrade-Skript synchronisiert auch bereits vorhandene Events beim
  Update auf v1.3 automatisch.
- Die öffentliche Odoo-19-Vorlage `/event/<slug>/register` rendert zusätzlich
  direkt `gl_landingpage_html`. Die View läuft mit hoher Priorität, damit spätere
  Theme-/Website-Anpassungen nicht versehentlich wieder auf den alten Inhalt
  zurückschalten.
- Direkte Änderungen im Odoo-Website-Editor werden weiterhin zurück in den
  Landingpage-HTML-Reiter übernommen, sobald die Verknüpfung aktiv ist.

## Austausch / Installation

1. Den kompletten Ordner `gl_landingpage_text_to_html` aus diesem ZIP über den
   bestehenden Modulordner im GitHub-Repository kopieren.
2. Commit + Push auf den Staging-Branch und den grünen Odoo.sh-Build abwarten.
3. In Odoo **Apps → App-Liste aktualisieren** und anschließend
   **Landingpage Text_to_HTML → Aktualisieren (Upgrade)** ausführen.
4. Veranstaltung 60 öffnen. Im Reiter **Landingpage HTML** einmal kontrollieren,
   dass die Formatierung vorhanden ist.
5. Danach `/event/blue-hour-story-60/register` mit Strg+F5 neu laden.

Nach dem Upgrade sollte kein manueller „Übernehmen“-Schritt mehr nötig sein.
Der Button bleibt nur als Reparatur-/Kontrollfunktion erhalten.

## Technische Kontrollpunkte

Wenn das HTML-Feld z. B. enthält:

```html
<p><strong>Musik wie Kino für die Seele</strong></p>
```

muss nach dem Speichern derselbe HTML-Inhalt auch in
`event.event.description` stehen. Die öffentliche Odoo-Seite nutzt in Odoo 19
die Vorlage `website_event.event_description_full`; dort wird das Feld innerhalb
von `#o_wevent_event_main_col` gerendert.

Das optionale alte Studio-Klartextfeld bleibt bestehen und wird weiterhin nur
als Klartext-Spiegel geführt.
