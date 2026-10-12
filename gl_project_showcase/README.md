# Groundlift Project Showcase – Odoo 19 SH (Version 1.4)

## Neues in Version 1.4 (Fix von 1.3)

- **PDF-/Dateiupload:** Computed MIME-Typen und Uploadvalidierung lesen Binärfelder mit `bin_size=False` und `bin_size_<feld>=False`, damit Odoo-Formulargrößenangaben nicht irrtümlich als Base64-Inhalt dekodiert werden.
- **Robuste Kodierung:** Zulässige Zeilenumbrüche und Leerzeichen in Base64-Payloads werden vor der Prüfung entfernt; ungültige Base64-Daten und Dateien über 40 MB werden weiter abgelehnt.
- **Alle Medien:** Derselbe Binärzugriff wird bei Galerie-Bild- und eigener WOFF2-Schrift-Prüfung verwendet.
- **Videoeditor breiter:** Dokumentliste aus der schmalen `<group>` entfernt. Das modalspezifische Backend-CSS erweitert den Video-Dialog auf Desktops auf bis zu 1400px; andere Dialoge bleiben unverändert.
- **Rückwärtskompatibilität:** Keine geänderten Feldnamen/Relationen; existierende Daten bleiben erhalten. Regeltabellen und öffentliche URLs sind unverändert.
- **Tests:** Regressionstest für `bin_size`-Kontexte sowie Base64-Zeilenumbrüche, zusätzlich lokale Syntax-/XML-Strukturprüfungen. Ein realer Odoo.sh-Upgrade-Test ist weiterhin erforderlich.

### Upgrade v1.3 → v1.4

1. Bestehenden Modulordner `gl_project_showcase` **vollständig ersetzen** (nicht zusätzlich hineinkopieren).
2. Änderungen nach Odoo.sh **Development/Staging** pushen; nach erfolgreichem Build in **Apps → Groundlift Project Showcase → Aktualisieren** das Modul-Upgrade ausführen.
3. Browser hart neu laden (Strg+F5), da das Backend-CSS neu eingebunden wird.
4. PDF mit deaktiviertem Download und PDF mit aktiviertem Download jeweils in einem Video und im Dokumententab hochladen; Vorschau und Downloadfreigaben prüfen.
5. Test mit JPG/PNG, Office-Datei (Download erlaubt) und großer Dateiliste durchführen. Erst danach Production aktualisieren.

## Neues in Version 1.3 (Upgrade von 1.2)

### 1. Dateien direkt an Vimeo-Videos anheften

- Unter **Vimeo-Showreel & Videos** Video anklicken; im Videoformular den Bereich **Dateien zu diesem Video** öffnen und PDFs/Bilder bzw. zum Download freigegebene Dateien hinzufügen.
- Alternativ im Tab **Dokumente** das Feld **Zugeordnetes Video** auswählen.
- Ein Dokument gehört höchstens zu **einem** Video und bleibt im zentralen Dokumenten-Tab sichtbar.
- Auf der Landingpage erscheint ein zugeordnetes Dokument mit Vorschau und seinem individuellen Downloadrecht **direkt unter dem Video**; nicht zugeordnete Dokumente bleiben im allgemeinen Bereich **Dokumente**.
- Ein Video kann beliebig viele Dokumente haben. Zuordnungen zu Videos eines anderen Showcases werden serverseitig abgelehnt.

### 2. Fotogalerie mit Tags und Überschriften

- Im Tab **Galerie-Überschriften** die gewünschten Tag-/Gruppennamen anlegen, z. B. Aufbau, Show, Backstage. Reihenfolge über den Griff einstellen.
- Im Tab **Fotogalerie** pro Bild einen oder mehrere **Galerie-Tags** auswählen (auch neue Tags können aus dem Auswahlfeld angelegt werden).
- Auf der öffentlichen/geschützten Landingpage werden nur befüllte Gruppen angezeigt, mit Tag-Namen als Abschnittsüberschrift und Bildern im bestehenden Grid/Lightbox-Design.
- Ein Foto kann in **mehreren** Gruppen vorkommen. Nicht getaggte Bilder erscheinen am Schluss unter **Weitere Fotos**; wenn gar keine Tags verwendet werden, bleibt die ursprüngliche einfache Galerie ohne zusätzliche Überschrift erhalten.
- Gruppierung ist auf das jeweilige Projekt-Showcase begrenzt. Tags eines anderen Projekts können nicht zugewiesen werden.

### Datenbestand & Berechtigung

- V1.3 ergänzt nur neue Datenbankfelder und das Galerie-Tag-Modell. Bestehende Videos, Dokumente, Bilder, URLs und Veröffentlichungseinstellungen werden nicht gelöscht.
- Für bestehende Daten bleibt die bisherige Darstellung erhalten: Dokumente ohne Videolink liegen im allgemeinen Bereich; Fotos ohne Tags bleiben in einer Galerie.
- Alle internen Odoo-Nutzer mit Projektzugriff behalten den Showcase-Reiter. Portal-/Kundenbenutzer bekommen keine neuen Bearbeitungsrechte.
- Dateien werden weiterhin nur über die expliziten Showcase-Routen mit Veröffentlichungs- und Zugriffsprüfung ausgeliefert.
- „Download nicht erlaubt“ bedeutet weiterhin Verzicht auf einen Download-Button – kein technischer Vollschutz gegen Speichern des im Browser angezeigten Inhalts.

### Upgrade in Odoo.sh

1. Vorhandenen Modulordner `gl_project_showcase` vollständig durch den Inhalt der ZIP ersetzen, keine Ordner doppelt ineinander verschachteln.
2. Push nach **Development**, dort **Apps → Groundlift Project Showcase → Aktualisieren (Upgrade)** ausführen. Ein bloßer Git-Push aktualisiert weder Views noch Datenbankschema.
3. Bestehendes Projekt öffnen → Ergebnis-Landingpage → Video anklicken und Datei zuordnen; Galerie-Überschriften anlegen und Bilder taggen.
4. Link zur Landingpage überprüfen, auch ausgeloggt und mit einem Kunden-Zugang, sowie Downloads zugelassen/gesperrt testen.
5. Nach erfolgreichem Staging-Test nach Production übernehmen.

**Validierung:** Python-Syntax und XML-Parsing können lokal geprüft werden. Ein vollständiger Odoo.sh-Modultest muss in der realen Umgebung erfolgen.

---

# Groundlift Project Showcase 19.0

**Version:** 19.0.1.4.0 · **Plattform:** Odoo 19 SH · **Abhängigkeiten:** `project`, `website`

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

## Korrektur Version 1.2

Der zusätzliche XML-Datensatz `menu_gl_project_showcase` aus Version 1.1 verwendete
noch `ir.ui.menu.groups_id`. In Odoo 19 wurde dieses Menü-Feld auf `group_ids`
umbenannt. Dies führte beim Installieren/Aktualisieren zum Parse-/Ladefehler.
Die v1.2 stellt auf `<field name="group_ids" .../>` um.

Die bestehende Odoo-Gruppe `base.group_user` bleibt der Berechtigungsträger;
keine manuelle Benutzerzuordnung. Die getrennten `ir.rule`-Felder heißen
in Odoo 19 weiterhin `groups` und wurden **nicht** geändert.

Für ein reguläres Upgrade einfach den Modulordner ersetzen; Modul muss
in der betroffenen Datenbank installiert/aktualisiert werden.
