import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Initial one-time cleanup: German is used as source for existing events."""
    installed_languages = {
        code for code, _name in env["res.lang"].get_installed()
    }

    if "de_DE" not in installed_languages:
        _logger.warning(
            "Groundlift Event Language Sync installed, but de_DE is not an installed language. "
            "Existing events were not synchronized."
        )
        return

    events = env["event.event"].sudo().with_context(active_test=False).search([])
    _logger.info(
        "Groundlift Event Language Sync: synchronizing %s existing event(s) from de_DE to en_US.",
        len(events),
    )

    for event in events:
        event._groundlift_sync_existing_event_from_german()
