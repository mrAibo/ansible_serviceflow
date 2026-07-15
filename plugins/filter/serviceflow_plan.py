# Copyright: (c) 2026 Aleksej Voronin
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from collections.abc import Mapping, Sequence

from ansible.errors import AnsibleFilterError


_ALLOWED_ACTIONS = ("start", "stop", "restart")
_ALLOWED_SERVICE_FIELDS = frozenset(
    {"name", "unit", "groups", "exclude_groups", "manage", "hooks", "ready"}
)
_ALLOWED_HOOK_PHASES = (
    "before_start",
    "before_stop",
    "after_ready",
    "after_stop",
)
_ALLOWED_HOOK_FIELDS = frozenset({"name", "tasks", "vars"})
_ALLOWED_READINESS_FIELDS = frozenset(
    {"type", "active_state", "sub_state", "timeout", "interval"}
)


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


def _positive_integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{field} must be a positive integer")
    return value


def _group_members(group_name, inventory_groups, field):
    if group_name not in inventory_groups:
        _fail(f"{field} references missing inventory group '{group_name}'")

    members = _sequence(
        inventory_groups[group_name],
        f"inventory group '{group_name}'",
    )
    return [
        _text(host, f"inventory group '{group_name}' host")
        for host in members
    ]


def _resolve_hosts(service_name, group_names, exclude_group_names, inventory_groups):
    hosts = []
    seen = set()

    for group_name in group_names:
        members = _group_members(
            group_name,
            inventory_groups,
            f"service '{service_name}'.groups",
        )
        for host in members:
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


def _hooks(value, field):
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        _fail(f"{field} must be a mapping")

    unsupported_phases = sorted(
        str(phase) for phase in value if phase not in _ALLOWED_HOOK_PHASES
    )
    if unsupported_phases:
        _fail(
            f"{field} contains unsupported phases: "
            + ", ".join(unsupported_phases)
        )

    normalized = {}
    for phase, entries in value.items():
        phase_field = f"{field}.{phase}"
        normalized[phase] = []
        for index, hook in enumerate(_sequence(entries, phase_field)):
            hook_field = f"{phase_field}[{index}]"
            if not isinstance(hook, Mapping):
                _fail(f"{hook_field} must be a mapping")

            unsupported_fields = sorted(
                str(key) for key in hook if key not in _ALLOWED_HOOK_FIELDS
            )
            if unsupported_fields:
                _fail(
                    f"{hook_field} contains unsupported fields: "
                    + ", ".join(unsupported_fields)
                )

            tasks = _text(hook.get("tasks"), f"{hook_field}.tasks")
            name = _text(hook.get("name", tasks), f"{hook_field}.name")
            variables = hook.get("vars", {})
            if not isinstance(variables, Mapping):
                _fail(f"{hook_field}.vars must be a mapping")

            normalized[phase].append(
                {
                    "name": name,
                    "tasks": tasks,
                    "vars": dict(variables),
                }
            )

    return normalized


def _readiness(value, field):
    if value is None:
        return None
    if not isinstance(value, Mapping):
        _fail(f"{field} must be a mapping")

    unsupported_fields = sorted(
        str(key) for key in value if key not in _ALLOWED_READINESS_FIELDS
    )
    if unsupported_fields:
        _fail(
            f"{field} contains unsupported fields: "
            + ", ".join(unsupported_fields)
        )

    readiness_type = _text(value.get("type"), f"{field}.type")
    if readiness_type != "systemd":
        _fail(f"{field}.type must be 'systemd'")

    active_state = _text(
        value.get("active_state", "active"),
        f"{field}.active_state",
    )
    sub_state = value.get("sub_state")
    if sub_state is not None:
        sub_state = _text(sub_state, f"{field}.sub_state")

    timeout = _positive_integer(value.get("timeout", 60), f"{field}.timeout")
    interval = _positive_integer(value.get("interval", 2), f"{field}.interval")

    return {
        "type": readiness_type,
        "active_state": active_state,
        "sub_state": sub_state,
        "timeout": timeout,
        "interval": interval,
        "attempts": max(1, (timeout + interval - 1) // interval + 1),
    }


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

        unsupported = sorted(
            str(key) for key in service if key not in _ALLOWED_SERVICE_FIELDS
        )
        if unsupported:
            _fail(f"{field} contains unsupported fields: {', '.join(unsupported)}")

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
        hooks = _hooks(service.get("hooks"), f"service '{name}'.hooks")
        readiness = _readiness(service.get("ready"), f"service '{name}'.ready")
        if hooks.get("after_ready") and readiness is None:
            _fail(f"service '{name}'.hooks.after_ready requires ready")

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
                "hooks": hooks,
                "ready": readiness,
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
