# Groundlift Project Showcase 19.0

**Version:** 19.0.1.1.0 · **Plattform:** Odoo 19 SH · **Abhängigkeiten:** `project`, `website`

Eine eigene Ergebnis-Landingpage pro Odoo-Projekt. Entworfen für veranstaltungsbezogene Medien- und Kundenübergaben.

## Funktionsumfang

- Nahtlose Projektverknüpfung: Reiter **Ergebnis-Landingpage** und Smart-Button **Showcase** in der Projektmaske.
- Genau eine Showcase-Konfiguration je Projekt (Odoo-19-`models.Constraint`).
- CI pro Showcase: Logo, Headerbild, Markenname, 4 Schriftstile plus optional hochladbare eigene WOFF2-Schrift, drei HEX-Farben. Die normale Website-CI wird nicht verändert.
- Vimeo-Showcase-URLs und Einzelvideos, inklusive Vimeo-Links mit `h`-Hash für unlisted Videos. **Erst nach Klick** wird Vimeo kontaktiert.
- Dokumente in einem **separaten, explizit freigegebenen Medienbestand**, keine automatische Freigabe von Projektanhängen.
- Vorschau für PDF/JPG/PNG/WebP; Dateien anderer Formate lassen sich nur mit aktiver Downloadfreigabe anbieten.
- Individuelle Downloadfreigabe je Dokument. Ohne Freigabe kein eigener Download-Endpunkt; die browserseitige PDF-Vorschau bleibt technisch kopierbar.
- Responsive Fotogalerie mit Lightbox.
- Zugriff: **privat** (angemeldete interne Odoo-Nutzer mit Projekt-Leserechten), **Kundenlogin** (angemeldeter Kontakt derselben kommerziellen Partnerfirma), **Passwort** (Passworthash, Session, einfaches Versuchslimit) oder **öffentlich**.
- Veröffentlichungsstatus unabhängig von Projektstatus. Nicht veröffentlichte Seiten sind nur für interne Projektbenutzer mit Projektzugriff sichtbar.
- Projektbezogene Regeln auch für Medienmodelle. Öffentlich kein ORM-Zugriff auf Showcase-Modelle.
- Website-Bindung: Showcases werden nur auf ihrer ausgewählten Odoo-Website ausgespielt.
- SEO standardmäßig `noindex`; bei öffentlich sichtbarer Seite optional aktivierbar.
- Konfigurierbare URLs für Impressum und Datenschutz.

## Installation in Odoo.sh

1. Den Ordner `gl_project_showcase/` **unverändert** in das Custom-Addons-Verzeichnis des Odoo.sh-Git-Repositories legen (oder im Repository als Top-Level-Modul ablegen).
2. Commit auf **Development** und Build abwarten; danach in Odoo die App-Liste aktualisieren (Entwicklermodus bei Bedarf).
3. Nach **Groundlift Project Showcase** suchen und installieren. Odoo installiert fehlende Abhängigkeiten `project` / `website`.
4. Alle internen Odoo-Benutzer (`base.group_user`) haben die Berechtigung automatisch. Eine eigene Redaktionsgruppe ist **nicht** erforderlich. Standardmäßige Projektsichtbarkeit und Mandantentrennung bleiben erhalten.
5. Im Projekt über die Aktion **Ergebnis-Landingpage öffnen / anlegen** eine Seite erstellen. Alternativ über **Projekt → Ergebnis-Landingpages** eine vorhandene Seite bearbeiten.
6. Website auswählen, CI/Medien eintragen, Zugriff festlegen. Für passwortgeschützte Seiten zuerst **Zugangspasswort setzen** (mind. 12 Zeichen).
7. Über **Veröffentlichen** aktivieren, den Link aus **Landingpage-URL** verwenden. Erst in Staging mit den Zugriffsarten testen.

**Achtung Odoo-Studio:** Die Projektintegration erbt die Standard-Projektformularansicht `project.edit_project` (in Odoo 19 bestätigt). Bei sehr weitreichenden Studio-Änderungen ggf. die Position des zusätzlichen Reiters überprüfen.

## Sicherheit und Grenzen

- **Nur diese App hochgeladene Medien werden veröffentlicht.** Normale Odoo-Projektanhänge und Aufgaben bleiben unberührt.
- Medien werden ausschließlich durch Controller mit Website-/Rechteprüfung ausgeliefert. Dateiauslieferung mit `Cache-Control: no-store` und `X-Content-Type-Options: nosniff`.
- **„Download deaktiviert“ ist keine DRM-Lösung.** Bei Browseranzeige können Dateien/Pixel prinzipiell kopiert oder per Screenshot gesichert werden; Browser können trotz `#toolbar=0` eigene Speichern-Funktionen zeigen. Für vertrauliche Dokumente empfiehlt sich eine Wasserzeichen-/Preview-Only-Strategie und rechtliche Zugriffskontrolle.
- Die integrierte Vorschau kann **keine Word-/Excel-/PowerPoint-Dateien rendern**. Für diese Formate erst in PDF exportieren oder Download aktivieren. Office-Dateien sind keine automatisch öffentlichen Vorschauen.
- Passwortschutz ist für geteilte Kundenlinks gedacht; die einfache per-Session-Drosselung ersetzt kein IP-basiertes Rate-Limiting via Reverse Proxy/WAF. Für besonders sensible Daten ist `private` oder `customer` mit Odoo-Login besser.
- Die Kundenlogin-Regel gewährt Mitgliedern derselben **kommerziellen Partnerorganisation** Zugang (nicht nur dem einzelnen Projektkontakt). Für noch engeren Zugang ist eine eigene Partner-Whitelist sinnvoll.
- Vimeo-Showcases und private/unlisted Vimeo-Videos unterliegen **zusätzlich** ihren Vimeo-Domain-/Embed-Einstellungen; nicht jedes private Video lässt sich einbetten.
- Impressum/Datenschutzlinke und eine korrekte Datenschutzinformation zur Vimeo-Einbindung müssen vom Betreiber eingestellt bzw. geprüft werden.
- Durch Website-Bindung sollten die Odoo-Website-Domains korrekt konfiguriert werden. Bei mehreren Odoo-Websites jede Domain testen.

## Technische Abnahme (Staging)

- Ein Testprojekt anlegen, Showcase erstellen, CI/Fotos/Videos/PDF hinterlegen und veröffentlichen.
- Ohne Login die private Seite und alle Medienendpunkte prüfen → keine Einsicht.
- Passwortseite im Inkognito-Modus: ohne/falsches Passwort kein Zugriff; nach korrektem Passwort Medien sichtbar. Passwortänderung invalidiert alte Zugriffssitzungen.
- Dateivorschau/Download: bei `allow_download=False` gibt `?download=1` einen 404 zurück; mit `True` ist Download erlaubt.
- Wechsel auf unveröffentlicht → kein Zugriff ohne Editorrechte, auch nicht auf direkte Medien-URLs.
- Screenshot/Browser-Save-Möglichkeiten zeigen die beschriebene technische Limitierung.
- Gleiche Seite auf anderer Website-Domain → 404.
- Projektfremde Mitarbeiter und Portalbenutzer prüfen; besonders in Multi-Company-Datenbanken.
- PDF/Word/hochaufgelöste Fotos, mobile Browser und Vimeo-Privacy testen.

## Entwicklernotiz

Es wurde eine statische Syntax-/XML-Prüfung im Generierungscontainer durchgeführt. **Ein vollständiger Odoo-19-Laufzeittest auf eurer SH-Datenbank war nicht möglich**, da hier keine Odoo-Instanz verfügbar ist. Bitte zuerst in `dev`/`staging` installieren; bei einem abweichenden Projektformular oder kundenspezifischen Regeln kann eine Anpassung erforderlich sein.

## Update von Version 1.0 auf 1.1

- Bestehenden Modulordner `gl_project_showcase` durch diesen ersetzen (nicht parallel installieren).
- In Odoo.sh pushen / Build abwarten. Im Apps-Menü **Groundlift Project Showcase → Upgrade** ausführen. Ein Git-Push allein aktualisiert die `ir.ui.view`-, `ir.rule`- und ACL-Datensätze nicht.
- Browser neu laden (Strg+F5), ein vorhandenes Projekt **über seine Einstellungen/Formularansicht** öffnen; nicht nur Aufgabenübersicht. Dort sind der Reiter und der Smart-Button.
- `Project Showcase: Redaktion` wird nicht mehr benötigt; eventuell aus früherer Installation verbliebene Gruppe kann ignoriert werden.
- Der Projekt-Hauptmenüpunkt von Odoo ist standardmäßig weiterhin nur für Projektbenutzer/Projektleiter sichtbar. Diese App verändert die Projekt-Hauptmenüberechtigung nicht. Wenn Mitarbeiter ihre Projekte bereits über Odoo aufrufen können, sehen sie den Showcase-Reiter.
