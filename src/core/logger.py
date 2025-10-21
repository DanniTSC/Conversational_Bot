import logging
import os
try:
    import coloredlogs
except Exception:
    coloredlogs = None
try:
    from pythonjsonlogger import jsonlogger
except Exception:
    jsonlogger = None

def setup_logger(name: str = "convo"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        if os.getenv("LOG_FORMAT", "").lower() == "json" and jsonlogger:
            fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
            handler.setFormatter(jsonlogger.JsonFormatter(fmt))
        else:
            fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
            handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
        if coloredlogs:
            coloredlogs.install(level="INFO", logger=logger, fmt=fmt)
    return logger
