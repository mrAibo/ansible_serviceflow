# Migration and comparison

## What ServiceFlow is

ServiceFlow is a small orchestration layer for ordered, cross-host systemd application lifecycles.

It does not replace standard Ansible modules. It composes them into one validated global workflow and adds two missing application-level concepts:

- lifecycle hooks at explicit transition boundaries;
- readiness that can require a new log record from the current start.

## What standard Ansible already does well

### `ansible.builtin.systemd_service`

Use the standard module when one task needs to manage one unit on the current or delegated host.

It provides:

- idempotent `started` and `stopped` states;
- check mode;
- native systemd interaction;
- returned `systemctl show` data;
- enablement, masking and daemon-reload controls when explicitly requested.

ServiceFlow deliberately continues to use this module for every service transition.

### `ansible.builtin.wait_for`

Use it for normal port waits, file existence and simple regex waits where historical content is acceptable.

ServiceFlow does not duplicate those general capabilities. Its log readiness exists because a startup workflow often needs a stricter boundary: an old matching line must not prove that the current start succeeded.

### `ansible.builtin.uri`

Use it directly for HTTP operations and application APIs. In ServiceFlow, such calls belong in project-owned hook task files.

### `ansible.builtin.service_facts`

Use it when a play needs a broad inventory of service states. ServiceFlow only reads the state required for the current unit and transition.

## Why a normal playbook can be insufficient

Consider a conventional multi-host play:

```yaml
- hosts: application_cluster
  tasks:
    - name: Start the local service
      ansible.builtin.systemd_service:
        name: "{{ local_unit }}"
        state: started
```

Ansible coordinates tasks across hosts according to play strategy and batching. A loop inside one task does not automatically create a global dependency sequence across different inventory groups.

For an application requiring:

```text
first tier ready → second tier ready → third tier
```

operators often create multiple plays, repeated delegation, group-specific conditions and manually duplicated reverse stop logic. ServiceFlow turns this into one ordered data structure.

## Comparison table

| Capability | Standard module/task | `community.general` style utilities | ServiceFlow |
|---|---|---|---|
| Manage one systemd unit | Excellent | Usually unnecessary | Uses `ansible.builtin.systemd_service` |
| Global order across inventory groups | Manual plays/delegation | No general application lifecycle contract | Built in |
| Automatic reverse stop order | Manual duplication | Usually not provided | Built in |
| Full-stack restart | Manual stop play plus start play | Usually not provided | Built in |
| Host resolution from multiple groups | Manual Jinja/loops | Varies by module | Built in with deduplication |
| Exclude maintenance hosts | Manual conditions | Varies | `exclude_groups` |
| Application shutdown step before unit stop | Separate tasks and conditions | Application-specific | `before_stop` task-file hook |
| Run task after actual readiness | Manual blocks | Application-specific | `after_ready` |
| Ignore historical matching log lines | Requires custom offset logic | General regex waits usually see old content | Built-in current-start boundary |
| Fail before any change on malformed full definition | Must be designed manually | Module validates only its invocation | Whole ServiceFlow definition validated first |
| Structured result for the complete lifecycle | Manual aggregation | Per-module results | Built in |
| Parallel or rolling execution | Native Ansible patterns available | Some specialized roles | Not in 0.1.0 |
| HTTP/port readiness | Standard modules already good | Standard/community utilities available | Deferred in 0.1.0 |

## Why not use a broad community collection instead

Community collections contain many valuable modules and plugins, but they generally solve individual resource operations. They cannot know an application's intended global lifecycle order, shutdown protocol or definition of readiness.

ServiceFlow is different because its primary abstraction is not a new systemd operation. It is the application lifecycle contract:

```text
ordered service definitions
+ inventory target resolution
+ transition-aware hooks
+ readiness boundary
+ reverse stop
+ structured result
```

The project stays intentionally small and relies on built-in modules wherever they already solve the problem.

## When not to use ServiceFlow

Do not use ServiceFlow when:

- only one unit on one host needs management;
- native systemd dependencies on the same host fully express the requirement;
- the application is Kubernetes-native;
- rolling updates or parallel batches are mandatory;
- the dependency structure is a complex graph rather than an ordered chain;
- HTTP or port readiness alone can be handled clearly by a few normal tasks;
- a vendor-provided role already implements the complete supported lifecycle.

For same-host units, first consider correct native systemd relationships such as `After=`, `Requires=` and an appropriate service `Type=`. Cross-host ordering and application-level readiness cannot generally be expressed by one host's systemd manager.

## Migration from a conventional playbook

### Before: shell and sudo

```yaml
- name: Start a unit
  ansible.builtin.shell: sudo systemctl start example.service
```

### After: declarative entry

```yaml
serviceflow_services:
  - name: application
    groups: [application]
    unit: example-application.service
```

ServiceFlow uses `become` and `ansible.builtin.systemd_service`; no shell-level sudo is required.

### Before: repeated group conditions

```yaml
when: "'frontend' in group_names or 'edge' in group_names"
```

### After

```yaml
groups:
  - frontend
  - edge
```

### Before: separate manually reversed stop list

```text
start: first, second, third
stop: third, second, first
```

### After

Declare one list. Stop reverses it automatically.

### Before: delete an old readiness line

```yaml
- ansible.builtin.lineinfile:
    path: /var/log/example/application.log
    regexp: '^Application ready$'
    state: absent
```

This mutates operational evidence and may remove legitimate historical records.

### After

```yaml
ready:
  type: log
  path: /var/log/example/application.log
  regex: '^Application ready$'
```

ServiceFlow records the pre-start boundary and leaves the file unchanged.

### Before: application-specific tasks mixed into orchestration

A large playbook may fetch state, loop over components, call APIs, stop units and wait for logs in one file.

### After

- generic order and units stay in `serviceflow_services`;
- application behavior moves into normal project-owned hook task files;
- the collection remains reusable and product-neutral.

## Suggested migration sequence

1. Document the real start order and stop order.
2. Confirm stop is the exact reverse or identify exceptions that remain outside 0.1.0.
3. Replace shell-level systemctl calls with service entries.
4. Map group-based conditions to `groups` and `exclude_groups`.
5. Convert simple enable/disable feature conditions to evaluated `manage` booleans.
6. Move pre-stop and post-start application operations into hooks.
7. Add systemd readiness first.
8. Add new-log readiness only where the current start must emit a specific record.
9. Run syntax check and check mode.
10. Test in a maintenance environment before replacing the original playbook.
11. Keep the old playbook available for rollback during the first adoption window, but do not run both orchestration paths concurrently.

## Design philosophy

ServiceFlow follows four rules:

1. Use Ansible built-ins for resource operations.
2. Add only orchestration semantics missing from those operations.
3. Validate the complete lifecycle before mutation.
4. Keep application-specific behavior in the consuming project.