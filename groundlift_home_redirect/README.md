# Groundlift Homepage Redirect – Odoo 19

Dieses Modul leitet ausschließlich die öffentliche Odoo-Startseite

`https://groundlift.odoo.com/`

auf

`https://groundlift.de/`

weiter.

## Was wird umgeleitet?

Nur der exakte Pfad `/` wird mit einem HTTP-302-Redirect umgeleitet.

Nicht betroffen sind unter anderem:

- das Odoo-Backend unter `/odoo`;
- die Anmeldung unter `/web/login`;
- Veranstaltungsseiten unter `/event/...`;
- Ticket- und Registrierungsseiten;
- Shop-, Portal- und sonstige Unterseiten;
- die Odoo-Website-Vorschau und der Website-Editor.

## Warum bleibt die Odoo-Vorschau erhalten?

Odoo lädt die Website im Backend innerhalb eines iframe. Eine Weiterleitung
dieses iframe auf eine andere Domain würde den Website-Builder durch die
Cross-Origin-Sicherheitsregeln des Browsers beschädigen. Das Modul erkennt
Editor- und authentifizierte iframe-Aufrufe und zeigt dort weiterhin die
normale Odoo-Startseite an.

## Installation auf Odoo.sh

1. Den Ordner `groundlift_home_redirect` in das GitHub-Repository kopieren.
2. Committen und auf den gewünschten Odoo.sh-Branch pushen.
3. Den erfolgreichen Odoo.sh-Build abwarten.
4. In Odoo **Apps** öffnen.
5. Den Filter **Apps** entfernen, falls das Modul nicht angezeigt wird.
6. Nach **Groundlift Homepage Redirect** suchen und das Modul installieren.
7. `https://groundlift.odoo.com/` in einem privaten Browserfenster testen.

## Hinweis zum Redirect

Das Modul verwendet absichtlich einen temporären HTTP-302-Redirect. Dadurch
wird die Weiterleitung nicht so aggressiv im Browser zwischengespeichert wie
ein permanenter HTTP-301-Redirect und kann bei Bedarf leichter geändert oder
entfernt werden.
