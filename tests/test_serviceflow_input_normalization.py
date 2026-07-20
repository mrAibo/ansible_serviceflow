import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "filter" / "serviceflow_plan.py"
SPEC = importlib.util.spec_from_file_location("serviceflow_plan", PLUGIN)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def expect_error(fragment, services, groups):
    try:
        MODULE.serviceflow_plan(services, groups, "start")
    except MODULE.AnsibleFilterError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"expected error containing: {fragment}")


def main():
    groups = {
        "workers": ["worker01", "maintenance01"],
        "maintenance": ["maintenance01"],
    }

    plan = MODULE.serviceflow_plan(
        [
            {
                "unit": "example-worker.service",
                "groups": "workers",
                "exclude_groups": "maintenance",
                "ready": {"type": "systemd"},
            },
            {
                "name": "background-worker",
                "unit": "example-worker@42.service",
                "groups": ["workers"],
            },
            {
                "unit": "example.socket",
                "groups": "workers",
            },
        ],
        groups,
        "start",
    )

    services = plan["phases"][0]["services"]
    assert services[0]["name"] == "example-worker"
    assert services[0]["hosts"] == ["worker01"]
    assert services[0]["ready"] == {
        "type": "systemd",
        "active_state": "active",
        "sub_state": None,
        "timeout": 60,
        "interval": 2,
        "retries": 30,
    }
    assert services[1]["name"] == "background-worker"
    assert services[2]["name"] == "example.socket"

    expect_error(
        "duplicate service name 'worker@42'",
        [
            {"unit": "worker@42.service", "groups": "workers"},
            {"unit": "worker@42.service", "groups": ["workers"]},
        ],
        groups,
    )
    expect_error(
        "name must be a non-empty string",
        [{"name": "", "unit": "worker.service", "groups": "workers"}],
        groups,
    )

    print("ServiceFlow input normalization tests passed")


if __name__ == "__main__":
    main()
