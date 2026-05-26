# Technische Hinweise

## Datenmodelle

- `gl.cleverreach.newsletter.config`: globale Konfiguration und API-Zugang.
- `gl.cleverreach.group`: importierte CleverReach-Gruppen/Empfängerlisten.
- `gl.cleverreach.newsletter.template`: austauschbare HTML-Vorlagen.
- `gl.cleverreach.event.queue`: Events, die in „Angekündigt“ verschoben wurden.
- `gl.cleverreach.newsletter.job`: erzeugte Newsletter-Aufträge.

## Cronjobs

- `Groundlift CleverReach: neue angekündigte Events prüfen`: alle 15 Minuten, läuft erst ab lokaler Erstellungsstunde.
- `Groundlift CleverReach: 14-tägigen Eventnewsletter prüfen`: alle 15 Minuten, läuft erst ab lokaler Erstellungsstunde.
- `Groundlift CleverReach: Newsletter-Watchdog`: stündlich.
- `Groundlift CleverReach: fällige Newsletter versenden`: alle 5 Minuten, verschickt in Odoo fällige Newsletter per CleverReach-Sofortversand.

## Erweiterungspunkte

Die wichtigste Stelle für CleverReach-Payload-Anpassungen ist:

```python
CleverReachNewsletterJob._cleverreach_create_mailing()
CleverReachNewsletterJob._cleverreach_send_mailing_now()
```

CleverReach wird nicht mehr für zukünftige Terminierung genutzt. Falls CleverReach für euren Account einen anderen Endpoint für Sofortversand erwartet, muss nur dort die Payload bzw. der Endpoint ergänzt werden.
