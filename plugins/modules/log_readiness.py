#!/usr/bin/python

# Copyright: (c) 2026 Aleksej Voronin
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

DOCUMENTATION = r'''
---
module: log_readiness
short_description: Wait for a regular expression in newly written log data
version_added: "0.1.0"
description:
  - Captures a file identity, byte offset and content anchor before a service transition.
  - Waits only in data written after that boundary.
  - Handles file creation, copy-truncate and rename-based rotation.
  - Treats bytes already present when a replacement inode is first observed as its new boundary.
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
    description: Supports boundary capture and readiness waits without changing managed files.
    support: full
author:
  - Aleksej Voronin (@mrAibo)
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
  description: Captured file identity, byte offset and content anchor.
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
  description: Number of detected truncations or same-inode rewrites.
  returned: action is wait
  type: int
'''

import codecs
import hashlib
import os
import re
import stat
import time

_ANCHOR_SIZE = 4096
_CHUNK_SIZE = 64 * 1024
_TAIL_LIMIT = 64 * 1024


class LogReadinessTimeout(Exception):
    def __init__(self, result):
        super().__init__("log readiness timed out")
        self.result = result


def _missing_boundary():
    return {
        "exists": False,
        "device": None,
        "inode": None,
        "offset": 0,
        "anchor_offset": 0,
        "anchor_length": 0,
        "anchor_sha256": None,
    }


def _regular_stat(path):
    try:
        file_stat = os.stat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError(f"log path is not a regular file: {path}")
    return file_stat


def _anchor_from_stream(stream, offset):
    length = min(offset, _ANCHOR_SIZE)
    anchor_offset = offset - length
    stream.seek(anchor_offset)
    data = stream.read(length)
    return {
        "anchor_offset": anchor_offset,
        "anchor_length": len(data),
        "anchor_sha256": hashlib.sha256(data).hexdigest(),
    }


def _anchor(path, offset):
    with open(path, "rb") as stream:
        return _anchor_from_stream(stream, offset)


def capture_boundary(path):
    try:
        with open(path, "rb") as stream:
            file_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise ValueError(f"log path is not a regular file: {path}")
            offset = file_stat.st_size
            return {
                "exists": True,
                "device": file_stat.st_dev,
                "inode": file_stat.st_ino,
                "offset": offset,
                **_anchor_from_stream(stream, offset),
            }
    except FileNotFoundError:
        return _missing_boundary()


def _normalized_boundary(boundary):
    if not isinstance(boundary, dict):
        raise ValueError("boundary must be a mapping")
    exists = boundary.get("exists")
    if not isinstance(exists, bool):
        raise ValueError("boundary.exists must be a boolean")
    if not exists:
        return _missing_boundary()

    normalized = {"exists": True}
    for key in ("device", "inode", "offset", "anchor_offset", "anchor_length"):
        value = boundary.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"boundary.{key} must be a non-negative integer")
        normalized[key] = value

    digest = boundary.get("anchor_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("boundary.anchor_sha256 must be a SHA-256 hex digest")
    normalized["anchor_sha256"] = digest
    return normalized


def _anchor_matches(path, tracked):
    if tracked.get("anchor_sha256") is None:
        return True
    try:
        with open(path, "rb") as stream:
            stream.seek(tracked["anchor_offset"])
            data = stream.read(tracked["anchor_length"])
    except FileNotFoundError:
        return False
    return (
        len(data) == tracked["anchor_length"]
        and hashlib.sha256(data).hexdigest() == tracked["anchor_sha256"]
    )


def _refresh_anchor(path, tracked):
    try:
        tracked.update(_anchor(path, tracked["offset"]))
    except FileNotFoundError:
        tracked.update(
            {
                "anchor_offset": 0,
                "anchor_length": 0,
                "anchor_sha256": None,
            }
        )


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
            if stat.S_ISREG(entry_stat.st_mode) and _identity_matches(entry_stat, tracked):
                return entry.path, entry_stat
    return None, None


def _new_decoder():
    return codecs.getincrementaldecoder("utf-8")(errors="replace")


def _read_new_data(path, offset, pattern, buffer, decoder):
    bytes_read = 0
    with open(path, "rb") as stream:
        stream.seek(offset)
        while True:
            chunk = stream.read(_CHUNK_SIZE)
            if not chunk:
                break
            offset += len(chunk)
            bytes_read += len(chunk)
            buffer += decoder.decode(chunk, final=False)
            if pattern.search(buffer):
                return offset, buffer, decoder, True, bytes_read
            if len(buffer) > _TAIL_LIMIT:
                buffer = buffer[-_TAIL_LIMIT:]
    return offset, buffer, decoder, False, bytes_read


def _tracked_from_boundary(boundary):
    if not boundary["exists"]:
        return None
    return dict(boundary)


def _new_tracking(file_stat):
    return {
        "device": file_stat.st_dev,
        "inode": file_stat.st_ino,
        "offset": 0,
        "anchor_offset": 0,
        "anchor_length": 0,
        "anchor_sha256": None,
    }


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


def _matched_result(path, tracked, started, bytes_read, rotations, truncations):
    return {
        "matched": True,
        "elapsed": time.monotonic() - started,
        "bytes_read": bytes_read,
        "rotations": rotations,
        "truncations": truncations,
        **_state_snapshot(path, tracked),
    }


def wait_for_match(path, regex, boundary, timeout, interval):
    pattern = re.compile(regex, re.MULTILINE)
    tracked = _tracked_from_boundary(_normalized_boundary(boundary))
    started = time.monotonic()
    deadline = started + timeout
    buffer = ""
    decoder = _new_decoder()
    bytes_read = 0
    rotations = 0
    truncations = 0

    while True:
        if tracked is not None:
            tracked_path, tracked_stat = _locate_identity(path, tracked)
            if tracked_path is not None:
                if tracked_stat.st_size < tracked["offset"] or not _anchor_matches(tracked_path, tracked):
                    tracked["offset"] = 0
                    tracked["anchor_sha256"] = None
                    buffer = ""
                    decoder = _new_decoder()
                    truncations += 1
                tracked["offset"], buffer, decoder, matched, read_count = _read_new_data(
                    tracked_path,
                    tracked["offset"],
                    pattern,
                    buffer,
                    decoder,
                )
                bytes_read += read_count
                if matched:
                    return _matched_result(path, tracked, started, bytes_read, rotations, truncations)
                _refresh_anchor(tracked_path, tracked)

        current_stat = _regular_stat(path)
        if current_stat is not None and not _identity_matches(current_stat, tracked):
            was_tracked = tracked is not None
            if was_tracked:
                rotations += 1
            tracked = _new_tracking(current_stat)
            buffer = ""
            decoder = _new_decoder()
            if was_tracked:
                tracked["offset"] = current_stat.st_size

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
            "action": {"type": "str", "required": True, "choices": ["capture", "wait"]},
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
            msg=f"timed out after {timeout} seconds waiting for regex in new data from {path}",
            **error.result,
        )
    except (OSError, ValueError) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
