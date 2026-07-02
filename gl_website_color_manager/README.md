# Groundlift Website Color Manager

Odoo-SH-19 Modul zum Scannen und Ändern tatsächlich gerenderter Website-Farben.

## Neu in 19.0.1.3.0

- Bereichsauswahl auf der Website: `Homepage scannen` → `Bereich anklicken`.
- Nach dem Klick erscheint direkt auf der Website ein Overlay mit den gefundenen Farben.
- Änderungen über den Overlay-Color-Picker werden sofort als Live-Vorschau auf die aktuelle Seite geschrieben.
- Mit `Speichern` wird ein direkter CSS-Override angelegt.
- Direkte Overrides sind nicht nur an die einzelne Seite gebunden, sondern an den erkannten CSS-Verweis: Selektor + Property oder CSS-Variable. Dadurch greifen sie auch auf Unterseiten derselben Odoo-Website, sofern dort derselbe CSS-Verweis verwendet wird.
- Die dynamische CSS-Datei bekommt einen Versionsparameter aus der letzten Änderung, damit Browser/Odoo.sh/CDN keine alte CSS-Antwort weiterverwenden.

- Overlay-Farben werden nicht mehr nur nach Hex-Wert zusammengefasst. Jede Fundstelle wird einzeln angezeigt: z. B. Schriftfarbe, Hintergrundfarbe, Rahmenfarbe, SVG-Füllung oder CSS-Variable.
- Dadurch kann dieselbe Originalfarbe in einem Bereich getrennt geändert werden, ohne dass Text und Fläche automatisch dieselbe neue Farbe bekommen.
- Beim Speichern werden alte breite Direkt-Overrides aus Version 19.0.1.2.0 für denselben angeklickten Bereich automatisch deaktiviert, sobald eine neue präzise Fundstelle gespeichert wird.
- Neues Backend-Menü: `Website Farben` → `Direkte Overrides`.

## Nutzung

1. Modul installieren oder aktualisieren.
2. `Website Farben` → `Homepage scannen` öffnen.
3. Website und Pfad auswählen.
4. `Bereich anklicken` wählen.
5. Auf der Website den gewünschten Bereich anklicken.
6. Im Overlay die passende Fundstelle wählen, z. B. Schriftfarbe oder Hintergrundfarbe, und Farbe per Picker ändern.
7. Ergebnis direkt prüfen.
8. `Speichern` klicken.

## Technische Logik

Der Scanner arbeitet browserbasiert, weil Odoo serverseitig nicht zuverlässig wissen kann, welche Farben nach Theme, Snippets, Inline-Styles, CSS-Variablen und Breakpoints wirklich sichtbar sind.

Beim Bereichsklick werden zwei Arten von Fundstellen gespeichert:

- gerenderte Styles des ausgewählten Elements und seiner Unterelemente,
- passende Stylesheet-Regeln, deren Selektoren auf den ausgewählten Bereich zutreffen.

Die zweite Art ist wichtig, damit ein gespeicherter Override auch auf anderen Seiten wirkt, wenn dort derselbe CSS-Selektor bzw. dieselbe CSS-Variable verwendet wird.

## Hinweise

- Alte Backend-Farbumschaltungen über `Farben ändern` bleiben erhalten.
- Neue Overlay-Änderungen landen unter `Direkte Overrides` und werden im CSS nach den allgemeinen Farbregeln ausgegeben, damit sie gewinnen.
- Falls ein Odoo-Snippet Inline-Styles mit `!important` setzt, kann auch ein direkter Override vom Browser blockiert werden. In diesem Fall muss der spezifische Inline-Wert im Website-Editor entfernt oder die Regel im Backend gezielt angepasst werden.
