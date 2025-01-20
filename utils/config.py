# utils/config.py
import logging

# Logging levels
LOG_LEVEL = logging.INFO  # Default logging level

# logging.DEBUG: Show all messages (debug, info, warning, error, critical).
# logging.INFO: Show info, warning, error, and critical messages.
# logging.WARNING: Show warning, error, and critical messages.
# logging.ERROR: Show error and critical messages.
# logging.CRITICAL: Show only critical messages.

# Logging format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Logging configuration
def setup_logging():
    logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)