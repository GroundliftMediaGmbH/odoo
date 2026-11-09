# Groundlift POS – Kassenzähl-Funnel & Trinkgeldentnahme (Odoo 19 / Odoo.sh)

Eigenständiges Addon: `gl_pos_cash_count_funnel` (Version `19.0.1.0.4`).

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

## Fix 19.0.1.0.1 (07.11.2026)

Owl-Lifecycle-Absturz `TypeError: ctx.String is not a function` beim
Kassenschluss behoben. In allen drei Scheine-/Münzenlisten wird statt
`[String(den.cents)]` nun `[den.cents]` verwendet. Numerische
JavaScript-Objektschlüssel werden automatisch in Strings konvertiert.
**Keine Änderung an Serverlogik, Kassenbuchungen oder Berechnungen.**
Nach Modul-Upgrade POS-Frontend / Assets neu laden.

## Korrektur 19.0.1.0.3 (08.11.2026)

**WICHTIG: Nur nach Staging-Test im Produktivsystem einsetzen.** Diese
Version behebt eine automatische Überentnahme bei Kartentrinkgeld,
insbesondere bei einem erfassten Anfangsbestand von **0,00 EUR**.

### Fehlerursache und Fix

Bis 19.0.1.0.2 wurde `daily_out = max(0, gezählt - Start -
Bartrinkgeld - Mischtrinkgeld)` berechnet; anschließend wurde das gesamte
Trinkgeld zusätzlich ausgezahlt. Bei zu kleinem Startbestand wurde dadurch
mehr Bargeld entnommen, als im Kasten lag. Beispiel des Vorfalls:

- Stückelzählung **614,80 EUR**, Odoo-Soll für diese Sitzung **139,13 EUR**.
- Trinkgeld **11,29 EUR** (6,49 EUR bar + 4,80 EUR unbar).
- Alter Algorithmus: **608,31 EUR** Tagesüberschuss + **11,29 EUR**
  Trinkgeld = **619,60 EUR**, also **4,80 EUR mehr als vorhanden**.
- Neuer Algorithmus: Der Tagesüberschuss wird notfalls um den unbaren
  Trinkgeldanteil gekappt. **Keine Überentnahme**. In diesem Beispiel wären
  die rein arithmetisch möglichen Entnahmen 603,51 + 11,29 EUR. Aber:
  **Sie werden NICHT automatisch gebucht**, weil die unabhängige
  Odoo-Sollprüfung eine Differenz von **475,67 EUR** feststellt.

### Sicherheit bei Differenzen

Die Preview zeigt den tatsächlich gezählten Bestand, den
`get_closing_control_data()`-Bargeld-Sollbetrag **dieser** Sitzung und die
Differenz. Bei einer Abweichung von **mehr als 1,00 EUR** ist jede
**automatische** Cash-Out-Buchung gesperrt, und zwar auch serverseitig, nicht
nur über den Button. Es werden keine fremden POS-Sitzungen aggregiert.

Die Bedienperson soll Zählung, Eröffnungsbestand und frühere
Bargeldbewegungen prüfen. **Bei weiterhin korrekter Zählung** kann sie die
Option **„Ohne Cash Out zur Odoo-Kassenprüfung“** wählen. Der IST-Wert wird
an das native Abschlussformular übergeben. **Es wird dann keine
Barentnahme gebucht**, und die Standard-Kassendifferenzprüfung von Odoo
bleibt aktiv (ggf. Managerfreigabe). Trinkgelder sind in diesem Sonderfall
separat zu klären; das Ausweichen auf die manuelle Odoo-Prüfung ist
**keine** automatische Trinkgeld-Auszahlung oder Differenzkorrektur.

Wenn wirklich weniger Bargeld als Trinkgeld vorhanden ist, bleibt eine
vollständige Auszahlung als Cash Out gesperrt. Die Fehlermeldung verweist
nun auf die manuelle Odoo-Kassenprüfung.

### POS-Oberfläche

- Hell/dunkel-Kontrast lokal definiert: dunkle Zahlen in weißen Eingaben;
  klar erkennbare +/- Touch-Buttons, eindeutige Scheine-/Münzwerte.
- Für Eröffnung, erste Schlusszählung und Nachzählung gibt es einen
  **sofort sichtbaren nächsten Schritt oberhalb der Zähltabelle**;
  die Summen und die Fortschrittsaktion stehen zusätzlich auch unten.
  Der obere Aktionsstreifen bleibt beim Scrollen soweit durch die
  Odoo-Popup-Struktur möglich sichtbar.
- Für große Abweichungen erscheint eine ausführliche Warnung anstelle
  eines scheinbar buchbaren Tagesüberschusses.
- Die native Odoo-Zahlungsartenliste bleibt bewusst erhalten. 0,00-EUR-
  Methoden sind konfigurierte Zahlungsmethoden, **keine anderen
  Bargeldbestände**. Die Zahlungsartenliste wird **nicht umgebucht oder
  künstlich gefiltert** (auch eine mit 0,00 EUR angezeigte Methode kann
  für spätere Korrekturen relevant sein).

### Bestandsdaten und Upgrades

Die Änderungen gelten für **neue** Buchungen ab 19.0.1.0.3. Bereits
gebuchte Cash-Out-Bewegungen älterer Versionen werden weder rückwirkend
geändert noch erneut gebucht. Bei früheren fehlerhaften Auszahlungen müssen
Kassenbuchungen einzeln von einem POS-Manager/Buchhaltung geprüft werden.

### Lokale Prüfergebnisse

- Serverformel mit den exakten Stückelzahlen aus dem Screenshot getestet,
  inkl. Sicherheitsblock und Grenzfällen mit 0 EUR Startbestand.
- Beispiel mit 200 EUR Start, 700 EUR Bestand, 20 EUR barem und 30 EUR
  unbarem Trinkgeld: 480 EUR Bar-Tagesüberschuss + 50 EUR Trinkgeld,
  170 EUR verbleiben (wie bisher).
- Python-/JS-Syntax und XML-Struktur geprüft. Ein interaktiver
  Odoo-19-Staging-Lauftest inklusive echter Cash-Out-Buchung steht noch aus.

## Erweiterung 19.0.1.0.2 (08.11.2026)

- **Touchbedienung:** Bei Eröffnung, erster Schlusszählung und Nachzählung
  stehen jeweils **− / Menge / +**. Die Zähler laufen in Einzelschritten,
  niemals unter 0 oder über 10.000. Bei Änderung der Eröffnungsmenge muss
  die Eröffnungszählung erneut übernommen werden.
- **Bar-Tagesüberschuss:** Der Wert ist ausschließlich aus **physisch
  gezähltem Bargeld** berechnet (gezählt minus Anfangsbestand minus
  sicher bare und vorsichtshalber als bar eingeordnete gemischte Trinkgelder).
  In der Vorschau und allen Abschlussansichten steht jetzt ausdrücklich
  **„in den Umschlag!“**. Es handelt sich nicht um den gesamten Tagesumsatz
  aller Zahlungsarten. Andere bereits erfolgte Bargeldbewegungen sind in
  der physisch gezählten Menge enthalten und müssen betrieblich berücksichtigt werden.
- **Trinkgelddefizit auffüllen:** Direkt unter „GESAMT BAR ENTNEHMEN“ steht
  das **sicher unbar eingenommene Trinkgeld**. Wenn unbare Zahlungen im POS
  nur Kartenzahlungen sind, entspricht das dem Karten-Trinkgeld. Bei weiteren
  unbaren Zahlungsarten sind diese ebenfalls enthalten; bei gemischten
  Zahlungen ist der Karten-Trinkgeldanteil nicht exakt zuzuordnen.
  **Der Betrag wird nicht zusätzlich entnommen**: Er ist bereits im
  „GESAMT BAR ENTNEHMEN“ enthalten. Der Hinweis erscheint auch nach der
  Buchung und im Bestätigungsdialog.
- Buchungslogik, Server-RPCs und die Trinkgeldzuordnung sind gegenüber
  19.0.1.0.1 **unverändert**. Nur Frontend-Labels/Touchsteuerung und
  die Modulversion wurden angepasst.

## Layout- und CSS-Korrektur 19.0.1.0.4 (08.11.2026)

- Zur Vermeidung von Sass-Kompilierfehlern wurde die lokale `.scss`-Datei
  vollständig durch **flaches, Odoo-asset-kompatibles CSS** ersetzt. Insbesondere
  der Ausdruck `min(100%, 330px)` im vorherigen SCSS konnte von Sass als
  dimensionsübergreifende Berechnung interpretiert werden.
- Bei Eröffnungszählung, Abschlusszählung und Nachzählung befinden sich
  gezählter Betrag, Hauptbutton und Hilfetext jeweils in **eigenen Zeilen**.
  Die Hauptbuttons bleiben auf schmalen Bildschirmen vollflächig, brechen
  bei Bedarf um und überdecken keine andere UI mehr.
- Alle Stückelungszeilen bleiben touch-tauglich mit großen Minus-/Plus-Tasten
  und gut lesbarer Anzahl; auf schmalen POS-Dialogen nur eine vollständige
  Stückelung pro Zeile statt zwei ineinander gequetschter Einträge.
- Für die Ausführung wird ein Odoo-Modulupgrade und POS-Asset-Neuladen
  benötigt. Wenn die Odoo-Meldung über fehlgeschlagene CSS-Kompilierung
  bestehen bleibt, muss der konkrete erste Kompilierungsfehler des POS-Bundles
  im Odoo.sh-Log geprüft werden, da andere Addons ebenfalls Ursachen sein können.
- Keine Änderungen an `models/pos_session.py` oder `cash_count_funnel.js`;
  keine Änderung an Kassenbeträgen, Cash-Outs oder Buchungsabläufen.
