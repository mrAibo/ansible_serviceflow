import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins" / "modules" / "log_readiness.py"
SPEC = importlib.util.spec_from_file_location("log_readiness", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def later(callback, delay=0.05):
    thread = threading.Thread(target=lambda: (time.sleep(delay), callback()))
    thread.start()
    return thread


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "application.log"

        path.write_text("Application ready\n", encoding="utf-8")
        boundary = MODULE.capture_boundary(path)
        thread = later(
            lambda: path.open("a", encoding="utf-8").write("Application ready\n")
        )
        result = MODULE.wait_for_match(
            str(path),
            "Application ready",
            boundary,
            1,
            0.01,
        )
        thread.join()
        assert result["matched"]
        assert result["bytes_read"] > 0
        assert result["rotations"] == 0
        assert result["truncations"] == 0

        path.write_text("old data\n", encoding="utf-8")
        boundary = MODULE.capture_boundary(path)
        thread = later(lambda: path.write_text("Application ready\n", encoding="utf-8"))
        result = MODULE.wait_for_match(str(path), "Application ready", boundary, 1, 0.01)
        thread.join()
        assert result["matched"]
        assert result["truncations"] == 1

        path.write_text("old data\n", encoding="utf-8")
        boundary = MODULE.capture_boundary(path)
        rotated = Path(directory) / "application.log.1"
        historical_line = "Application ready historical\n"
        current_line = "Application ready current\n"

        def rotate():
            os.rename(path, rotated)
            with path.open("wb") as stream:
                stream.write(historical_line.encode("utf-8"))
            time.sleep(0.3)
            with path.open("ab") as stream:
                stream.write(current_line.encode("utf-8"))

        thread = later(rotate)
        result = MODULE.wait_for_match(str(path), "^Application ready", boundary, 1, 0.01)
        thread.join()
        assert result["matched"]
        assert result["bytes_read"] == len(current_line.encode("utf-8"))
        assert result["rotations"] == 1

        path.unlink()
        boundary = MODULE.capture_boundary(path)
        assert not boundary["exists"]
        thread = later(lambda: path.write_text("Application ready\n", encoding="utf-8"))
        result = MODULE.wait_for_match(str(path), "Application ready", boundary, 1, 0.01)
        thread.join()
        assert result["matched"]
        assert result["path_exists"]

        path.write_text("Application ready\n", encoding="utf-8")
        boundary = MODULE.capture_boundary(path)
        try:
            MODULE.wait_for_match(str(path), "Application ready", boundary, 0.05, 0.01)
        except MODULE.LogReadinessTimeout as error:
            assert not error.result["matched"]
            assert error.result["bytes_read"] == 0
        else:
            raise AssertionError("old matching data satisfied readiness")

        def fail_path_stat(*_args, **_kwargs):
            raise AssertionError("capture_boundary must not call path-based os.stat")

        original_stat = MODULE.os.stat
        MODULE.os.stat = fail_path_stat
        try:
            boundary = MODULE.capture_boundary(path)
            assert boundary["exists"]
        finally:
            MODULE.os.stat = original_stat

        path.write_bytes(b"")
        boundary = MODULE.capture_boundary(path)
        original_chunk_size = MODULE._CHUNK_SIZE
        MODULE._CHUNK_SIZE = 3
        try:
            thread = later(
                lambda: path.write_text("Prefix ✅ Application ready\n", encoding="utf-8")
            )
            result = MODULE.wait_for_match(
                str(path),
                "✅ Application ready",
                boundary,
                1,
                0.01,
            )
            thread.join()
            assert result["matched"]
        finally:
            MODULE._CHUNK_SIZE = original_chunk_size

    print("Log readiness tests passed")


if __name__ == "__main__":
    main()
