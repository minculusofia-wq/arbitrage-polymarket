import logging
import sys
from logging.handlers import RotatingFileHandler
import os

# Create logs directory if it doesn't exist
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger(name="ArbitrageBot", log_file="bot.log", level=logging.INFO):
    """
    Sets up a configured logger with file and console handlers.
    """
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if already setup
    if logger.hasHandlers():
        return logger

    # Rotating File Handler (10MB per file, max 5 backups)
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_file), 
        maxBytes=10*1024*1024, 
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# Default logger instance
logger = setup_logger()
