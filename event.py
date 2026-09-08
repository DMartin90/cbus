"""C-Bus keypad / eDLT key-press events.

One ``event`` entity per input unit (Saturn/Neo keypad or glass eDLT). It
fires whenever that unit originates a group change on the bus — i.e. someone
physically pressed a key. The event attributes carry which group (and which
key slot) was hit and the resulting level, so automations can react to the
*press* rather than to the load state.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_APP,
    ATTR_GROUP,
    ATTR_GROUP_NAME,
    ATTR_LEVEL,
    ATTR_SLOT,
    ATTR_UNIT,
    ATTR_UNIT_TYPE,
    DOMAIN,
    ROLE_EDLT,
    ROLE_KEYPAD,
)
from .coordinator import CBusCoordinator

_LOGGER = logging.getLogger(__name__)

EVENT_ON = "on"
EVENT_OFF = "off"
EVENT_RAMP = "ramp"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: CBusCoordinator = data["coordinator"]
    project = coordinator.project_name

    entities: List[CBusKeypadEvent] = []

    for network_id, net_data in coordinator.discovery_model.items():
        for addr, unit in net_data.get("units", {}).items():
            if unit.get("role") not in (ROLE_KEYPAD, ROLE_EDLT):
                continue
            entities.append(
                CBusKeypadEvent(coordinator, project, str(network_id), unit)
            )

    if entities:
        _LOGGER.info("Loaded %d C-Bus keypad event entities", len(entities))
        async_add_entities(entities)
    else:
        _LOGGER.info("No C-Bus keypads found.")


class CBusKeypadEvent(EventEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Keys"
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = [EVENT_ON, EVENT_OFF, EVENT_RAMP]

    def __init__(
        self,
        coordinator: CBusCoordinator,
        project: str,
        network: str,
        unit: Dict[str, Any],
    ) -> None:
        self.coordinator = coordinator
        self.project = project
        self.network = network
        self._unit = int(unit["address"])
        self._unit_type = unit.get("type")
        self._slots = unit.get("slots", [])

        self._attr_unique_id = f"cbus_keypad_{project}_{network}_p{self._unit}"
        self._attr_device_info = coordinator.device_info_for_unit(self._unit, network)

    async def async_added_to_hass(self) -> None:
        self.coordinator.register_unit_callback(
            self._unit, self._on_unit_event, project=self.project, network=self.network
        )

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.unregister_unit_callback(
            self._unit, self._on_unit_event, project=self.project, network=self.network
        )

    def _slot_for(self, app: int, group: int) -> int | None:
        for s in self._slots:
            if int(s.get("app", -1)) == app and int(s.get("group", -1)) == group:
                return s.get("slot")
        return None

    def _on_unit_event(self, app: int, group: int, level: int) -> None:
        if level <= 0:
            event_type = EVENT_OFF
        elif level >= 255:
            event_type = EVENT_ON
        else:
            event_type = EVENT_RAMP

        self._trigger_event(
            event_type,
            {
                ATTR_UNIT: self._unit,
                ATTR_UNIT_TYPE: self._unit_type,
                ATTR_APP: app,
                ATTR_GROUP: group,
                ATTR_GROUP_NAME: self.coordinator.group_name(app, group, self.network),
                ATTR_LEVEL: level,
                ATTR_SLOT: self._slot_for(app, group),
            },
        )
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {
            ATTR_UNIT: self._unit,
            ATTR_UNIT_TYPE: self._unit_type,
            "keys": [
                {
                    ATTR_SLOT: s.get("slot"),
                    ATTR_APP: s.get("app"),
                    ATTR_GROUP: s.get("group"),
                    ATTR_GROUP_NAME: self.coordinator.group_name(
                        int(s.get("app", 56)), int(s.get("group")), self.network
                    ),
                }
                for s in self._slots
            ],
        }
