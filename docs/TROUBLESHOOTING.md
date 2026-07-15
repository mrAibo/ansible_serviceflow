# Troubleshooting

## Start with the plan

Use syntax check and check mode before changing services:

```bash
ansible-playbook -i inventory.ini lifecycle.yml --syntax-check
ansible-playbook -i inventory.ini lifecycle.yml --check -e requested_action=restart
```

For runtime failures, rerun with additional verbosity:

```bash
ansible-playbook -i inventory.ini lifecycle.yml -vvv -e requested_action=start
```

## `unsupported action`

Cause: `serviceflow_action` is not `start`, `stop` or `restart`.

Fix the value supplied by variables or `-e`.

## `missing inventory group`

Cause: a service references a group not present in the selected inventory.

Check:

```bash
ansible-inventory -i inventory.ini --graph
```

Do not create empty placeholder groups to hide an inventory mistake. Correct the inventory or service definition.

## `resolves to no target hosts`

Possible causes:

- all positive groups are empty;
- every resolved host is also in an `exclude_groups` group;
- the wrong inventory file was selected.

This is a fail-fast error before service changes.

## Duplicate service name

Every logical `name` must be unique, even when units or groups differ. The name is the stable result and hook identifier.

## `manage must be a boolean`

Wrong:

```yaml
manage: "false"
```

Correct:

```yaml
manage: false
```

or:

```yaml
manage: "{{ feature_enabled | bool }}"
```

## Unsupported service fields

ServiceFlow rejects unknown keys instead of silently ignoring them. Check spelling against [REFERENCE.md](REFERENCE.md).

## Hook task file not found

Relative paths are resolved from `playbook_dir`.

Example layout:

```text
project/
├── playbooks/
│   └── lifecycle.yml
└── hooks/
    └── prepare.yml
```

The task reference from `playbooks/lifecycle.yml` is:

```yaml
tasks: ../hooks/prepare.yml
```

Use `{{ playbook_dir }}` mentally as the starting directory. Do not duplicate directory names.

## Hook failed before stop

A failing `before_stop` hook intentionally prevents the unit from being stopped. Fix the application shutdown step or implement an explicit, reviewed recovery path inside the hook task file.

Avoid broad `ignore_errors: true`; it can convert a failed safety boundary into a destructive stop.

## Permission denied

Confirm:

```yaml
serviceflow_become: true
```

Then verify the Ansible connection account can use become for:

- `systemctl show/start/stop` through Ansible modules;
- reading the configured log path;
- any operations performed by hooks.

ServiceFlow does not modify sudoers.

## Systemd readiness timeout

Inspect the unit:

```bash
systemctl show example-application.service \
  -p ActiveState -p SubState -p Result
systemctl status example-application.service --no-pager
journalctl -u example-application.service -n 100 --no-pager
```

Common causes:

- expected `sub_state` does not match the unit type;
- the process exits after systemd reports a short-lived start;
- the application requires more time than `timeout`;
- `Type=` in the unit does not model the real startup boundary.

Prefer correcting readiness semantics over adding an arbitrary sleep.

## Log readiness timeout with an old matching line present

This is expected. Existing matching content is deliberately ignored. Only bytes written after the current start boundary can satisfy readiness.

Check whether the current start actually writes the configured message and path.

## Log readiness skipped with `no_start_transition`

The unit was already active. Waiting for a new startup line would never complete reliably, so ServiceFlow records the log check as skipped.

Use systemd readiness when an already-running service must always be verified. Use a separate application health-check hook when deeper validation is required.

## Service started but readiness failed

Version 0.1.0 does not roll back a successfully started unit after readiness timeout. The lifecycle stops before later services.

Inspect and decide explicitly whether to:

- fix the application and retry;
- stop the unit manually;
- run the normal ServiceFlow stop action;
- add project-specific recovery outside the current run.

## Rotation count remains zero

A process may keep an already-open file descriptor and continue writing to the renamed inode. That is normal Unix behavior. ServiceFlow follows the old inode when possible and then the new configured path, but the exact counter depends on which identity received the new data.

Readiness success and preservation of new-only semantics are more important than forcing a particular counter in an application-level test.

## Regex problems

Invalid regex syntax fails during validation. A valid but overly strict expression may still time out.

Remember that `^` and `$` behavior depends on the record and newline context. Test the intended expression against representative neutral log lines before production rollout.

## The next service did not run

ServiceFlow stops on the first hook, systemd or readiness failure. This is intentional: continuing would violate the declared dependency order.

## Check mode did not execute hooks or readiness

That is expected. Hooks may mutate external systems, and future readiness events cannot occur without starting services. Check mode validates and predicts but does not simulate application behavior.

## Diagnostic bundle

Collect only non-sensitive information:

```bash
ansible --version
ansible-galaxy collection list mraibo.serviceflow
ansible-inventory -i inventory.ini --graph
systemctl show <unit> -p ActiveState -p SubState -p Result
journalctl -u <unit> -n 100 --no-pager
```

Redact real hostnames, addresses, credentials, tokens and proprietary log contents before publishing an issue.