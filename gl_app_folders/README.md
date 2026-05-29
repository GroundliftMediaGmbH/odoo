# Groundlift App-Folders Desktop für Odoo 19 SH

Dieses Modul stellt einen persönlichen Odoo-Desktop als Client Action bereit.
Jeder interne Benutzer kann eigene Ordner anlegen, benennen, mit einem Icon versehen und Odoo-Apps per Drag & Drop hineinlegen.

## Bedienung

1. App **Mein Desktop** öffnen.
2. **Neuer Ordner** klicken und Bezeichnung/Icon vergeben.
3. Apps per Drag & Drop auf einen Ordner ziehen.
4. Eine App auf eine andere App ziehen, um direkt einen neuen Ordner mit beiden Apps zu erzeugen.
5. Ordner öffnen, um Bezeichnung/Icon zu ändern, Apps zu entfernen oder den Ordner zu löschen.
6. Optional **Als Startseite setzen** klicken. Dadurch wird die Home Action des aktuellen Benutzers auf diesen Desktop gesetzt.

## Installation auf Odoo.sh

1. Ordner `gl_app_folders` in dein Custom-Addons-Repository legen.
2. Committen und auf den gewünschten Odoo.sh-Branch pushen.
3. Build abwarten.
4. In Odoo Apps-Liste aktualisieren.
5. Modul **Groundlift App-Folders Desktop** installieren.

## Technischer Ansatz

Das Modul patcht nicht den Enterprise-HomeMenu-Code, sondern legt eine eigene stabile OWL-Client-Action an.
Das ist für Odoo.sh deutlich update-sicherer. Über den Button **Als Startseite setzen** kann jeder Benutzer diese Client Action individuell als persönliche Home Action setzen.
