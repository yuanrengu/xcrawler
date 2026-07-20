from __future__ import annotations

import logging

LOGGER_NAME = "xcrawler"
_HANDLER_MARKER = "_xcrawler_cli_handler"


def configure_logging(*, verbose: bool = False) -> None:
    """Configure package diagnostics without changing third-party log levels."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.propagate = False

    handler = next(
        (item for item in logger.handlers if getattr(item, _HANDLER_MARKER, False)),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        setattr(handler, _HANDLER_MARKER, True)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
