#!/usr/bin/with-contenv bashio
# Home Assistant add-on run script for NTPower custom component

echo "Starting NTPower custom component..."

# Ensure data directory exists
mkdir -p /config/ntpower_data

# Nothing to run continuously - this add-on just provides the integration
# Home Assistant will call the services (refresh/backfill) as needed

echo "NTPower custom component setup complete. Services available: ntpower.refresh, ntpower.backfill"

# Keep container alive
tail -f /dev/null
