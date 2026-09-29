"""Constants for the Veeam ONE integration."""

DOMAIN = "veeam_one"
DEFAULT_NAME = "Veeam ONE"
CONF_VERIFY_SSL = "verify_ssl"
CONF_API_VERSION = "api_version"
DEFAULT_PORT = 1239
DEFAULT_VERIFY_SSL = True
# "Use the newest version the server serves", re-resolved on every setup so a server upgrade
# or a newer veeam-one is picked up without editing the entry.
AUTO_API_VERSION = "auto"
# Used when detection finds nothing, e.g. behind a proxy that rewrites statuses
DEFAULT_API_VERSION = "2.3"
CONNECT_TIMEOUT = 60
REQUEST_TIMEOUT = 30.0
UPDATE_INTERVAL = 60
UPDATE_TIMEOUT = 180
PAGE_LIMIT = 10000
# Veeam ONE answers every collection from one database; don't fire ~50 queries at it at once.
MAX_CONCURRENT_REQUESTS = 6
# Raise a repair issue this many days before the Veeam ONE license expires
LICENSE_WARNING_DAYS = 30

SERVICE_RESOLVE_ALARM = "resolve_alarm"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ALARM_IDS = "alarm_ids"
ATTR_COMMENT = "comment"
DEFAULT_RESOLVE_COMMENT = "Resolved from Home Assistant"
