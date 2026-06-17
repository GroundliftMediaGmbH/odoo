# Grafiken – Odoo 19 SH

Odoo-App zum Erstellen der 2048 × 1045 px großen Kino-Veranstaltungsankündigungen von GROUNDLIFT.

## Funktionsumfang

- Erstellung direkt aus einer Odoo-Veranstaltung
- Automatische Übernahme von Datum, Uhrzeit, Titel, Text nach dem Bindestrich, Veranstaltungsart und Event-URL
- Upload und interaktive Positionierung des Veranstaltungsbildes
- Fester, unsichtbarer polygonaler Bildausschnitt entsprechend `Kino_Bildausschnitt.png`
- Kanten-Anfasser zum Croppen, Eck-Anfasser zum Drehen, sanfter Mausrad-Zoom und Verschieben im Bild
- Automatische Zwei-Farben-Palette aus dem hochgeladenen Bild
- Kontrastmodus und manuelle Color-Picker
- Änderbare Texte, Fotocredit, Störer, Ticketzeile und QR-Ziel
- Austauschbares Logo und austauschbare feste Ebenen über die Vorlagenkonfiguration
- Generierter QR-Code zur Eventseite
- Ausgabe und Speicherung als JPG
- Integration in die Veranstaltungsansicht über „Grafik erstellen“ und den Smart-Button „Grafiken“

## Aktualisierung von Version 19.0.1.0.0

Die Version 19.0.1.0.1 behebt die Installation unter Odoo 19, indem die Suchansicht an die aktuelle Odoo-19-Syntax angepasst wurde. Den bestehenden Modulordner vollständig durch diese Version ersetzen, committen, den Odoo.sh-Build abwarten und anschließend die App installieren bzw. aktualisieren.

## Installation auf Odoo.sh 19

1. Den Ordner `groundlift_graphics` in das Custom-Addons-Repository kopieren.
2. Committen und auf den gewünschten Odoo.sh-Branch pushen.
3. Den Build abwarten.
4. Apps-Liste aktualisieren.
5. Die App **Grafiken** installieren.
6. Unter **Grafiken → Konfiguration → Grafikvorlagen** das Logo und bei Bedarf die Originalschriftdateien hinterlegen.

## Schriften

Die gelieferten PNG-Layer enthalten die bereits gerasterten Buchstaben, aber keine eigentlichen Font-Dateien. Deshalb kann das Modul die Glyphen ohne die Originalschrift nicht mathematisch rekonstruieren. Positionen, Größen, Zeilenabstände und Buchstabenabstände sind anhand der Referenzebenen fest eingestellt. Für pixelgenaue Buchstabenformen können in der Vorlage die verwendeten OTF-, TTF-, WOFF- oder WOFF2-Dateien hochgeladen werden.

Ohne hochgeladene Schriftdateien werden standardmäßig verwendet:

- normal: `Arial`
- fett: `Arial Black`
- schmal: `Arial Narrow`

## Event-Zuordnung

Beispiel:

`Mensch, Otto! - Zu Gast: Vanessa Eden`

wird zu:

- Titel: `MENSCH, OTTO!`
- Untertitel: `ZU GAST: VANESSA EDEN`

Die Veranstaltungsart kommt zunächst aus der Odoo-Veranstaltungsvorlage (`event_type_id`), ersatzweise aus dem ersten Event-Tag. Alle Werte sind im Grafik-Editor anpassbar.

## Technische Hinweise

- Zielauflösung: 2048 × 1045 px
- Ausgabeformat: JPG (Qualität 96 %)
- QR-Code: Python-Paket `qrcode`, das in den offiziellen Odoo-19-Abhängigkeiten enthalten ist
- Frontend: native Canvas-API in einer Odoo-Owl-Client-Action; keine externen CDN-Abhängigkeiten
- Bilder und Schriften werden als Odoo-Attachments gespeichert


## Automatische Dateinamen

Das Kino-Ausspielformat verwendet standardmäßig:

`JJJJMMTT-JJJJMMTT Veranstaltungsname_Kino.jpg`

Das erste Datum ist das Erstellungsdatum des Grafikdatensatzes, das zweite Datum das lokale Veranstaltungsdatum. Umlaute werden dateisystemfreundlich umgesetzt (`ä` → `ae`, `ü` → `ue`, `ß` → `ss`). Der Suffix `Kino` wird in der Grafikvorlage gepflegt, sodass weitere Ausspielformate später eigene Suffixe erhalten können.

## Feste PNG-Ebenen

Logo, Rahmen und Original-Störer werden vor dem Zeichnen automatisch auf ihren sichtbaren Alpha-Bereich zugeschnitten. Dadurch bleiben Position und Größe auch dann korrekt, wenn Odoo die transparente Gesamtfläche eines hochgeladenen PNGs auf eine andere Auflösung skaliert.


- Veranstaltungsart unter der Uhrzeit: bevorzugt aus dem Event-Feld `Kategorie (Label)` (Groundlift Website), sonst Eventtyp/Tag
