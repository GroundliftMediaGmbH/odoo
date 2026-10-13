# Groundlift POS – Drafts löschen (Odoo 19.sh)

## Funktion
Im POS: **Menü (☰) → Kasse schließen → Drafts löschen**.

Das Modul verwendet die reguläre Odoo-Stornierungsfunktion, nicht `unlink()`.
Es prüft und storniert **ausschließlich** Entwürfe der **aktuellen Kassensitzung**, die:

- bereits mindestens **60 Sekunden unverändert** sind,
- **0,00 € Gesamtbetrag**, **keine Zahlungen**, **keine Lagerbewegungen** und **keine Rechnung** haben,
- **keinen geplanten Abhol-/Lieferzeitpunkt** enthalten,
- entweder **keine Positionen** haben oder **exakt gegengebuchte Positionen** enthalten (gleicher Artikel, Einzelpreis, Rabatt und Steuern; Summe der Mengen je Schlüssel = 0).

Reguläre offene Verkäufe mit Betrag > 0, kostenfreie Artikel, geplante Bestellungen und bezahlte Aufträge bleiben unangetastet. Vor der Stornierung werden die Kandidaten angezeigt und ausdrücklich bestätigt. Zwischenzeitliche Änderungen verhindern die Stornierung; parallele Bearbeitung wird per Datenbanksperre abgesichert. Maximal 200 Kandidaten pro Vorgang. Die Aktion wird protokolliert.

Nach Erfolg werden passende lokale Entwürfe aus dem POS-Cache entfernt und der Dialog zum Kassenschluss mit frischen Daten erneut geöffnet. Andere POS-Geräte können noch veraltete Ansichten haben; deshalb vor dem Schließen weiterhin die Synchronisierung prüfen.

## Installation auf Odoo.sh

1. Den Ordner `gl_pos_draft_cleanup` in euer Odoo.sh-Git-Repository unter die Custom-Addons legen (z. B. `custom_addons/`). Den Modulordner nicht in ein weiteres gleichnamiges Unterverzeichnis verschachteln.
2. Erst auf **Staging** deployen; Apps-Liste aktualisieren und **Groundlift POS – Drafts löschen** installieren.
3. POS auf Staging neu laden und im Dialog `Kasse schließen` den Button prüfen.
4. Nach erfolgreichem Test auf **Production** übernehmen. Bei Installation während des Betriebs bitte vorher laufende POS-Sitzungen/Browsersync prüfen, keine ungesendeten Verkäufe verlieren.

## Tests auf Staging

- Zwei leere Entwürfe älter als 60 Sekunden in derselben Sitzung: Vorschau → bestätigen → `cancel`.
- Gin-Tonic +1/-1 mit identischem Preis/Rabatt/Steuern und 0 €: wird angeboten.
- Bezahlter Auftrag, laufender Verkauf mit 9 €, kostenloser Artikel, 0-€-Entwurf jünger als 60 Sek., Entwurf mit Zahlung oder Lagerbewegung: werden NICHT angeboten.
- Entwurf der *anderen* POS-Sitzung: wird nicht angeboten.
- Parallelbearbeitung oder Änderung nach Vorschau: Server lehnt ab, keine Teilstornierung.
- Anschließend Kassenschluss mit tatsächlich gezähltem Bargeldbestand testen.

## Einschränkungen

- Der Button ist nur im **Kassenschluss-Dialog** sichtbar.
- Er repariert keine anderen Buchungs-/Zahlungs-/Mollie-Probleme.
- Er setzt serverseitig den Sitzungsverantwortlichen oder POS-Manager voraus. Bei gemeinsam genutztem POS-Login muss die Rollenzuordnung entsprechend eingerichtet sein.
- Eine echte Live-Installation wurde hier nicht durchgeführt: Staging-Test mit eurem Odoo-19.sh-Build ist erforderlich.
