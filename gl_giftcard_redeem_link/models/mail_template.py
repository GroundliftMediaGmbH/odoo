import re

from odoo import models


_REDEEM_URL = "https://groundlift.de/public-events.php"

# The standard Odoo 19 gift-card template renders
# {{ object.get_base_url() }}/shop into an absolute /shop URL.
# We change only href attributes that end at /shop (optionally with
# slash/query/fragment) and only for loyalty.mail_template_gift_card.
_SHOP_HREF_RE = re.compile(
    r"(?P<prefix>\\bhref\\s*=\\s*[\\\"'])"
    r"https?://[^\\\"']+/shop(?:[/?#][^\\\"']*)?"
    r"(?P<suffix>[\\\"'])",
    flags=re.IGNORECASE,
)


class MailTemplate(models.Model):
    _inherit = "mail.template"

    def _generate_template(
        self,
        res_ids,
        render_fields,
        recipients_allow_suggested=False,
        find_or_create_partners=False,
    ):
        values_by_res_id = super()._generate_template(
            res_ids,
            render_fields,
            recipients_allow_suggested=recipients_allow_suggested,
            find_or_create_partners=find_or_create_partners,
        )

        gift_card_template = self.env.ref(
            "loyalty.mail_template_gift_card",
            raise_if_not_found=False,
        )
        if not gift_card_template or self.id != gift_card_template.id:
            return values_by_res_id

        for values in values_by_res_id.values():
            body_html = values.get("body_html")
            if not body_html:
                continue

            values["body_html"] = _SHOP_HREF_RE.sub(
                lambda match: (
                    f"{match.group('prefix')}{_REDEEM_URL}{match.group('suffix')}"
                ),
                str(body_html),
            )

        return values_by_res_id
