# Ansible ServiceFlow

Dependency-aware systemd service lifecycle orchestration for Ansible.

> **Status:** MVP development. The planner and lifecycle role now validate service definitions, resolve inventory-group hosts, and execute deterministic start, stop and restart phases with native systemd check mode and structured results. Hooks and readiness are not implemented yet.

ServiceFlow is intended for applications whose services run on different inventory hosts and must be started or stopped in a strict order. It complements `ansible.builtin.systemd_service`; it does not replace it.

## Problem

A conventional playbook often grows into repeated `shell: systemctl ...`, group-based `when` expressions, manual reverse ordering, log manipulation and application-specific tasks mixed into one long file.

ServiceFlow will keep the application definition declarative:

```yaml
serviceflow_action: restart

serviceflow_services:
  - name: backend
    groups: [backend]
    unit: example-backend.service
    ready:
      type: log
      path: /var/log/example/backend.log
      regex: 'Application ready'
      timeout: 300

  - name: worker
    groups: [worker]
    unit: example-worker.service

  - name: api
    groups: [api]
    unit: example-api.service
    hooks:
      before_stop:
        - tasks: hooks/prepare_shutdown.yml

  - name: frontend
    groups: [frontend, edge]
    unit: example-frontend.service
```

The `ready` and `hooks` fields above show the target MVP interface. Until their implementation lands, the planner rejects them instead of silently changing services without the requested safeguards.

The declared order is the start order. Stop uses the exact reverse order. Restart performs a complete stop followed by a complete start.

## MVP

The first release is limited to:

- ordered start and reverse-order stop;
- restart as full stop plus full start;
- target resolution from inventory groups;
- `manage` and `exclude_groups` selection;
- native task-file hooks around service transitions;
- readiness through systemd state or a new log entry;
- check-mode planning;
- structured results and clear validation errors.

Arbitrary dependency graphs, parallel execution, rolling restarts, containers and platform-specific application integrations are intentionally deferred.

See [the MVP design](docs/DESIGN.md) and [issue #1](https://github.com/mrAibo/ansible_serviceflow/issues/1).

## License

GPL-3.0-or-later.
