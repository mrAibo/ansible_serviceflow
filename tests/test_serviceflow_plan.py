#!/usr/bin/env python3

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "filter" / "serviceflow_plan.py"
SPEC = importlib.util.spec_from_file_location("serviceflow_plan", PLUGIN)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def expect_error(fragment, services, groups, action):
    try:
        MODULE.serviceflow_plan(services, groups, action)
    except MODULE.AnsibleFilterError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"expected error containing: {fragment}")


def service_names(plan, phase_index=0):
    return [service["name"] for service in plan["phases"][phase_index]["services"]]


def main():
    groups = {
        "backend": ["backend01"],
        "frontend": ["frontend01", "shared01"],
        "edge": ["shared01", "edge01"],
        "maintenance": ["shared01"],
    }
    services = [
        {
            "name": "backend",
            "groups": ["backend"],
            "unit": "example-backend.service",
            "ready": {
                "type": "systemd",
                "active_state": "active",
                "sub_state": "exited",
                "timeout": 10,
                "interval": 2,
            },
            "hooks": {
                "before_stop": [
                    {
                        "name": "Prepare shutdown",
                        "tasks": "hooks/prepare_shutdown.yml",
                        "vars": {"timeout": 60},
                    }
                ],
                "after_ready": [
                    {
                        "name": "Record readiness",
                        "tasks": "hooks/record_ready.yml",
                    }
                ],
            },
        },
        {
            "name": "frontend",
            "groups": ["frontend", "edge"],
            "exclude_groups": ["maintenance"],
            "unit": "example-frontend.service",
        },
    ]

    start = MODULE.serviceflow_plan(services, groups, "start")
    assert service_names(start) == ["backend", "frontend"]
    assert start["phases"][0]["services"][1]["hosts"] == ["frontend01", "edge01"]
    assert start["phases"][0]["services"][0]["hooks"] == {
        "before_stop": [
            {
                "name": "Prepare shutdown",
                "tasks": "hooks/prepare_shutdown.yml",
                "vars": {"timeout": 60},
            }
        ],
        "after_ready": [
            {
                "name": "Record readiness",
                "tasks": "hooks/record_ready.yml",
                "vars": {},
            }
        ],
    }
    assert start["phases"][0]["services"][0]["ready"] == {
        "type": "systemd",
        "active_state": "active",
        "sub_state": "exited",
        "timeout": 10,
        "interval": 2,
        "attempts": 6,
    }
    assert start["phases"][0]["services"][1]["ready"] is None

    log_plan = MODULE.serviceflow_plan(
        [
            {
                "name": "backend",
                "groups": ["backend"],
                "unit": "example-backend.service",
                "ready": {
                    "type": "log",
                    "path": "/var/log/example/application.log",
                    "regex": "^Application ready$",
                    "timeout": 30,
                },
            }
        ],
        groups,
        "start",
    )
    assert log_plan["phases"][0]["services"][0]["ready"] == {
        "type": "log",
        "path": "/var/log/example/application.log",
        "regex": "^Application ready$",
        "timeout": 30,
        "interval": 1,
    }

    stop = MODULE.serviceflow_plan(services, groups, "stop")
    assert service_names(stop) == ["frontend", "backend"]

    restart = MODULE.serviceflow_plan(services, groups, "restart")
    assert [phase["action"] for phase in restart["phases"]] == ["stop", "start"]
    assert service_names(restart, 0) == ["frontend", "backend"]
    assert service_names(restart, 1) == ["backend", "frontend"]

    optional = services + [
        {
            "name": "optional",
            "groups": ["not-present"],
            "unit": "optional.service",
            "manage": False,
        }
    ]
    skipped = MODULE.serviceflow_plan(optional, groups, "start")
    assert skipped["skipped"] == [{"name": "optional", "reason": "manage=false"}]
    assert service_names(skipped) == ["backend", "frontend"]

    expect_error("unsupported action", services, groups, "reload")
    expect_error(
        "duplicate service name",
        services + [dict(services[0])],
        groups,
        "start",
    )
    expect_error(
        "missing inventory group 'missing'",
        [{"name": "broken", "groups": ["missing"], "unit": "broken.service"}],
        groups,
        "start",
    )
    expect_error(
        "resolves to no target hosts",
        [
            {
                "name": "excluded",
                "groups": ["frontend"],
                "exclude_groups": ["frontend"],
                "unit": "excluded.service",
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "manage must be a boolean",
        [
            {
                "name": "bad-manage",
                "groups": ["frontend"],
                "unit": "bad.service",
                "manage": "false",
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "ready.type must be one of: systemd, log",
        [
            {
                "name": "bad-type",
                "groups": ["frontend"],
                "unit": "bad-type.service",
                "ready": {"type": "http"},
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "ready.timeout must be a positive integer",
        [
            {
                "name": "bad-timeout",
                "groups": ["frontend"],
                "unit": "bad-timeout.service",
                "ready": {"type": "systemd", "timeout": 0},
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "ready contains unsupported fields: regex",
        [
            {
                "name": "bad-systemd-field",
                "groups": ["frontend"],
                "unit": "bad-systemd-field.service",
                "ready": {"type": "systemd", "regex": "ready"},
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "ready contains unsupported fields: active_state",
        [
            {
                "name": "bad-log-field",
                "groups": ["frontend"],
                "unit": "bad-log-field.service",
                "ready": {
                    "type": "log",
                    "path": "/var/log/example/application.log",
                    "regex": "ready",
                    "active_state": "active",
                },
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "ready.path must be absolute",
        [
            {
                "name": "relative-log",
                "groups": ["frontend"],
                "unit": "relative-log.service",
                "ready": {
                    "type": "log",
                    "path": "application.log",
                    "regex": "ready",
                },
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "ready.regex is invalid",
        [
            {
                "name": "bad-regex",
                "groups": ["frontend"],
                "unit": "bad-regex.service",
                "ready": {
                    "type": "log",
                    "path": "/var/log/example/application.log",
                    "regex": "[",
                },
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "hooks.after_ready requires ready",
        [
            {
                "name": "missing-ready",
                "groups": ["frontend"],
                "unit": "missing-ready.service",
                "hooks": {"after_ready": [{"tasks": "hooks/example.yml"}]},
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "unsupported fields: on_error",
        [
            {
                "name": "bad-hook",
                "groups": ["frontend"],
                "unit": "bad-hook.service",
                "hooks": {
                    "before_stop": [
                        {"tasks": "hooks/example.yml", "on_error": "continue"}
                    ]
                },
            }
        ],
        groups,
        "start",
    )

    registered = MODULE.FilterModule().filters()
    assert registered["serviceflow_plan"] is MODULE.serviceflow_plan
    print("ServiceFlow planner tests passed")


if __name__ == "__main__":
    main()
