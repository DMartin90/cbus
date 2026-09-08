"""Diagnostics support: Settings → Integrations → C-Bus → Download diagnostics."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"host"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    if coordinator is None:
        return {"entry": async_redact_data(dict(entry.data), TO_REDACT), "error": "not loaded"}

    levels = {
        f"{p}/{n}/{a}/{g}": lvl for (p, n, a, g), lvl in coordinator.group_levels.items()
    }
    sources = {
        f"{p}/{n}/{a}/{g}": u for (p, n, a, g), u in coordinator.last_source_unit.items()
    }

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "link": async_redact_data(coordinator.link_info, TO_REDACT),
        "model": coordinator.discovery_model,
        "group_levels": levels,
        "last_source_unit": sources,
    }
