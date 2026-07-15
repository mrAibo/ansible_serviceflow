#!/usr/bin/python

# Copyright: (c) 2026 Aleksej Voronin
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

DOCUMENTATION = r'''
---
module: log_readiness
short_description: Wait for a regular expression in newly written log data
version_added: "0.1.0"
description:
  - Captures a file identity and byte offset before a service transition.
  - Waits only in data written after that boundary.
  - Handles file creation, copy-truncate and rename-based rotation.
options:
  action:
    description: Capture a boundary or wait from a captured boundary.
    required: true
    type: str
    choices: [capture, wait]
  path:
    description: Absolute path to the log file.
    required: true
    type: path
  regex:
    description: Python regular expression searched with multiline mode.
    type: str
  boundary:
    description: Boundary returned by a previous capture action.
    type: dict
  timeout:
    description: Maximum wait time in seconds.
    type: int
    default: 60
  interval:
    description: Poll interval in seconds.
    type: float
    default: 1.0
attributes:
  check_mode:
    support: full
author:
  - Aleksej Voronin
'''

EXAMPLES = r'''
- name: Capture current log boundary
  mraibo.serviceflow.log_readiness:
    action: capture
    path: /var/log/example/application.log
  register: log_boundary

- name: Wait for a new readiness message
  mraibo.serviceflow.log_readiness:
    action: wait
    path: /var/log/example/application.log
    regex: 'Application ready'
    boundary: "{{ log_boundary.boundary }}"
    timeout: 120
'''

RETURN = r'''
boundary:
  description: Captured file identity and byte offset.
  returned: action is capture
  type: dict
matched:
  description: Whether the expression matched new log data.
  returned: action is wait and successful
  type: bool
elapsed:
  description: Elapsed wait time in seconds.
  returned: action is wait
  type: float
bytes_read:
  description: Number of post-boundary bytes examined.
  returned: action is wait
  type: int
rotations:
  description: Number of identity changes followed at the configured path.
  returned: action is wait
  type: int
truncations:
  description: Number of detected size reductions for a tracked identity.
  returned: action is wait
  type: int
'''

import os
import re
import stat
import time

_CHUNK_SIZE = 64 * 1024
_TAIL_LIMIT = 64 * 1024


class LogReadinessTimeout(Exception):
    def __init__(self, result):
        super().__init__("log readiness timed out")
        self.result = result


def _regular_stat(path):
    try:
        file_stat = os.stat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError(f"log path is not a regular file: {path}")
    return file_stat


def capture_boundary(path):
    file_stat = _regular_stat(path)
    if file_stat is None:
        return {
            "exists": False,
            "device": None,
            "inode": None,
            "offset": 0,
        }
    return {
        "exists": True,
        "device": file_stat.st_dev,
        "inode": file_stat.st_ino,
        "offset": file_stat.st_size,
    }


def _normalized_boundary(boundary):
    if not isinstance(boundary, dict):
        raise ValueError("boundary must be a mapping")
    exists = boundary.get("exists")
    if type(exists) is not bool:
        raise ValueError("boundary.exists must be a boolean")
    if not exists:
        return {"exists": False, "device": None, "inode": None, "offset": 0}

    normalized = {"exists": True}
    for key in ("device", "inode", "offset"):
        value = boundary.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"boundary.{key} must be a non-negative integer")
        normalized[key] = value
    return normalized


def _identity_matches(file_stat, tracked):
    return (
        file_stat is not None
        and tracked is not None
        and file_stat.st_dev == tracked["device"]
        and file_stat.st_ino == tracked["inode"]
    )


def _locate_identity(path, tracked):
    current_stat = _regular_stat(path)
    if _identity_matches(current_stat, tracked):
        return path, current_stat

    directory = os.path.dirname(path) or "."
    try:
        entries = os.scandir(directory)
    except FileNotFoundError:
        return None, None

    with entries:
        for entry in entries:
            try:
                entry_stat = entry.stat(follow_symlinks=True)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                continue
            if _identity_matches(entry_stat, tracked):
                return entry.path, entry_stat
    return None, None


def _read_new_data(path, offset, pattern, buffer):
    bytes_read = 0
    with open(path, "rb") as stream:
        stream.seek(offset)
        while True:
            chunk = stream.read(_CHUNK_SIZE)
            if not chunk:
                break
            offset += len(chunk)
            bytes_read += len(chunk)
            buffer += chunk.decode("utf-8", errors="replace")
            if pattern.search(buffer):
                return offset, buffer, True, bytes_read
            if len(buffer) > _TAIL_LIMIT:
                buffer = buffer[-_TAIL_LIMIT:]
    return offset, buffer, False, bytes_read


def _state_snapshot(path, tracked):
    current_stat = _regular_stat(path)
    return {
        "path_exists": current_stat is not None,
        "path_device": current_stat.st_dev if current_stat else None,
        "path_inode": current_stat.st_ino if current_stat else None,
        "path_size": current_stat.st_size if current_stat else None,
        "tracked_device": tracked["device"] if tracked else None,
        "tracked_inode": tracked["inode"] if tracked else None,
        "tracked_offset": tracked["offset"] if tracked else 0,
    }


def wait_for_match(path, regex, boundary, timeout, interval):
    pattern = re.compile(regex, re.MULTILINE)
    boundary = _normalized_boundary(boundary)
    tracked = None
    if boundary["exists"]:
        tracked = {
            "device": boundary["device"],
            "inode": boundary["inode"],
            "offset": boundary["offset"],
        }

    started = time.monotonic()
    deadline = started + timeout
    buffer = ""
    bytes_read = 0
    rotations = 0
    truncations = 0

    while True:
        if tracked is not None:
            tracked_path, tracked_stat = _locate_identity(path, tracked)
            if tracked_path is not None:
                if tracked_stat.st_size < tracked["offset"]:
                    tracked["offset"] = 0
                    buffer = ""
                    truncations += 1
                (
                    tracked["offset"],
                    buffer,
                    matched,
                    read_count,
                ) = _read_new_data(tracked_path, tracked["offset"], pattern, buffer)
                bytes_read += read_count
                if matched:
                    return {
                        "matched": True,
                        "elapsed": time.monotonic() - started,
                        "bytes_read": bytes_read,
                        "rotations": rotations,
                        "truncations": truncations,
                        **_state_snapshot(path, tracked),
                    }

        current_stat = _regular_stat(path)
        if current_stat is not None and not _identity_matches(current_stat, tracked):
            if tracked is not None:
                rotations += 1
            tracked = {
                "device": current_stat.st_dev,
                "inode": current_stat.st_ino,
                "offset": 0,
            }
            buffer = ""
            (
                tracked["offset"],
                buffer,
                matched,
                read_count,
            ) = _read_new_data(path, 0, pattern, buffer)
            bytes_read += read_count
            if matched:
                return {
                    "matched": True,
                    "elapsed": time.monotonic() - started,
                    "bytes_read": bytes_read,
                    "rotations": rotations,
                    "truncations": truncations,
                    **_state_snapshot(path, tracked),
                }

        now = time.monotonic()
        if now >= deadline:
            raise LogReadinessTimeout(
                {
                    "matched": False,
                    "elapsed": now - started,
                    "bytes_read": bytes_read,
                    "rotations": rotations,
                    "truncations": truncations,
                    **_state_snapshot(path, tracked),
                }
            )
        time.sleep(min(interval, deadline - now))


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "action": {
                "type": "str",
                "required": True,
                "choices": ["capture", "wait"],
            },
            "path": {"type": "path", "required": True},
            "regex": {"type": "str"},
            "boundary": {"type": "dict"},
            "timeout": {"type": "int", "default": 60},
            "interval": {"type": "float", "default": 1.0},
        },
        supports_check_mode=True,
    )

    action = module.params["action"]
    path = module.params["path"]
    timeout = module.params["timeout"]
    interval = module.params["interval"]

    if not os.path.isabs(path):
        module.fail_json(msg="path must be absolute")
    if timeout <= 0:
        module.fail_json(msg="timeout must be positive")
    if interval <= 0:
        module.fail_json(msg="interval must be positive")

    try:
        if action == "capture":
            module.exit_json(changed=False, boundary=capture_boundary(path))

        regex = module.params["regex"]
        boundary = module.params["boundary"]
        if not regex:
            module.fail_json(msg="regex is required when action=wait")
        if boundary is None:
            module.fail_json(msg="boundary is required when action=wait")
        try:
            re.compile(regex, re.MULTILINE)
        except re.error as error:
            module.fail_json(msg=f"invalid regex: {error}")

        result = wait_for_match(path, regex, boundary, timeout, interval)
        module.exit_json(changed=False, **result)
    except LogReadinessTimeout as error:
        module.fail_json(
            msg=(
                f"timed out after {timeout} seconds waiting for regex "
                f"in new data from {path}"
            ),
            **error.result,
        )
    except (OSError, ValueError) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
