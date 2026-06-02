# Groundlift Google Analytics Dashboard

Kleines Odoo-19-SH-Modul, das einen eigenen Menüpunkt **Google Analytics** anlegt und beim Anklicken eine interne Odoo-Seite mit einem eingebetteten Looker-Studio-/Google-Analytics-Dashboard öffnet.

## Enthalten

- Odoo-Menüpunkt: **Google Analytics**
- Interne Route: `/groundlift/google-analytics`
- Iframe mit dem angegebenen Looker-Studio-Link
- Button „Zurück zu Odoo“
- Button „Extern öffnen“

## Installation auf Odoo.sh

1. ZIP entpacken.
2. Den Ordner `groundlift_google_analytics` in den Addons-/Custom-Modul-Ordner des Odoo.sh-Repositories kopieren.
3. Änderungen committen und nach Odoo.sh pushen.
4. In Odoo Apps aktualisieren.
5. Modul **Groundlift Google Analytics Dashboard** installieren.

## Hinweis

Falls das Dashboard leer bleibt oder eine Login-Meldung zeigt, liegt das in der Regel an den Freigabeeinstellungen des Looker-Studio-Reports oder an Browser-/Google-Cookie-Einschränkungen. In diesem Fall den Report in Looker Studio passend freigeben oder den Button „Extern öffnen“ nutzen.
