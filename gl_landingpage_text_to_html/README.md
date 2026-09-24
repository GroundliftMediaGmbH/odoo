# Landingpage Text_to_HTML — Odoo 19 SH (Fix 19.0.1.1.0)

## Was in Version 1.1 behoben ist

In Version 1 war das neue `gl_landingpage_html` nur an **eine**
Standard-Odoo-Vorlage gebunden. Andere Odoo-Eventansichten zeigen oft das
native Feld `event.event.description`, und eine unabhängig gehostete
Groundlift-PHP-Website verwendet ihre eigene Ausgabe. Deshalb wurde HTML im
Backend gespeichert, ohne überall auf der Website sichtbar zu werden.

Version 1.1 verbindet `gl_landingpage_html` zusätzlich mit der nativen
Odoo-Webseitenbeschreibung `event.event.description` und synchronisiert
Website-Editor-Änderungen zurück. Das ursprüngliche Studio-Textfeld bleibt
unverändert erhalten (selber technischer Name, Typ `text`). Ein API-Endpunkt
stellt die formatierte HTML-Beschreibung einer **veröffentlichten** Veranstaltung
für die externe PHP-Website bereit. Die PHP-Datei muss diesen Endpunkt explizit
verwenden; das kann ein Odoo-Modul allein nicht automatisch tun.

## Installation / UPDATE (nicht erneut als neues Modul installieren)

1. Den ganzen bestehenden Ordner `gl_landingpage_text_to_html` in GitHub durch
   den gleichnamigen Ordner aus diesem ZIP ersetzen. Er muss im Addons-Suchpfad
   liegen; **nicht** beide Versionen gleichzeitig ablegen.
2. Änderungen zuerst in den Odoo.sh-Staging-Branch pushen und Build abwarten.
3. **Apps → App-Liste aktualisieren → Landingpage Text_to_HTML → Upgrade/Aktualisieren.**
   Push/Server-Neustart allein führt die XML- und Daten-Migration nicht aus.
4. Version `19.0.1.1.0` im Modul bestätigen.
5. Event-Formular → `Landingpage HTML` öffnen, fett und Link testen. Auf der
   **Odoo-gehosteten** `/event/...`-Seite auf `Bearbeiten` klicken, im Textbereich
   formatieren, speichern, Backend gegenprüfen.

Die Upgrade-Migration übernimmt bereits vorhandenes HTML und verknüpft die
native Odoo-Beschreibung **nur**, wenn sie leer oder textlich identisch ist.
Unabhängige vorhandene native Odoo-Beschreibungen werden NICHT überschrieben.
In solchen Fällen steht im Reiter ein Button zum bewussten Sichern und Ersetzen.

## Synchronisierungsregel

* HTML-Feld geändert → altes Studio-Textfeld erhält Klartext; die native
  Webseitenbeschreibung erhält HTML, wenn verbunden.
* Altes Studio-Textfeld geändert → HTML-Fassung wird aus Klartext neu gebaut.
  Bereits hinzugefügte Formatierungen gehen dabei bewusst verloren.
* Native Odoo-Webseitenbeschreibung **direkt auf der Website** geändert →
  HTML-Fassung und Klartext werden aktualisiert, sofern verbunden.
* Ist eine vorhandene native Beschreibung **anders**, bleibt sie zunächst
  unabhängig. Im Reiter `Landingpage HTML` kann sie gesichert und ausdrücklich
  durch den formatierten Text ersetzt werden. Die Sicherung steht Administratoren
  dort zur Verfügung.

**Achtung:** Die native `event.description` ist ein vorhandenes Odoo-Feld;
dieses Modul ändert seine Inhalte, wenn es verbunden ist. Ein Staging-Backup
vor dem Upgrade ist wichtig.

## Altes Textfeld erkennen

Wie in Version 1: Systemparameter
`gl_landingpage_text_to_html.source_field` = technischer Feldname des bereits
vorhandenen **event.event**-Textfeldes (z. B. `x_studio_...`). Es wird nur
getextet/geschrieben, niemals umbenannt oder umdefiniert. Ohne eindeutiges
Feld bleibt die Synchronisation deaktiviert, statt ein fremdes Feld zu ändern.

## Welche Website ist gemeint?

### A. Odoo-gehostete `/event/...`-Seite

Hier funktioniert das Odoo-Website-Frontend mit einem `t-field` und dem
nativen HTML-Feld `event.description` nach Upgrade und erfolgreicher Verknüpfung.
Andere individuell abgeänderte QWeb-Ansichten können zusätzliche Anpassungen
brauchen, wenn sie weiterhin das alte Studio-Textfeld explizit ausgeben.

### B. `groundlift.de` (PHP / anderer Webserver)

**Nicht mit dem Odoo Website-Editor auf der PHP-Seite bearbeitbar.** Die
Bearbeitung findet im Odoo-Backend oder auf der Odoo-gehosteten Eventseite
statt. Die Darstellung auf `groundlift.de` muss aus HTML gespeist werden;
dafür stellt dieses Modul einen öffentlichen, auf veröffentlichte Events
beschränkten Fragment-Endpunkt bereit:

    https://DEINE-ODOO-DOMAIN/gl/landingpage/event/60/description.html

Er liefert *nur HTML*, keine ganze Seite. Unveröffentlichte Events → 404.

PHP-Beispiel für eine eigene Event-Detailseite (nur als Vorlage, NICHT
automatisch in die vorhandene Groundlift-Datei integriert):

```php
<?php
$odooId = (int) $event['odoo_id']; // Feldname an eure Datenstruktur anpassen
$url = 'https://DEINE-ODOO-DOMAIN/gl/landingpage/event/' . $odooId . '/description.html';
$curl = curl_init($url);
curl_setopt_array($curl, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 5,
    CURLOPT_CONNECTTIMEOUT => 2,
]);
$html = curl_exec($curl);
$status = curl_getinfo($curl, CURLINFO_HTTP_CODE);
curl_close($curl);
if ($status === 200 && $html !== false) {
    // Die Antwort ist Odoo-sanitisiertes HTML; NICHT htmlspecialchars($html).
    echo '<div class="event-description">' . $html . '</div>';
} else {
    // Bestehendes Verhalten bei Netzwerk-/API-Fehlern beibehalten.
    echo nl2br(htmlspecialchars($event['description'] ?? '', ENT_QUOTES, 'UTF-8'));
}
?>
```

Eine bestehende PHP-Seite muss im Original geprüft werden, um ihren
Event-ID-Abgleich, Caching und Fallback korrekt zu berücksichtigen.
Insbesondere funktioniert dies nicht, wenn PHP den HTML-Fragmente-Text
nachträglich mit `htmlspecialchars()` oder `strip_tags()` entformatiert.

## Abnahme auf Staging

1. Bekanntes Event mit Quelltext/HTML öffnen; Fettschrift/Link im HTML-Feld
   speichern. Das ursprüngliche Klartextfeld enthält weiter nur Text.
2. Prüfen: `Mit Odoo-Webseitenbeschreibung verbunden` ist aktiv; andernfalls
   den unabhängigen nativen Inhalt prüfen und bei Bedarf *bewusst* ersetzen.
3. Odoo-Eventseite anzeigen; Fett und Link werden dargestellt.
4. Auf der **Odoo-Eventseite** `Bearbeiten` → Text bearbeiten → speichern; das
   Backend-HTML spiegelt die Änderung.
5. Falls `groundlift.de` verwendet wird: Fragment-URL zuerst im Browser
   testen; danach den PHP-Renderer ergänzen und erneut testen.
6. Eine zweite Veranstaltung und unveröffentlichte Veranstaltung testen.

Nicht live auf Production ohne Freigabe aus Staging ausrollen.
