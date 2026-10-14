"""Switches for Zyxel port-forward rules."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.ha_zyxel.api import set_port_forward_enabled
from custom_components.ha_zyxel.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create one switch per port-forward rule the router reports."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    rules = (coordinator.data or {}).get("nat_rules") or []
    async_add_entities(
        PortForwardSwitch(coordinator, data["router"], entry, rule["Index"])
        for rule in rules
        if "Index" in rule
    )


class PortForwardSwitch(CoordinatorEntity, SwitchEntity):
    """Enable or disable a single port-forward rule."""

    _attr_icon = "mdi:router-network"

    def __init__(self, coordinator, router, entry: ConfigEntry, index: int) -> None:
        super().__init__(coordinator)
        self._router = router
        self._index = index
        self._attr_unique_id = f"{entry.entry_id}_nat_{index}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    def _rule(self) -> dict[str, Any] | None:
        for rule in (self.coordinator.data or {}).get("nat_rules") or []:
            if rule.get("Index") == self._index:
                return rule
        return None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._rule() is not None

    @property
    def name(self) -> str:
        rule = self._rule() or {}
        return f"Zyxel Port Forward {rule.get('Description') or self._index}"

    @property
    def is_on(self) -> bool | None:
        rule = self._rule()
        return None if rule is None else bool(rule.get("Enable"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rule = self._rule() or {}
        return {
            "protocol": rule.get("Protocol"),
            "external_port": _ports(rule, "External"),
            "internal_port": _ports(rule, "Internal"),
            "internal_client": rule.get("InternalClient"),
            "rule_index": self._index,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        rule = self._rule()
        if rule is None:
            return
        await self.hass.async_add_executor_job(
            set_port_forward_enabled, self._router, dict(rule), enabled
        )
        rule["Enable"] = enabled  # reflect immediately, the next poll confirms it
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


def _ports(rule: dict[str, Any], side: str) -> str:
    start, end = rule.get(f"{side}PortStart"), rule.get(f"{side}PortEnd")
    return str(start) if start == end else f"{start}-{end}"
