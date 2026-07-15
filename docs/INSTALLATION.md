# Installation and compatibility

## Requirements

ServiceFlow requires:

- `ansible-core` 2.15 or newer on the control node;
- Linux managed hosts using systemd;
- Python available on managed hosts for normal Ansible module execution;
- privilege escalation when the connecting user cannot manage units or read readiness logs.

The collection has no external Python dependencies. Service transitions use `ansible.builtin.systemd_service`; only the new-log-entry boundary is implemented by the collection module.

## Install from Ansible Galaxy

After publication:

```bash
ansible-galaxy collection install mraibo.serviceflow
```

Install an exact version for reproducible automation:

```bash
ansible-galaxy collection install mraibo.serviceflow:0.1.0
```

## Install with `requirements.yml`

```yaml
---
collections:
  - name: mraibo.serviceflow
    version: "0.1.0"
```

```bash
ansible-galaxy collection install -r requirements.yml
```

Commit `requirements.yml` to the consuming project. Do not depend implicitly on whichever version happens to be installed on an operator workstation.

## Install from a Git tag

Before Galaxy publication, or when testing a repository tag:

```yaml
---
collections:
  - name: https://github.com/mrAibo/ansible_serviceflow.git
    type: git
    version: "0.1.0"
```

## Install a locally built artifact

```bash
git clone https://github.com/mrAibo/ansible_serviceflow.git
cd ansible_serviceflow
git switch --detach 0.1.0

mkdir -p build
ansible-galaxy collection build --output-path build
ansible-galaxy collection install \
  build/mraibo-serviceflow-0.1.0.tar.gz \
  --force
```

## Verify the installation

```bash
ansible-galaxy collection list mraibo.serviceflow
ansible-doc -t role mraibo.serviceflow.lifecycle
ansible-doc mraibo.serviceflow.log_readiness
```

## Privilege escalation

The default is:

```yaml
serviceflow_become: true
```

This applies to service management, readiness operations and hook task files. Set it to `false` only when the connecting account already has all required permissions.

ServiceFlow does not configure sudoers. Privilege policy remains the responsibility of the consuming environment.

## Unsupported platforms in 0.1.0

Version 0.1.0 does not manage:

- SysV init;
- OpenRC;
- launchd;
- Windows services;
- containers or Kubernetes workloads.

It also does not create systemd dependency units or modify unit enablement.