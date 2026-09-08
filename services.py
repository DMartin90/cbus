"""Home Assistant services for the C-Bus integration.

`cbus.set_label` pushes a dynamic label to eDLT / DLT keypad widgets, so
HA data (Sonos track, temperatures, alarm state, …) can be shown on the
physical keypads. Labels are addressed by C-Bus group number — the eDLT
renders it on whichever widget is mapped to that group.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .coordinator import CBusCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_LABEL = "set_label"

ATTR_GROUP = "group"
ATTR_TEXT = "text"
ATTR_APP = "app"
ATTR_NETWORK = "network"
ATTR_PROJECT = "project"
ATTR_LANGUAGE = "language"
ATTR_VARIANT = "variant"
ATTR_ACTION_SEL = "action_sel"
ATTR_UNICODE = "unicode"
ATTR_ICON = "icon"
ATTR_CLEAR = "clear"

SET_LABEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_GROUP): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Optional(ATTR_TEXT, default=""): cv.string,
        vol.Optional(ATTR_CLEAR, default=False): cv.boolean,
        vol.Optional(ATTR_APP, default=56): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Optional(ATTR_LANGUAGE, default=1): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Optional(ATTR_VARIANT, default="F0"): vol.Any(
            None, vol.All(cv.string, vol.Upper, vol.In(["F0", "F1", "F2", "F3"]))
        ),
        vol.Optional(ATTR_ACTION_SEL, default="-"): cv.string,
        vol.Optional(ATTR_UNICODE, default=True): cv.boolean,
        vol.Optional(ATTR_ICON): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
        vol.Optional(ATTR_PROJECT): cv.string,
        vol.Optional(ATTR_NETWORK): cv.string,
    }
)


def _pick_coordinator(hass: HomeAssistant, call: ServiceCall) -> CBusCoordinator:
    entries = hass.data.get(DOMAIN, {})
    coordinators = [
        d["coordinator"] for d in entries.values() if isinstance(d, dict) and "coordinator" in d
    ]
    if not coordinators:
        raise HomeAssistantError("No C-Bus integration is loaded")

    project = call.data.get(ATTR_PROJECT)
    network = call.data.get(ATTR_NETWORK)
    if project or network:
        for c in coordinators:
            if (not project or c.project_name == project) and (
                not network or c.network_id == str(network)
            ):
                return c
        raise HomeAssistantError(
            f"No C-Bus network matches project={project!r} network={network!r}"
        )
    return coordinators[0]


async def async_register_services(hass: HomeAssistant) -> None:
    """Register integration-wide services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_LABEL):
        return

    async def _handle_set_label(call: ServiceCall) -> None:
        coordinator = _pick_coordinator(hass, call)
        group = call.data[ATTR_GROUP]
        try:
            resp = await coordinator.session.send_label(
                coordinator.project_name,
                call.data.get(ATTR_NETWORK) or coordinator.network_id,
                call.data[ATTR_APP],
                group,
                call.data.get(ATTR_TEXT, ""),
                language=call.data[ATTR_LANGUAGE],
                variant=call.data.get(ATTR_VARIANT),
                action_sel=call.data[ATTR_ACTION_SEL],
                unicode=call.data[ATTR_UNICODE],
                icon=call.data.get(ATTR_ICON),
                clear=call.data[ATTR_CLEAR],
            )
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HomeAssistantError(f"C-Gate rejected label for group {group}: {exc}") from exc

        _LOGGER.debug("set_label group=%s -> %s", group, "; ".join(resp))

    hass.services.async_register(
        DOMAIN, SERVICE_SET_LABEL, _handle_set_label, schema=SET_LABEL_SCHEMA
    )
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_LABEL)


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove services when the last config entry unloads."""
    # Called from async_unload_entry AFTER the entry has been popped from
    # hass.data, so this counts only the entries that remain loaded.
    remaining = [
        d for d in hass.data.get(DOMAIN, {}).values()
        if isinstance(d, dict) and "coordinator" in d
    ]
    if not remaining and hass.services.has_service(DOMAIN, SERVICE_SET_LABEL):
        hass.services.async_remove(DOMAIN, SERVICE_SET_LABEL)
