# Landingpage Text_to_HTML – Odoo 19 SH – v1.9

Diese Variante verwendet **keine Website-QWeb-Vererbung** mehr.

- Das bestehende Groundlift-Textfeld bleibt erhalten.
- Der Klartext wird in `gl_landingpage_html` gespiegelt und dort als HTML bearbeitet.
- `gl_landingpage_html` ist für die Website führend und wird 1:1 nach `event.description` synchronisiert.
- Die normale Odoo-Eventseite rendert damit die HTML-Fassung über ihr natives Beschreibungsfeld.
- Eine veraltete QWeb-View aus früheren Versionen wird vor dem Modul-Upgrade per SQL neutralisiert und vom alten XML-ID-Mapping getrennt.
- Die Migration verwendet **kein** `odoo.upgrade` / `upgrade-util` und benötigt daher keine zusätzliche `requirements.txt`-Abhängigkeit.
