import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # The 1.6 ticket rewrite was withdrawn in 1.7. The method it called no
    # longer exists; do not rewrite historical ticket net prices on upgrades.
    _logger.info("GL gross: obsolete 1.6 ticket rewrite skipped")
