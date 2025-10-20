import logging
try:
    import coloredlogs
except Exception:
    coloredlogs = None

def setup_logger(name: str = "convo"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
        if coloredlogs:
            coloredlogs.install(level="INFO", logger=logger, fmt=fmt)
    return logger
