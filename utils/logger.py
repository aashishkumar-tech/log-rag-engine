# utils/logger.py
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

# Env vars (optional):
# LOG_LEVEL=DEBUG|INFO|... (already used)
# LOG_TO_FILE=1 to enable file logging
# LOG_DIR=logs (default)
# LOG_FILE=app.log (default when not daily)
# LOG_MAX_BYTES=1048576 (1MB default)
# LOG_BACKUPS=5 (rotation backups)
# LOG_DAILY=1 create new file per UTC day named YYYY-MM-DD-<LOG_BASE>.log
# LOG_BASE=app base name used when LOG_DAILY=1

def _maybe_add_file_handler(logger: logging.Logger):
    if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        return
    if os.getenv("LOG_TO_FILE", "0") != "1":
        return
    log_dir = os.getenv("LOG_DIR", "logs")
    daily = os.getenv("LOG_DAILY", "0") == "1"
    if daily:
        base = os.getenv("LOG_BASE", "app")
        log_file = f"{datetime.utcnow().strftime('%Y-%m-%d')}-{base}.log"
    else:
        log_file = os.getenv("LOG_FILE", "app.log")
    max_bytes = int(os.getenv("LOG_MAX_BYTES", str(1 * 1024 * 1024)))
    backups = int(os.getenv("LOG_BACKUPS", "5"))
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, log_file)
    fh = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding='utf-8')
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)


def get_logger(name: str, level_str: str = None):
    level_str = level_str or os.getenv("LOG_LEVEL", "DEBUG")
    level = LEVELS.get(level_str.upper(), logging.DEBUG)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    _maybe_add_file_handler(logger)
    return logger


def log_startup_summary(logger: logging.Logger):
    logger.info(
        "Startup configuration: level=%s file_logging=%s daily=%s backend=%s async_build=%s persist_disabled=%s", 
        os.getenv("LOG_LEVEL", "DEBUG"),
        os.getenv("LOG_TO_FILE", "0"),
        os.getenv("LOG_DAILY", "0"),
        os.getenv("EMBED_BACKEND", "hf"),
        os.getenv("ASYNC_BUILD", "1"),
        os.getenv("DISABLE_PERSIST", "0")
    )
