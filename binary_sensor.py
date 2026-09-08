"""C-Bus PIR / occupancy sensors.

A C-Bus PIR does not publish a dedicated "motion" signal: it is programmed to
switch a lighting group directly. C-Gate, however, tags every group change
with the unit that originated it (``sourceunit=N``), so motion is derived as:

  * ON  — the PIR unit itself turned one of its groups on
  * OFF — that group went to 0 (PIR timeout, or anyone switching it off)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_GROUP,
    ATTR_GROUP_NAME,
    ATTR_LAST_MOTION,
    ATTR_UNIT,
    ATTR_UNIT_TYPE,
    DOMAIN,
    ROLE_PIR,
)
from .coordinator import CBusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: CBusCoordinator = data["coordinator"]
    project = coordinator.project_name

    entities: List[CBusMotionSensor] = []

    for network_id, net_data in coordinator.discovery_model.items():
        for addr, unit in net_data.get("units", {}).items():
            if unit.get("role") != ROLE_PIR:
                continue
            if not unit.get("groups"):
                _LOGGER.debug("PIR unit %s has no groups programmed; skipping", addr)
                continue
            entities.append(
                CBusMotionSensor(coordinator, project, str(network_id), unit)
            )

    if entities:
        _LOGGER.info("Loaded %d C-Bus motion sensors", len(entities))
        async_add_entities(entities)
    else:
        _LOGGER.info("No C-Bus PIR units found.")


class CBusMotionSensor(BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Motion"
    _attr_device_class = BinarySensorDeviceClass.MOTION

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
        # (app, group) pairs this PIR is programmed to control
        self._targets = [
            (int(s["app"]), int(s["group"])) for s in unit.get("slots", [])
        ] or [(int(unit.get("app", 56)), int(g)) for g in unit.get("groups", [])]

        self._is_on = False
        self._last_motion = None
        self._active_group: int | None = None

        self._attr_unique_id = f"cbus_motion_{project}_{network}_p{self._unit}"
        self._attr_device_info = coordinator.device_info_for_unit(self._unit, network)

    async def async_added_to_hass(self) -> None:
        self.coordinator.register_unit_callback(
            self._unit, self._on_unit_event, project=self.project, network=self.network
        )
        for app, group in self._targets:
            self.coordinator.register_callback(
                app,
                group,
                self._make_group_listener(group),
                project=self.project,
                network=self.network,
            )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.unregister_unit_callback(
            self._unit, self._on_unit_event, project=self.project, network=self.network
        )

    # PIR originated a change on one of its groups
    def _on_unit_event(self, app: int, group: int, level: int) -> None:
        if level > 0:
            self._is_on = True
            self._active_group = group
            self._last_motion = dt_util.utcnow()
        else:
            self._is_on = False
        self.async_write_ha_state()

    # Group went off by any means (timeout, keypad, HA) -> no longer occupied
    def _make_group_listener(self, group: int):
        def _listener(level: int) -> None:
            if level == 0 and self._is_on and (
                self._active_group is None or self._active_group == group
            ):
                self._is_on = False
                self.async_write_ha_state()

        return _listener

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        group = self._active_group
        if group is None and self._targets:
            group = self._targets[0][1]
        return {
            ATTR_UNIT: self._unit,
            ATTR_UNIT_TYPE: self._unit_type,
            ATTR_GROUP: group,
            ATTR_GROUP_NAME: self.coordinator.group_name(56, group, self.network)
            if group is not None
            else None,
            ATTR_LAST_MOTION: self._last_motion.isoformat() if self._last_motion else None,
        }
