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
        "modeshape": ["modeshape01"],
        "web": ["web01", "shared01"],
        "tobi": ["shared01", "tobi01"],
        "maintenance": ["shared01"],
    }
    services = [
        {
            "name": "modeshape",
            "groups": ["modeshape"],
            "unit": "xout-modeshape.service",
        },
        {
            "name": "web",
            "groups": ["web", "tobi"],
            "exclude_groups": ["maintenance"],
            "unit": "xout-web.service",
        },
    ]

    start = MODULE.serviceflow_plan(services, groups, "start")
    assert service_names(start) == ["modeshape", "web"]
    assert start["phases"][0]["services"][1]["hosts"] == ["web01", "tobi01"]

    stop = MODULE.serviceflow_plan(services, groups, "stop")
    assert service_names(stop) == ["web", "modeshape"]

    restart = MODULE.serviceflow_plan(services, groups, "restart")
    assert [phase["action"] for phase in restart["phases"]] == ["stop", "start"]
    assert service_names(restart, 0) == ["web", "modeshape"]
    assert service_names(restart, 1) == ["modeshape", "web"]

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
    assert service_names(skipped) == ["modeshape", "web"]

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
                "groups": ["web"],
                "exclude_groups": ["web"],
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
                "groups": ["web"],
                "unit": "bad.service",
                "manage": "false",
            }
        ],
        groups,
        "start",
    )
    expect_error(
        "unsupported fields: hooks, ready",
        [
            {
                "name": "unsafe",
                "groups": ["web"],
                "unit": "unsafe.service",
                "hooks": {},
                "ready": {"type": "systemd"},
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
