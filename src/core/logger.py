import logging, os, sys
from logging.handlers import RotatingFileHandler

TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")

def _trace(self, msg, *args, **kwargs):
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, msg, args, **kwargs)

logging.Logger.trace = _trace  # type: ignore[attr-defined]

class _Color:
    MAP = {
        "TRACE": "\033[38;5;244m",
        "DEBUG": "\033[36m",
        "INFO":  "\033[32m",
        "WARNING":"\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL":"\033[35m",
    }
    END = "\033[0m"

class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname
        color = _Color.MAP.get(level, "")
        end = _Color.END if color else ""
        record.levelname = f"{color}{level}{end}"
        return super().format(record)

def _parse_level(name: str) -> int:
    name = (name or "").upper().strip()
    return {
        "TRACE": TRACE_LEVEL, "DEBUG": logging.DEBUG, "INFO": logging.INFO,
        "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL
    }.get(name, logging.INFO)

def setup_logger(name: str = "bot"):
    level = _parse_level(os.getenv("LOG_LEVEL", "INFO"))

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%H:%M:%S"

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(ColorFormatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(ch)

    # File (rotativ), dacă vrei log pe disc
    log_dir = os.getenv("LOG_DIR", "").strip()
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(os.path.join(log_dir, "app.log"), maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
        logger.addHandler(fh)

    logger.debug("Logger ready (level=%s)", logging.getLevelName(level))
    return logger
