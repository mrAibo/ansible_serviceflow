import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "filter" / "serviceflow_features.py"
SPEC = importlib.util.spec_from_file_location("serviceflow_features", PLUGIN)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def expect_error(fragment, callback):
    try:
        callback()
    except MODULE.AnsibleFilterError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"expected error containing: {fragment}")


def main():
    services = [
        {
            "name": "web",
            "unit": "web.service",
            "groups": ["web"],
            "hooks": {
                "after_start": [
                    {
                        "name": "Warm cache",
                        "tasks": "hooks/warm.yml",
                        "vars": {"token": "SECRET"},
                    }
                ],
                "after_ready": [{"tasks": "hooks/ready.yml"}],
            },
            "ready": {
                "type": "http",
                "url": "https://127.0.0.1/health",
                "headers": {"Authorization": "Bearer SECRET"},
                "user": "health",
                "password": "SECRET",
                "content_regex": "ready",
                "timeout": 10,
                "interval": 2,
            },
        }
    ]

    prepared = MODULE.serviceflow_prepare_features(services)
    assert "after_start" not in prepared[0]["hooks"]
    assert prepared[0]["ready"]["type"] == "systemd"

    base_plan = {
        "action": "start",
        "phases": [
            {
                "action": "start",
                "services": [
                    {
                        "name": "web",
                        "unit": "web.service",
                        "hosts": ["web01"],
                        "hooks": {"after_ready": [{"name": "ready", "tasks": "hooks/ready.yml", "vars": {}}]},
                        "ready": prepared[0]["ready"],
                    }
                ],
            }
        ],
        "skipped": [],
    }
    applied = MODULE.serviceflow_apply_features(base_plan, services)
    service = applied["phases"][0]["services"][0]
    assert service["hooks"]["after_start"][0]["name"] == "Warm cache"
    assert service["ready"]["type"] == "http"
    assert service["ready"]["retries"] == 5

    redacted = MODULE.serviceflow_redact_features(applied)
    ready = redacted["phases"][0]["services"][0]["ready"]
    assert ready["has_headers"] is True
    assert ready["has_auth"] is True
    assert "headers" not in ready
    assert "user" not in ready
    assert "password" not in ready
    assert "SECRET" not in repr(redacted)

    port = MODULE.serviceflow_prepare_features(
        [{"name": "api", "unit": "api.service", "groups": ["api"], "ready": {"type": "port", "port": 8443}}]
    )
    assert port[0]["ready"]["type"] == "systemd"

    journal_plan = MODULE.serviceflow_apply_features(
        {
            "action": "start",
            "phases": [{"action": "start", "services": [{"name": "worker", "unit": "worker.service", "hosts": ["worker01"], "hooks": {}, "ready": None}]}],
            "skipped": [],
        },
        [{"name": "worker", "unit": "worker.service", "groups": ["worker"], "ready": {"type": "journal", "regex": "Worker ready"}}],
    )
    assert journal_plan["phases"][0]["services"][0]["ready"]["unit"] == "worker.service"

    expect_error(
        "port must not exceed 65535",
        lambda: MODULE.serviceflow_prepare_features(
            [{"name": "bad", "unit": "bad.service", "groups": ["bad"], "ready": {"type": "port", "port": 70000}}]
        ),
    )
    expect_error(
        "interval must not exceed",
        lambda: MODULE.serviceflow_prepare_features(
            [{"name": "bad", "unit": "bad.service", "groups": ["bad"], "ready": {"type": "http", "url": "http://localhost", "timeout": 1, "interval": 2}}]
        ),
    )

    registered = MODULE.FilterModule().filters()
    assert set(registered) == {
        "serviceflow_prepare_features",
        "serviceflow_apply_features",
        "serviceflow_redact_features",
    }
    print("ServiceFlow feature tests passed")


if __name__ == "__main__":
    main()
