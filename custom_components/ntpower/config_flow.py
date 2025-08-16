from homeassistant import config_entries
import voluptuous as vol
from .const import (
    DOMAIN, CONF_ACCOUNT_ID, CONF_SERVICE_ID, CONF_USERNAME, CONF_PASSWORD,
    CONF_STATISTIC_ID, CONF_UNIT, CONF_TIMEZONE, CONF_BASE_URL, CONF_PORTAL_ORIGIN
)

class NTPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="NTPower Energy", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_ACCOUNT_ID): str,
            vol.Required(CONF_SERVICE_ID): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_STATISTIC_ID, default="sensor:ntpower_energy_export"): str,
            vol.Optional(CONF_UNIT, default="kWh"): str,
            vol.Optional(CONF_TIMEZONE, default="America/Toronto"): str,
            vol.Optional(CONF_BASE_URL, default="https://myaccountapi.ntpower.lhsharedservices.com"): str,
            vol.Optional(CONF_PORTAL_ORIGIN, default="https://myaccount.ntpower.ca"): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema)
