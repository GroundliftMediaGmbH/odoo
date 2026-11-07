# Groundlift POS – Kassenzähl-Funnel & Trinkgeldentnahme (Odoo 19 / Odoo.sh)

Eigenständiges Addon: `gl_pos_cash_count_funnel` (Version `19.0.1.0.0`).

## Bedienung

### Kasseneröffnung

Der **native** Odoo-Dialog „Opening Control“ zeigt statt des manuellen Betragsfeldes
sofort die bebilderte EUR-Stückelzählung (500 € bis 1 Cent). Anzahl je Schein/Münze
angeben → **Zählung übernehmen** → normal auf **Kasse eröffnen** klicken.
Der gezählte Wert wird an Odoos unverändertes `set_opening_control` übergeben.
Die Stückelung wird in den normalen Eröffnungsnotizen protokolliert.

### Kassenschluss

Beim Aufruf des **nativen** „Closing Register“-Dialogs erscheint zusätzlich ein
vierstufiger Helfer:

1. Bargeld **vor** jeder Entnahme zählen; inklusive bereits in der Kasse liegendem
   Bartrinkgeld (Pflicht).
2. Preview: Startbestand, gezähltes Bargeld, abzuführender Tagesüberschuss,
   gesamtes Trinkgeld (bar/unbar/gemischt), gesamte Bargeldentnahme,
   danach verbleibender Bestand, Betrag unter ursprünglichem Startbestand
   und tatsächliche Differenz zu Odoos theoretischem Kassenstand.
3. **Verbindlich Cash Out buchen** mit gesonderter Bestätigung. Führt zwei
   **normale** Odoo `pos.session.try_cash_in_out('out', ...)` aus: Tagesüberschuss
   und Trinkgeld. Nach der Buchung Bargeld **physisch entnehmen**.
4. Danach nochmals alle Scheine und Münzen zählen; Abschlusszählung ins
   native Odoo-Cash-Count-Feld übernehmen; native Schließen-Schaltfläche
   erst danach freigeschaltet. Echte verbleibende Kassendifferenz wird wie
   bisher von Odoo ermittelt und ggf. bestätigt.

Bei Abbruch, Verbindungsverlust oder erneutem Aufrufen erkennt der Helfer
bereits gebuchte Entnahmen und verlangt **nur erneutes Nachzählen**. Er bucht
**keine** Entnahmen doppelt. Ein Server-Lock, Stichtagssignatur, Berechtigungs-
prüfung und DB-Transaktionsgrenzen verhindern konkurrierende Doppelbuchungen.

## Beispiel (ohne gemischte Trinkgelder)

- Wechselgeld zu Beginn: 200,00 €
- Zum Schluss bar gezählt: 700,00 €
- Bartrinkgeld: 20,00 €, unbares Trinkgeld: 30,00 €
- Abzuführender Bargeldumsatz: 700 − 200 − 20 = **480,00 €**
- Gesamtes auszuzahlendes Trinkgeld: 20 + 30 = **50,00 €**
- Insgesamt Bar-Cash-Out: **530,00 €**
- Nach Entnahme verbleibend: **170,00 €**
- Wechselgeldlücke durch die unbare Trinkgeld-Auszahlung: **30,00 €**
- Odoo erfasst **keine künstliche Kassendifferenz** allein wegen der
  gebuchten Cash-Out-Vorgänge. Eine *echte* Abweichung zwischen Odoo-
  Soll und physischem Ist bleibt im nativen Kassenschluss sichtbar.

## Gemischte Zahlungsarten

Odoo speichert im Standard `pos.order.tip_amount` pro Bestellung und
`pos.payment.amount` pro Zahlungsmethode, aber ohne verlässliche Zuordnung
*des Trinkgeldanteils* zu einzelnen Zahlungsmethoden bei Mischzahlungen.
Deshalb wird bei gemischten Zahlungen das Trinkgeld **vollständig** ausbezahlt,
bei der Tagesabschöpfung jedoch vorsichtshalber als **bar** angenommen.
Der exakte unbare Trinkgeldanteil ist für solche Vorgänge nicht bestimmbar,
und der Bildschirm zeigt das explizit an. In der Anzeige „sicher unbar“ sind
Karten **und ggf. andere nicht-bar erfasste Zahlungsarten** enthalten.

## Zusammenspiel mit Groundlift-Modulen

Quellstand geprüft: `odoo-main-production (3)(2).zip` vom 06.11.2026.

- `gl_pos_closing_tips`: bestehende unveränderte Trinkgeldanzeige im
  Kassenschluss bleibt erhalten. Gleiche Klassifizierung Bar/Unbar/Gemischt.
- `gl_pos_draft_cleanup`: Drafts-löschen-Schaltfläche im Kassenschluss bleibt
  erhalten; sie löst **keinen** Cash Out aus. Vor jeder Entnahmevorschau
  synchronisiert der Helfer lokale POS-Bestellungen.
- `gl_pos_anonymous_event_tickets`: keine Berührung der Ticketregistrierung.
- `gl_gross_sales_price`: keine Berührung von Brutto-/Netto-/Rundungsregeln.
- `groundlift_kino_pos`: keine Änderung am externen Kino-Dashboard.

Native Odoo-Kasseneröffnung, Kassenschluss und `pos.session`-Accounting werden
**nicht ersetzt**. Es werden ausschließlich die beiden POS-Dialoge per OWL-Patch
und Template-Erweiterung ergänzt. Cash-Outs verwenden die Standard-API.

## WICHTIG: Buchhaltung

Ein Odoo **Cash Out** dokumentiert den Bargeldabgang, ist aber nicht
zwangsläufig die abschließende Buchung einer *Trinkgeldverbindlichkeit*.
Daher bitte mit Buchhaltung/Steuerberatung prüfen, auf welche Konten
Tagesabschöpfung und Mitarbeitertrinkgeld durch das jeweilige Kassenjournal
gebucht bzw. wie deren Kontoauszüge ausgeglichen werden sollen. Das Modul
ändert **keine** Kontenkonfiguration und erzeugt **keine** Lohnabrechnung.

## Installation (zuerst Staging)

1. Modulordner `gl_pos_cash_count_funnel` in den Root eures bestehenden
   Odoo.sh-Custom-Addons-Repositories kopieren (kein doppelter Modulordner).
2. Commit / Push in **Staging**, Apps-Liste aktualisieren, App
   „Groundlift POS – Kassenzähl-Funnel & Trinkgeldentnahme“ installieren.
3. Im POS „Bargeldkontrolle“ aktivieren, Mitarbeiter für die reguläre Odoo
   Cash-In/Out-Funktion berechtigen, Euro-Währung vorausgesetzt.
4. POS **nach Synchronisierung** aller offenen Verkäufe vollständig neu laden.
   Keine Neuladung während aktiver Kundenzahlungen!
5. Erst nach vollständigem Staging-Test auf Production installieren.

## Staging-Testmatrix

- EUR-Stückelung: 1 × 50 €, 2 × 2 €, 1 × 0,20 € = 54,20 €; Öffnen erst nach
  „Zählung übernehmen“ möglich. Native Eröffnungsnotiz prüfen.
- Nullbestand 0,00 € explizit bestätigen.
- Abschluss wie obiges Beispiel: 480 € Tagesüberschuss, 50 € Trinkgeld,
  170 € Nachzählung; genau **zwei** Cash-Out-Zeilen, keine künstliche Differenz.
- Nach bestätigtem Cash Out Dialog schließen/öffnen: **kein doppeltes** Cash Out.
- Fehlende POS-Cash-Out-Berechtigung: Hinweis statt unberechtigter Buchung.
- Nicht erfolgreich synchronisierte Orders: Entnahmeberechnung verweigern.
- Gemischte Zahlungen: Trinkgeld vollständig ausbezahlen, Zuordnung als
  unsicher kennzeichnen.
- Zählfehler: echte Kassendifferenz erscheint weiter wie bisher.
- Prüfung, dass `gl_pos_draft_cleanup` im selben Dialog noch funktioniert
  und `gl_pos_closing_tips` weiterhin angezeigt wird.
- Staging Test mit mehreren Terminals und Abbruch direkt nach der Buchung:
  über „Buchungsstatus erneut prüfen“ ausschließlich wieder zur Nachzählung.

### Grenzen und Stand der Prüfung

Quellcode von Groundlift-Produktion und Odoo-19-Kernmethoden statisch geprüft.
PY- und JS-Syntax, XML-Wohlgeformtheit und Paketstruktur lokal geprüft.
Kein Zugriff auf eine laufende Groundlift-Staging-Datenbank und kein Live-Test
der OWL-Assets/Buchhaltungsbuchungen; **vor Einsatz zwingend Staging-Test**.
Nur Euro-Stückelungen werden ersetzt; andere Währungen nutzen nativen Dialog.
