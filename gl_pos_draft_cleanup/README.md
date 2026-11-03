# Groundlift POS – Drafts löschen (Fix 19.0.1.1.0)

Odoo 19 / Odoo.sh – Upgrade derselben App `gl_pos_draft_cleanup`.

## Verhalten

Button **Drafts löschen** im POS-Dialog **Kasse schließen**:

1. Lokale Bestellungen werden zunächst synchronisiert.
2. Es erscheint ausdrücklich eine **VORSCHAU**. Bis hierher wird nichts verändert.
3. Erst nach **Jetzt verbindlich stornieren** wird `pos.session.gl_cancel_draft_cleanup()` ausgeführt.
4. Der Server prüft erneut alle Voraussetzungen, sperrt die betroffenen Datensätze, storniert sie via `action_pos_order_cancel()` und ermittelt die Zahl der danach verbleibenden Drafts.
5. Der Benutzer erhält eine eigene Meldung **X Draft(s) STORNIERT – bestätigt**, einschließlich verbleibender offener Drafts. Ein Fehler zeigt **Drafts NICHT storniert**.
6. Der **Kassenschluss wird NICHT automatisch ausgelöst**. Danach den Kassenschlussdialog regulär schließen/öffnen und die Sitzung normal abschließen.

Das Modul unterscheidet bewusst `Vorschau` und `Stornierung`.

## Was geändert wurde

- Version 19.0.1.1.0 statt 19.0.1.0.0.
- Die bisherige Implementierung rief nach serverseitiger Stornierung lokale POS-Cache-Funktionen und `pos.closeSession()` auf. Ein dort auftretender Fehler konnte die erfolgreiche Stornierung verdecken. Diese Schritte sind jetzt getrennt; der Kassenschluss erfolgt nicht automatisch.
- Expliziter zweiter Bestätigungsbutton, klare Erfolgs-/Fehlermeldung.
- Server antwortet mit `remaining_drafts`, sodass das Ergebnis nicht aus dem Frontend-Cache geschätzt werden muss.
- Fehler in der *lokalen* POS-Auftragsbereinigung überschreiben keine bereits erfolgreiche serverseitige Stornierung. In diesem Fall wird die erforderliche manuelle Synchronisierung angezeigt.

## Sicherheitsgrenzen

Nur Drafts der **aktuellen** Sitzung, die wenigstens 60 Sekunden unverändert sind, mit Gesamtbetrag 0,00 EUR und ohne Zahlungen, Lagerbewegungen, Rechnung oder geplanten Zeitpunkt. Zulässig sind nur vollständig leere Aufträge oder exakt (Produkt, Preis, Rabatt, Steuern) gegengebuchte Positionen. Bezahlte oder normal offene Verkäufe werden nicht verändert. Es werden maximal 200 Drafts pro Aufruf bearbeitet. Autorisierung und erneute Prüfung serverseitig; Datensatzsperre bis zum RPC-Ende.

**Wichtig**: Die App nutzt ausschließlich die Odoo-Stornierung (`state=cancel`), keine physische Löschung. Der Erfolg des Aufrufs kann lokale ungesendete Änderungen anderer Geräte nicht ausschließen. Während der Bereinigung sollte niemand dieselben Bestellungen auf einem anderen Terminal bearbeiten.

## Upgrade einer bereits installierten App auf Odoo.sh

1. Auf **Staging** den vorhandenen Ordner `gl_pos_draft_cleanup` im Git-Repository **vollständig ersetzen** (nicht zwei Versionen parallel installieren).
2. Änderungen committen / Staging neu bauen.
3. In Apps die installierte App **Groundlift POS – Drafts löschen** mit **Upgrade/Aktualisieren** aktualisieren. Nur Git-Deploy kann Asset-Caches unverändert lassen.
4. POS-Clients **erst nach erfolgreicher Synchronisierung ihrer lokalen Verkäufe** neu laden. Bei der Umstellung während einer Veranstaltung ist besondere Vorsicht erforderlich.
5. Auf Staging testweise leeren Draft älter als 60 Sekunden erzeugen, prüfen, **Jetzt verbindlich stornieren** klicken; dann in der Shell `state=cancel` überprüfen und anschließend Kassenschluss testen.
6. Erst dann Production aktualisieren.

### Staging-Testmatrix

- Leerer 0-EUR-Draft mit 60+ Sekunden: nach Bestätigung `cancel`.
- +1/−1 gleicher Artikel gleicher Preis/Steuern: nach Bestätigung `cancel`.
- Vorschau ohne Bestätigung: bleibt `draft`.
- Draft <60 Sekunden, laufende Bestellung >0 EUR, Gratisartikel ohne Gegenbuchung, Draft mit Zahlung/Lagerbewegung: geschützt.
- Der Server zeigt `remaining_drafts` korrekt an.
- Fehler beim lokalen Cache-Aufräumen darf keine falsche Meldung `nicht storniert` produzieren, wenn Server bereits storniert hat.
- Andere Kassensitzung nicht betroffen.

## Diagnose, falls weiterhin nichts passiert

- Unterscheidet der Dialog noch `VORSCHAU` und `Jetzt verbindlich stornieren`? Wenn nicht: alter JS-Assetcache/Modul noch nicht upgegradet.
- Bei `Drafts NICHT storniert`: Fehlermeldung/Console-Screenshot weitergeben.
- Sind danach noch `remaining_drafts > 0`, so wurden diese aus Sicherheitsgründen nicht ausgewählt und müssen gesondert untersucht werden.
- Eine allgemeine POS-/Buchhaltungsstörung wird durch dieses Modul nicht behoben.

Eine Live-Integration in Groundlifts Odoo.sh-Installation wurde hier nicht getestet.
