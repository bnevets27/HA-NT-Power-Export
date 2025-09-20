from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import (
    DOMAIN, CONF_ACCOUNT_ID, CONF_SERVICE_ID, CONF_USERNAME, CONF_PASSWORD,
    CONF_STATISTIC_ID, CONF_UNIT, CONF_TIMEZONE, CONF_BASE_URL,
    CONF_START_DATE, CONF_INITIAL_SUM, CONF_METER_READING_DATE, CONF_METER_READING_KWH,
    CONF_RECALCULATE_FROM_METER
)

class NTPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            try:
                # Validate the input
                schema = self._get_schema()
                validated_input = schema(user_input)
                return self.async_create_entry(title="NTPower", data=validated_input)
            except vol.Invalid as ex:
                # Handle validation errors
                if "initial_sum" in str(ex.path):
                    errors["initial_sum"] = "invalid_float"
                elif "meter_reading_kwh" in str(ex.path):
                    errors["meter_reading_kwh"] = "invalid_float"
                else:
                    errors["base"] = "invalid_input"

        return self.async_show_form(
            step_id="user", 
            data_schema=self._get_schema(),
            errors=errors
        )
    
    def _get_schema(self):
        """Get the configuration schema."""
        return vol.Schema({
            vol.Required(CONF_USERNAME, description="NT Power username"): str,
            vol.Required(CONF_PASSWORD, description="NT Power password"): str,
            vol.Required(CONF_ACCOUNT_ID, description="Account ID (find this on your NT Power bill or online account)"): str,
            vol.Required(CONF_SERVICE_ID, description="Service ID (find this on your NT Power bill or online account)"): str,
            vol.Optional(CONF_STATISTIC_ID, default="sensor:ntpower_energy_export", description="Home Assistant statistic ID for energy data"): str,
            vol.Optional(CONF_UNIT, default="kWh", description="Energy unit (kWh recommended)"): str,
            vol.Optional(CONF_TIMEZONE, default="America/Toronto", description="Your timezone (e.g., America/Toronto, America/New_York)"): str,
            vol.Optional(CONF_BASE_URL, default="https://myaccountapi.ntpower.lhsharedservices.com", description="NT Power API base URL (leave default unless specified by NT Power)"): str,
            vol.Optional(CONF_START_DATE, description="Start date for data collection (format: YYYY-MM-DD, example: 2025-01-01)"): str,
            vol.Optional(CONF_INITIAL_SUM, default=0.0, description="Starting meter reading in kWh (optional, use 0.0 for automatic calculation)"): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(CONF_METER_READING_DATE, description="Date/time of known meter reading (format: YYYY-MM-DD HH:MM, example: 2025-09-19 23:00)"): str,
            vol.Optional(CONF_METER_READING_KWH, description="Known meter reading in kWh (example: 83761.120, used to sync with actual meter)"): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(CONF_RECALCULATE_FROM_METER, default=False, description="Enable meter reading recalibration to fix sync issues"): bool,
        })
