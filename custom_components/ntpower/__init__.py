from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_START_DATE, CONF_END_DATE, CONF_INITIAL_SUM, CONF_FULL_HISTORY,
    CONF_STATE_STORE, CONF_RESET_BASELINE, CONF_CONTINUE_FROM_TSV,
)
from .fetch_energy import fetch_energy_and_write

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH = "refresh"
SERVICE_BACKFILL = "backfill"

SERVICE_SCHEMA = vol.Schema({
    vol.Optional(CONF_START_DATE): str,
    vol.Optional(CONF_END_DATE): str,
    vol.Optional(CONF_INITIAL_SUM): vol.Coerce(float),
    vol.Optional(CONF_FULL_HISTORY): bool,
    vol.Optional(CONF_STATE_STORE): str,
    vol.Optional(CONF_RESET_BASELINE): bool,
    vol.Optional(CONF_CONTINUE_FROM_TSV): str,
})

def _merge(base: dict, overrides: dict | None) -> dict:
    merged = dict(base or {})
    if overrides:
        merged.update({k: v for k, v in overrides.items() if v is not None})
    return merged

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    async def handle_refresh(call: ServiceCall):
        try:
            config = _merge(hass.data[DOMAIN][entry.entry_id], call.data)
            await hass.async_add_executor_job(fetch_energy_and_write, config)
        except Exception as exc:
            _LOGGER.exception("ntpower.refresh failed: %s", exc)
            raise HomeAssistantError(str(exc)) from exc

    async def handle_backfill(call: ServiceCall):
        try:
            config = _merge(hass.data[DOMAIN][entry.entry_id], call.data)
            # default backfill to full_history if not explicitly set
            config.setdefault(CONF_FULL_HISTORY, True)
            await hass.async_add_executor_job(fetch_energy_and_write, config)
        except Exception as exc:
            _LOGGER.exception("ntpower.backfill failed: %s", exc)
            raise HomeAssistantError(str(exc)) from exc

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_BACKFILL, handle_backfill, schema=SERVICE_SCHEMA)
    _LOGGER.debug("NTPower services registered: %s, %s", SERVICE_REFRESH, SERVICE_BACKFILL)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
