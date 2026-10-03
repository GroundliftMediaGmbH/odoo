# Landingpage Text_to_HTML – v1.8

## Zweck
- Bestehendes Groundlift-Klartextfeld bleibt erhalten.
- Klartext wird nach HTML gespiegelt.
- HTML ist im Tab **Landingpage HTML** editierbar.
- `event.event.description` wird immer mit der HTML-Version synchronisiert.
- Die öffentliche Odoo-Eventseite rendert dadurch die HTML-Version über Odoos Standardfeld.
- Es gibt **keine Website-QWeb-Vererbung und keinen XPath auf die Eventseite**.

## Reparatur gegenüber v1.2–v1.7
Ältere Versionen hinterließen die QWeb-View
`gl_landingpage_event_description_html` mit einem inzwischen ungültigen XPath.

Die v1.8-Pre-Migration neutralisiert diese View per SQL, bevor Odoo die Views
validiert. Entscheidend ist, dass nicht nur `active=False` gesetzt wird, sondern
auch `inherit_id=NULL` und `mode='primary'`. Dadurch muss Odoo den alten XPath
beim Upgrade nicht mehr gegen die geänderte Parent-View auflösen.
