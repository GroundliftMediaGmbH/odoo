# Landingpage Text_to_HTML — Groundlift / Odoo 19 SH — v1.4

Diese Version basiert bewusst wieder auf der vorherigen v1.2-Logik, vereinfacht
aber die Ausgabe der Veranstaltungsseite auf **eine einzige Quelle**:
`event.event.gl_landingpage_html`.

## Gewünschtes Verhalten

1. Das bestehende Groundlift-/Studio-Klartextfeld bleibt erhalten.
2. Änderungen dort werden automatisch in HTML umgewandelt und in
   **Landingpage HTML** gespiegelt.
3. Das HTML-Feld ist mit dem Odoo-HTML-Editor frei formatierbar.
4. Änderungen im HTML-Feld werden als Klartext in das alte Textfeld
   zurückgespiegelt.
5. Die öffentliche Odoo-Veranstaltungsseite rendert **ausschließlich**
   `gl_landingpage_html`. Es gibt im QWeb-Template keinen Fallback mehr auf die
   native Odoo-Beschreibung.
6. Zusätzlich wird `event.description` intern identisch gehalten. Das ist nur
   ein Kompatibilitäts-Fallback für andere installierte Groundlift-/Odoo-Views,
   die möglicherweise weiterhin das native Feld verwenden. Sichtbar soll auf
   der Standardseite trotzdem ausschließlich `gl_landingpage_html` sein.

## Wichtig beim Upgrade von v1.3

Die Modulversion ist absichtlich **19.0.1.4.0**. Dadurch kann Odoo beim Upgrade
die Migration ausführen. Die Migration:

- behält bereits vorhandene, formatierte Landingpage-HTML-Texte vollständig bei;
- füllt nur leere HTML-Felder aus dem alten Klartextfeld;
- synchronisiert danach den nativen Website-Fallback auf dieselbe HTML-Version.

## Installation / Austausch

1. Den kompletten Ordner `gl_landingpage_text_to_html` aus diesem ZIP im
   Repository ersetzen.
2. Auf Odoo.sh Staging pushen und den Build abwarten.
3. In Odoo **Apps → App-Liste aktualisieren**.
4. **Landingpage Text_to_HTML → Aktualisieren** ausführen.
5. Danach die Veranstaltung neu öffnen und die Website mit **Strg+F5** laden.

Bei Veranstaltung 60 sollte nach dem Upgrade der Inhalt im Tab
**Landingpage HTML** unverändert vorhanden sein und genau diese formatierte
Version auf `/event/.../register` erscheinen.
