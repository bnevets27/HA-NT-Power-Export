DOMAIN = "ntpower"

CONF_ACCOUNT_ID = "account_id"
CONF_SERVICE_ID = "service_id"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_STATISTIC_ID = "statistic_id"
CONF_UNIT = "unit"
CONF_TIMEZONE = "timezone"
CONF_BASE_URL = "base_url"
CONF_PORTAL_ORIGIN = "portal_origin"

# Optional overrides / advanced
CONF_START_DATE = "start_date"       # YYYY-MM-DD
CONF_END_DATE = "end_date"           # YYYY-MM-DD (exclusive midnight local)
CONF_INITIAL_SUM = "initial_sum"     # float baseline meter reading
CONF_FULL_HISTORY = "full_history"   # bool
CONF_STATE_STORE = "state_store"     # path for persistence JSON
CONF_RESET_BASELINE = "reset_baseline"  # bool
CONF_CONTINUE_FROM_TSV = "continue_from_tsv"  # path to previous TSV to seed baseline
