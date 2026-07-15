# Copyright (C) 2026 Aleksej Voronin
# GNU General Public License v3.0 or later

from collections.abc import Mapping, Sequence

from ansible.errors import AnsibleFilterError


_ALLOWED_ACTIONS = ("start", "stop", "restart")


def _fail(message):
    raise AnsibleFilterError("ServiceFlow: " + message)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string")
    return value.strip()


def _sequence(value, field):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(f"{field} must be a list")
    return list(value)


def _names(value, field):
    names = _sequence(value, field)
    if not names:
        _fail(f"{field} must not be empty")
    return [_text(name, f"{field} entry") for name in names]


def _group_members(group_name, inventory_groups, field):
    if group_name not in inventory_groups:
        _fail(f"{field} references missing inventory group '{group_name}'")

    members = _sequence(inventory_groups[group_name], f"inventory group '{group_name}'")
    return [_text(host, f"inventory group '{group_name}' host") for host in members]


def _resolve_hosts(service_name, group_names, exclude_group_names, inventory_groups):
    hosts = []
    seen = set()

    for group_name in group_names:
        for host in _group_members(group_name, inventory_groups, f"service '{service_name}'.groups"):
            if host not in seen:
                hosts.append(host)
                seen.add(host)

    excluded = set()
    for group_name in exclude_group_names:
        excluded.update(
            _group_members(
                group_name,
                inventory_groups,
                f"service '{service_name}'.exclude_groups",
            )
        )

    resolved = [host for host in hosts if host not in excluded]
    if not resolved:
        _fail(f"service '{service_name}' resolves to no target hosts")
    return resolved


def _phase(action, services):
    return {"action": action, "services": list(services)}


def serviceflow_plan(services, inventory_groups, action):
    """Validate configuration and return deterministic lifecycle phases."""

    action = _text(action, "serviceflow_action")
    if action not in _ALLOWED_ACTIONS:
        allowed = ", ".join(_ALLOWED_ACTIONS)
        _fail(f"unsupported action '{action}'; allowed actions: {allowed}")

    services = _sequence(services, "serviceflow_services")
    if not services:
        _fail("serviceflow_services must not be empty")
    if not isinstance(inventory_groups, Mapping):
        _fail("inventory groups must be a mapping")

    planned = []
    skipped = []
    service_names = set()

    for index, service in enumerate(services):
        field = f"serviceflow_services[{index}]"
        if not isinstance(service, Mapping):
            _fail(f"{field} must be a mapping")

        name = _text(service.get("name"), f"{field}.name")
        if name in service_names:
            _fail(f"duplicate service name '{name}'")
        service_names.add(name)

        unit = _text(service.get("unit"), f"service '{name}'.unit")
        if any(character.isspace() for character in unit):
            _fail(f"service '{name}'.unit must not contain whitespace")

        group_names = _names(service.get("groups"), f"service '{name}'.groups")
        exclude_group_names = service.get("exclude_groups", [])
        exclude_group_names = [
            _text(group, f"service '{name}'.exclude_groups entry")
            for group in _sequence(
                exclude_group_names,
                f"service '{name}'.exclude_groups",
            )
        ]

        manage = service.get("manage", True)
        if type(manage) is not bool:
            _fail(f"service '{name}'.manage must be a boolean")
        if not manage:
            skipped.append({"name": name, "reason": "manage=false"})
            continue

        planned.append(
            {
                "name": name,
                "unit": unit,
                "hosts": _resolve_hosts(
                    name,
                    group_names,
                    exclude_group_names,
                    inventory_groups,
                ),
            }
        )

    if action == "start":
        phases = [_phase("start", planned)]
    elif action == "stop":
        phases = [_phase("stop", reversed(planned))]
    else:
        phases = [
            _phase("stop", reversed(planned)),
            _phase("start", planned),
        ]

    return {
        "action": action,
        "phases": phases,
        "skipped": skipped,
    }


class FilterModule:
    def filters(self):
        return {"serviceflow_plan": serviceflow_plan}
