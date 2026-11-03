import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

SYNC_CONTEXT_KEY = "groundlift_event_language_sync_running"
GERMAN_LANG = "de_DE"
ENGLISH_LANG = "en_US"
SYNC_LANGS = {GERMAN_LANG, ENGLISH_LANG}


class EventEvent(models.Model):
    _inherit = "event.event"

    @api.model
    def _groundlift_translation_sync_fields(self):
        """Return all writable, stored translated fields on event.event.

        The list is built dynamically from the live registry. This means it also
        covers translated fields added later by other modules or Odoo Studio.
        Non-stored fields and computed fields without an inverse are excluded,
        because they cannot safely be written back.
        """
        result = set()
        for name, field in self._fields.items():
            if not field.translate or not field.store:
                continue
            if field.related:
                # Writing a related field could modify a different model.
                continue
            if field.compute and not field.inverse:
                # Pure computed fields must never be force-written.
                continue
            result.add(name)
        return result

    @api.model
    def _groundlift_current_language(self):
        return self.env.context.get("lang") or self.env.user.lang or ENGLISH_LANG

    def _groundlift_mirror_translated_values(self, values, source_lang):
        """Mirror translated values from DE to EN or EN to DE.

        German and English are intentionally treated as two views of the same
        event content. Therefore an edit made while either language is active is
        copied to the other language as well.
        """
        if source_lang not in SYNC_LANGS:
            return

        translated_fields = self._groundlift_translation_sync_fields()
        mirror_values = {
            name: value
            for name, value in values.items()
            if name in translated_fields
        }
        if not mirror_values:
            return

        target_lang = ENGLISH_LANG if source_lang == GERMAN_LANG else GERMAN_LANG
        _logger.debug(
            "Groundlift event language sync: mirroring fields %s from %s to %s for event ids %s",
            sorted(mirror_values),
            source_lang,
            target_lang,
            self.ids,
        )

        self.with_context(
            **{
                "lang": target_lang,
                SYNC_CONTEXT_KEY: True,
            }
        ).write(mirror_values)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        if self.env.context.get(SYNC_CONTEXT_KEY):
            return records

        source_lang = self._groundlift_current_language()
        if source_lang in SYNC_LANGS:
            for record, values in zip(records, vals_list, strict=True):
                record._groundlift_mirror_translated_values(values, source_lang)

        return records

    def write(self, vals):
        if self.env.context.get(SYNC_CONTEXT_KEY):
            return super().write(vals)

        source_lang = self._groundlift_current_language()
        result = super().write(vals)

        if source_lang in SYNC_LANGS:
            self._groundlift_mirror_translated_values(vals, source_lang)

        return result

    def _groundlift_sync_existing_event_from_german(self):
        """Make the English translation equal to the current German values."""
        self.ensure_one()

        field_names = self._groundlift_translation_sync_fields()
        if not field_names:
            return

        german_record = self.with_context(lang=GERMAN_LANG)
        values = {name: german_record[name] for name in field_names}

        self.with_context(
            **{
                "lang": ENGLISH_LANG,
                SYNC_CONTEXT_KEY: True,
            }
        ).write(values)
