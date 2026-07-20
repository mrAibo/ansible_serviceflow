# Copyright: (c) 2026 Aleksej Voronin
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

DOCUMENTATION = r"""
name: serviceflow_features
short_description: Prepare and redact ServiceFlow 0.2 lifecycle features
version_added: "0.2.0"
description:
  - Validates feature fields added after the base lifecycle planner.
  - Preserves the stable 0.1 planner while adding new hooks and readiness types.
  - Redacts HTTP credentials and headers from public plans.
author:
  - Aleksej Voronin (@mrAibo)
"""

import copy
import re
from collections.abc import Mapping, Sequence

from ansible.errors import AnsibleFilterError


_NEW_READY_TYPES = ("port", "http", "journal")
_HTTP_SECRET_FIELDS = ("headers", "user", "password")


def _fail(message):
    raise AnsibleFilterError("ServiceFlow: " + message)


def _mapping(value, field):
    if not isinstance(value, Mapping):
        _fail(f"{field} must be a mapping")
    return value


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string")
    return value.strip()


def _positive_integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{field} must be a positive integer")
    return value


def _boolean(value, field):
    if not isinstance(value, bool):
        _fail(f"{field} must be a boolean")
    return value


def _hook_list(value, field):
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(f"{field} must be a list")
    normalized = []
    for index, hook in enumerate(value):
        hook_field = f"{field}[{index}]"
        hook = _mapping(hook, hook_field)
        unsupported = sorted(set(hook) - {"name", "tasks", "vars"})
        if unsupported:
            _fail(f"{hook_field} contains unsupported fields: {', '.join(unsupported)}")
        tasks = _text(hook.get("tasks"), f"{hook_field}.tasks")
        name = _text(hook.get("name", tasks), f"{hook_field}.name")
        variables = hook.get("vars", {})
        if not isinstance(variables, Mapping):
            _fail(f"{hook_field}.vars must be a mapping")
        normalized.append({"name": name, "tasks": tasks, "vars": dict(variables)})
    return normalized


def _common_ready(value, field):
    timeout = _positive_integer(value.get("timeout", 60), f"{field}.timeout")
    interval = _positive_integer(value.get("interval", 1), f"{field}.interval")
    if interval > timeout:
        _fail(f"{field}.interval must not exceed {field}.timeout")
    return timeout, interval


def _port_ready(value, field):
    unsupported = sorted(set(value) - {"type", "host", "port", "timeout", "interval"})
    if unsupported:
        _fail(f"{field} contains unsupported fields: {', '.join(unsupported)}")
    timeout, interval = _common_ready(value, field)
    port = _positive_integer(value.get("port"), f"{field}.port")
    if port > 65535:
        _fail(f"{field}.port must not exceed 65535")
    return {
        "type": "port",
        "host": _text(value.get("host", "127.0.0.1"), f"{field}.host"),
        "port": port,
        "timeout": timeout,
        "interval": interval,
    }


def _http_ready(value, field):
    allowed = {
        "type", "url", "method", "status_code", "content_regex", "headers",
        "user", "password", "validate_certs", "timeout", "interval"
    }
    unsupported = sorted(set(value) - allowed)
    if unsupported:
        _fail(f"{field} contains unsupported fields: {', '.join(unsupported)}")
    timeout, interval = _common_ready(value, field)
    status_code = value.get("status_code", [200])
    if isinstance(status_code, int) and not isinstance(status_code, bool):
        status_code = [status_code]
    if isinstance(status_code, (str, bytes)) or not isinstance(status_code, Sequence):
        _fail(f"{field}.status_code must be an integer or list of integers")
    normalized_codes = []
    for code in status_code:
        if isinstance(code, bool) or not isinstance(code, int) or not 100 <= code <= 599:
            _fail(f"{field}.status_code entries must be HTTP status integers")
        normalized_codes.append(code)
    headers = value.get("headers", {})
    if not isinstance(headers, Mapping):
        _fail(f"{field}.headers must be a mapping")
    content_regex = value.get("content_regex")
    if content_regex is not None:
        content_regex = _text(content_regex, f"{field}.content_regex")
        try:
            re.compile(content_regex)
        except re.error as error:
            _fail(f"{field}.content_regex is invalid: {error}")
    return {
        "type": "http",
        "url": _text(value.get("url"), f"{field}.url"),
        "method": _text(value.get("method", "GET"), f"{field}.method").upper(),
        "status_code": normalized_codes,
        "content_regex": content_regex,
        "headers": dict(headers),
        "user": value.get("user"),
        "password": value.get("password"),
        "validate_certs": _boolean(value.get("validate_certs", True), f"{field}.validate_certs"),
        "timeout": timeout,
        "interval": interval,
        "retries": timeout // interval,
    }


def _journal_ready(value, field, unit):
    unsupported = sorted(set(value) - {"type", "unit", "regex", "timeout", "interval"})
    if unsupported:
        _fail(f"{field} contains unsupported fields: {', '.join(unsupported)}")
    timeout, interval = _common_ready(value, field)
    regex = _text(value.get("regex"), f"{field}.regex")
    try:
        re.compile(regex)
    except re.error as error:
        _fail(f"{field}.regex is invalid: {error}")
    return {
        "type": "journal",
        "unit": _text(value.get("unit", unit), f"{field}.unit"),
        "regex": regex,
        "timeout": timeout,
        "interval": interval,
        "retries": timeout // interval,
    }


def _new_ready(value, field, unit):
    value = _mapping(value, field)
    ready_type = value.get("type")
    if ready_type == "port":
        return _port_ready(value, field)
    if ready_type == "http":
        return _http_ready(value, field)
    if ready_type == "journal":
        return _journal_ready(value, field, unit)
    return None


def serviceflow_prepare_features(services):
    """Return services accepted by the stable base planner."""

    if isinstance(services, (str, bytes)) or not isinstance(services, Sequence):
        _fail("serviceflow_services must be a list")
    prepared = copy.deepcopy(list(services))
    for index, service in enumerate(prepared):
        if not isinstance(service, Mapping):
            continue
        hooks = service.get("hooks")
        if isinstance(hooks, Mapping) and "after_start" in hooks:
            _hook_list(hooks["after_start"], f"serviceflow_services[{index}].hooks.after_start")
            hooks = dict(hooks)
            hooks.pop("after_start")
            service["hooks"] = hooks
        ready = service.get("ready")
        if isinstance(ready, Mapping) and ready.get("type") in _NEW_READY_TYPES:
            normalized = _new_ready(ready, f"serviceflow_services[{index}].ready", service.get("unit"))
            service["ready"] = {
                "type": "systemd",
                "active_state": "active",
                "timeout": normalized["timeout"],
                "interval": min(normalized["interval"], normalized["timeout"]),
            }
    return prepared


def serviceflow_apply_features(plan, services):
    """Restore validated feature fields onto a base execution plan."""

    plan = copy.deepcopy(_mapping(plan, "execution plan"))
    originals = {}
    for index, service in enumerate(services):
        service = _mapping(service, f"serviceflow_services[{index}]")
        name = _text(service.get("name"), f"serviceflow_services[{index}].name")
        originals[name] = service
    for phase in plan.get("phases", []):
        for service in phase.get("services", []):
            original = originals[service["name"]]
            hooks = original.get("hooks", {})
            if isinstance(hooks, Mapping) and "after_start" in hooks:
                service.setdefault("hooks", {})["after_start"] = _hook_list(
                    hooks["after_start"],
                    f"service '{service['name']}'.hooks.after_start",
                )
            ready = original.get("ready")
            if isinstance(ready, Mapping) and ready.get("type") in _NEW_READY_TYPES:
                service["ready"] = _new_ready(
                    ready,
                    f"service '{service['name']}'.ready",
                    service["unit"],
                )
    return plan


def serviceflow_redact_features(plan):
    """Remove HTTP credentials and headers from a public plan."""

    plan = copy.deepcopy(_mapping(plan, "public plan"))
    for phase in plan.get("phases", []):
        for service in phase.get("services", []):
            ready = service.get("ready")
            if not isinstance(ready, Mapping) or ready.get("type") != "http":
                continue
            ready = dict(ready)
            ready["has_headers"] = bool(ready.get("headers"))
            ready["has_auth"] = bool(ready.get("user") is not None or ready.get("password") is not None)
            for field in _HTTP_SECRET_FIELDS:
                ready.pop(field, None)
            service["ready"] = ready
    return plan


class FilterModule:
    def filters(self):
        return {
            "serviceflow_prepare_features": serviceflow_prepare_features,
            "serviceflow_apply_features": serviceflow_apply_features,
            "serviceflow_redact_features": serviceflow_redact_features,
        }
