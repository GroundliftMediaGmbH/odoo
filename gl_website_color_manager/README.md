# Groundlift Website Color Manager

Odoo-SH-19 Modul zum Scannen und Ändern tatsächlich gerenderter Website-Farben.

## Neu in 19.0.1.5.0

- Der Bereichsklick speichert Overlay-Änderungen jetzt **spezifisch für das exakt angeklickte Element**.
- Es werden im Overlay keine passenden Stylesheet-Regeln und keine globalen CSS-Variablen mehr angeboten. Dadurch wird aus einem Klick auf Schrift/Button/Bereich keine globale Theme-Farbänderung mehr.
- Die erzeugten Selektoren sind absichtlich sehr genau (`body > ... > element:nth-of-type(...)`), damit nicht automatisch andere Buttons, Überschriften oder Bereiche derselben Klasse mit geändert werden.
- Die Live-Vorschau bleibt erhalten: Picker ändern → Ergebnis sofort sehen → `Speichern`.
- `Rückgängig` bleibt pro Zeile erhalten und deaktiviert genau den gespeicherten spezifischen Override.
- Beim Speichern eines neuen spezifischen Overrides werden ältere breite Direkt-Overrides für denselben angeklickten Bereich/Farbwert deaktiviert, damit alte globale Regeln nicht weiter dazwischenfunken.

## Nutzung

1. Modul installieren oder aktualisieren.
2. `Website Farben` → `Homepage scannen` öffnen.
3. Website und Pfad auswählen.
4. `Bereich anklicken` wählen.
5. Auf der Website exakt den Text, Button, Balken, Rahmen oder Bereich anklicken, der geändert werden soll.
6. Im Overlay die passende einzelne Fundstelle wählen.
7. Farbe per Picker ändern und das Ergebnis direkt prüfen.
8. `Speichern` klicken, damit die Änderung spezifisch für diesen exakten Element-Selektor gespeichert wird.
9. Mit `Rückgängig` kann der gespeicherte direkte Override wieder deaktiviert werden.

## Technische Logik

Der Scanner arbeitet browserbasiert, weil Odoo serverseitig nicht zuverlässig wissen kann, welche Farben nach Theme, Snippets, Inline-Styles, CSS-Variablen und Breakpoints wirklich sichtbar sind.

Beim Bereichsklick wird jetzt nur noch das exakt angeklickte Element ausgewertet. Kind-Elemente, passende Stylesheet-Regeln und globale CSS-Variablen werden in diesem Overlay-Modus bewusst nicht mehr mitgescannt. So bleibt die Änderung lokal/spezifisch und wird nicht wieder zur globalen Theme-Farbänderung.

Gespeichert wird als direkter Override nach:

- Website,
- Quelle (`computed` im spezifischen Overlay-Modus),
- CSS-Selektor,
- CSS-Eigenschaft,
- CSS-Variable,
- Originalwert,
- gefundener Farbe.

Dadurch wirkt eine gespeicherte Overlay-Änderung nur dort, wo derselbe sehr spezifische Element-Selektor existiert. Sie ist nicht mehr als globale Theme-/Stylesheet-Regel gedacht.

## Hinweise

- Alte Backend-Farbumschaltungen über `Farben ändern` bleiben erhalten.
- Neue Overlay-Änderungen landen unter `Direkte Overrides` und werden im CSS nach den allgemeinen Farbregeln ausgegeben, damit der spezifische Element-Override gewinnt.
- Falls ein Odoo-Snippet Inline-Styles mit `!important` setzt, kann auch ein direkter Override vom Browser blockiert werden. In diesem Fall muss der spezifische Inline-Wert im Website-Editor entfernt oder die Regel im Backend gezielt angepasst werden.
