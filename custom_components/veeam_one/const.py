"""Constants for the Veeam ONE integration."""

DOMAIN = "veeam_one"
DEFAULT_NAME = "Veeam ONE"
CONF_VERIFY_SSL = "verify_ssl"
DEFAULT_PORT = 1239
DEFAULT_VERIFY_SSL = True
API_VERSION = "2.3"
UPDATE_INTERVAL = 60
UPDATE_TIMEOUT = 180
PAGE_LIMIT = 10000
# Veeam ONE answers every collection from one database; don't fire ~50 queries at it at once.
MAX_CONCURRENT_REQUESTS = 6

SERVICE_RESOLVE_ALARM = "resolve_alarm"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ALARM_IDS = "alarm_ids"
ATTR_COMMENT = "comment"
DEFAULT_RESOLVE_COMMENT = "Resolved from Home Assistant"
