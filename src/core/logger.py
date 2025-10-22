import logging
import os

try:
    from rich.logging import RichHandler
    from rich.traceback import install as rich_install
    _HAS_RICH = True
except Exception:
    _HAS_RICH = False

try:
    from pythonjsonlogger import jsonlogger
except Exception:
    jsonlogger = None


def setup_logger(name: str = "convo"):
    """
    Controlezi logarea cu variabile de mediu:
      - LOG_LEVEL=DEBUG|INFO|WARNING|ERROR (default INFO)
      - LOG_FORMAT=rich|plain|json (default rich dacă există rich, altfel plain)
      - RICH_WIDTH=120 (opțional)
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt_choice = os.getenv("LOG_FORMAT", "rich" if _HAS_RICH else "plain").lower()

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    if fmt_choice == "json" and jsonlogger:
        handler = logging.StreamHandler()
        handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    elif fmt_choice == "rich" and _HAS_RICH:
        rich_install(show_locals=False, width=int(os.getenv("RICH_WIDTH", "120")), word_wrap=True)
        handler = RichHandler(markup=True, enable_link_path=False, rich_tracebacks=True, show_time=True, show_level=True, show_path=False)
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))

    logger.addHandler(handler)
    logger.propagate = False
    return logger
