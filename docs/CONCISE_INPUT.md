# Concise service input

Version 0.2.0 adds optional input shortcuts without changing lifecycle behavior.

```yaml
serviceflow_services:
  - unit: example-database.service
    groups: database
    ready: {type: systemd}
```

The planner normalizes this to the same internal service definition used by existing configurations.

## Name derivation

When `name` is omitted, only a final `.service` suffix is removed from `unit`:

- `example-worker.service` becomes `example-worker`;
- `worker@42.service` becomes `worker@42`;
- `example.socket` remains `example.socket`.

An explicit non-empty `name` always wins. Duplicate explicit or derived names are rejected.

## Group fields

`groups` and `exclude_groups` accept either one string or a list of strings:

```yaml
groups: database
exclude_groups: maintenance
```

```yaml
groups:
  - database
  - reporting
exclude_groups:
  - maintenance
```

There is no automatic inventory discovery. Every unit and positive target group remains explicit.

## Readiness

Readiness remains a dictionary. Use normal YAML or the equivalent inline form:

```yaml
ready:
  type: systemd
```

```yaml
ready: {type: systemd}
```

Existing configurations retain their behavior and result schema.
