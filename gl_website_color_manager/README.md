# Groundlift Website Color Manager

Odoo-SH-19 Modul zum Scannen und Ändern tatsächlich gerenderter Website-Farben.

## Neu in 19.0.1.4.0

- Der Bereichsklick arbeitet jetzt **pixel-/elementgenau**: Es wird nicht mehr automatisch der ganze Container samt Kind-Elementen analysiert.
- Es wird im Overlay nichts mehr nach Hex-Farbe zusammengefasst. Jede Zeile ist eine einzelne Fundstelle, z. B. exakt `color`, exakt `background-color`, exakt `border-top-color` oder exakt eine passende Stylesheet-Regel.
- Dadurch kann dieselbe Farbe an Schrift, Fläche und Rahmen komplett unterschiedlich geändert werden.
- `Speichern` legt weiterhin einen globalen Override für denselben CSS-Verweis an: gleicher Selektor + gleiche CSS-Eigenschaft + gleicher Originalwert.
- Neben `Speichern` gibt es jetzt pro Zeile `Rückgängig`. Dieser Button deaktiviert den passenden direkten Override und lädt das dynamische CSS sofort neu.
- Die eigenen Manager-Stylesheets werden beim Scan ignoriert, damit alte gespeicherte Overrides und Live-Vorschauen den nächsten Scan nicht als neue Originalfarbe verfälschen.
- CSS-Variablen werden nicht mehr pauschal auf `:root` geschrieben, sondern auf den erkannten Selektor. Nur echte `:root`-Variablen wirken dadurch komplett global.

## Nutzung

1. Modul installieren oder aktualisieren.
2. `Website Farben` → `Homepage scannen` öffnen.
3. Website und Pfad auswählen.
4. `Bereich anklicken` wählen.
5. Auf der Website exakt den Text, Button, Balken, Rahmen oder Bereich anklicken, der geändert werden soll.
6. Im Overlay die passende einzelne Fundstelle wählen.
7. Farbe per Picker ändern und das Ergebnis direkt prüfen.
8. `Speichern` klicken, damit die Änderung global für denselben CSS-Verweis gilt.
9. Mit `Rückgängig` kann der gespeicherte direkte Override wieder deaktiviert werden.

## Technische Logik

Der Scanner arbeitet browserbasiert, weil Odoo serverseitig nicht zuverlässig wissen kann, welche Farben nach Theme, Snippets, Inline-Styles, CSS-Variablen und Breakpoints wirklich sichtbar sind.

Beim Bereichsklick werden jetzt nur noch das exakt angeklickte Element und die darauf passenden Stylesheet-Regeln ausgewertet. Kind-Elemente werden nicht mehr automatisch mitgescannt. So werden Schrift, Hintergrund und Rahmen nicht mehr miteinander vermischt.

Gespeichert wird als direkter Override nach:

- Website,
- Quelle (`computed`, `stylesheet`, `css_variable`),
- CSS-Selektor,
- CSS-Eigenschaft,
- CSS-Variable,
- Originalwert,
- gefundener Farbe.

Dadurch wirkt eine gespeicherte Änderung auf anderen Seiten derselben Website, sofern dort derselbe CSS-Verweis verwendet wird.

## Hinweise

- Alte Backend-Farbumschaltungen über `Farben ändern` bleiben erhalten.
- Neue Overlay-Änderungen landen unter `Direkte Overrides` und werden im CSS nach den allgemeinen Farbregeln ausgegeben, damit sie gewinnen.
- Falls ein Odoo-Snippet Inline-Styles mit `!important` setzt, kann auch ein direkter Override vom Browser blockiert werden. In diesem Fall muss der spezifische Inline-Wert im Website-Editor entfernt oder die Regel im Backend gezielt angepasst werden.
