# Landingpage Text_to_HTML – Odoo 19 SH

## Zweck

* Das bestehende **Textfeld "Event Beschreibung" bleibt unangetastet**.
* Das Modul legt `event.event.gl_landingpage_html` (HTML) an.
* Bei Installation werden bestehende Texte übernommen, sofern **genau ein**
  `event.event`-Textfeld mit der Feldbeschriftung "Event Beschreibung" erkannt wird.
* Zeilenumbrüche werden als `<br/>` ausgegeben; HTML-Zeichen werden escaped.
* Bearbeitung entweder im Backend unter **Landingpage HTML** oder **direkt im
  Odoo-Website-Editor auf der Standard-Veranstaltungsseite**.
* HTML-Bearbeitung schreibt den lesbaren Text ohne Formatierungen ins bisherige
  Textfeld zurück. Bearbeiten des bisherigen Feldes schreibt die HTML-Fassung
  neu – dabei gehen dort vorhandene Formatierungen verloren.

## Quellfeld prüfen – wichtig!

Der Screenshot zeigt nur die Beschriftung, **nicht** den technischen Feldnamen.
Das Modul erkennt das Feld nur, wenn die Beschriftung eindeutig passt.
Andernfalls unter **Einstellungen → Technisch → Parameter → Systemparameter**
folgenden Parameter anlegen:

    Schlüssel: gl_landingpage_text_to_html.source_field
    Wert:      <technischer Name des existierenden event.event-Textfeldes>

Der Wert muss vom Typ `text` sein. Er darf NICHT `description` sein (das
Standard-Odoo-Feld `description` ist schon HTML!). Das Modul nimmt keinerlei
Änderungen an vorhandenen Studio-Felddefinitionen vor.

Falls du den Parameter erst **nach** Installation eingetragen hast, öffne eine
Veranstaltung → **Landingpage HTML** → **Bestehenden Text übernehmen**.
Der Button überschreibt bewusst keine bereits formatierte HTML-Fassung.

## GitHub / Odoo SH

Den Ordner `gl_landingpage_text_to_html` ins Root deines Odoo-Addons-Repos
legen (neben die übrigen Modulordner); committen/pushen; zunächst **staging**
aktualisieren, dann Apps-Liste aktualisieren und das Modul installieren.
Nach erfolgreichem Test die gleiche Version auf production deployen.

## Geltungsbereich

Die Website-Vorlage erweitert **nur** die Standard-Odoo-19-Veranstaltungsseite,
deren Odoo-Vorlage `website_event.event_description_full` ist. Wenn eure
Groundlift-Homepage eine **eigene QWeb-Vorlage oder PHP-Seite auf Hetzner**
verwendet, muss **diese** gesondert auf `gl_landingpage_html` umgestellt werden.
Das kann ein Odoo-Modul ohne Zugriff auf diese Website-Implementierung nicht
verlässlich automatisch erledigen.

Eine bereits per Website-Builder individuell ersetzte Event-Vorlage kann die
Odoo-Standardvorlage übersteuern; dann ist eine gezielte Anpassung erforderlich.

## Konfliktregel

* Alte Text-Beschreibung geändert → HTML wird aus dem Text neu erstellt
  (**bestehende Formatierungen gehen dabei verloren**).
* HTML-Beschreibung geändert → ursprüngliches Textfeld erhält Klartext
  (**Linkziele können im Klartext nicht gespeichert werden**).
* Wenn beide Felder in einem Write mitgeliefert werden, gilt HTML.

## Sicherheits- und Abnahmetest

1. Vor der Installation Odoo-SH-Backup / Staging benutzen.
2. Eine bestehende Veranstaltung aufrufen: Zeilenumbrüche müssen identisch sein.
3. Ein Wort fett formatieren, einen Link einfügen, speichern: Website prüfen.
4. Bestehendes Feld prüfen: dort weiterhin reiner Text.
5. Bestehenden Text manuell ändern: HTML wird ersetzt (Hinweis oben beachten).
6. Eine zweite Veranstaltung prüfen: HTML ist pro Veranstaltung gespeichert.

Nicht auf einer ungeprüften Produktionsinstanz installieren: Studio-Feldname und
eventuelle individuelle Website-Overrides sind aus dem Screenshot nicht ablesbar.
