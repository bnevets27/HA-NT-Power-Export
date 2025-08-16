from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN
from .fetch_energy import fetch_energy_and_write

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    async def handle_refresh(call: ServiceCall):
        config = hass.data[DOMAIN][entry.entry_id]
        await hass.async_add_executor_job(fetch_energy_and_write, config)

    hass.services.async_register(DOMAIN, "refresh", handle_refresh)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    return True
