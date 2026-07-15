# Development rules

Apply the Ponytail ladder before changing code:

1. Confirm the change is needed.
2. Reuse existing project code and Ansible functionality.
3. Prefer Python's standard library and native systemd features.
4. Add no dependency unless the existing platform cannot solve the problem cleanly.
5. Make the smallest understandable change in the correct place.

Project-specific constraints:

- ServiceFlow orchestrates `ansible.builtin.systemd_service`; it does not reimplement systemd operations.
- Keep the public model as an ordered service list until a real requirement proves that a dependency graph is necessary.
- Start uses declared order; stop uses the exact reverse; restart is full stop followed by full start.
- Resolve hosts from inventory data, not from the orchestrator host's `group_names`.
- Hooks reference native Ansible task files. Do not embed or interpret arbitrary task dictionaries from variables.
- Product-specific behavior belongs in consumer hook files, not collection core.
- An old log line must never satisfy readiness for a new service start.
- Validate the complete plan before changing the first service.
- Check mode must not change services or wait for events that can only occur after a change.
- Never hide hook or readiness failures with unconditional `ignore_errors`.
- Non-trivial behavior needs the smallest runnable test that fails when the behavior breaks.
