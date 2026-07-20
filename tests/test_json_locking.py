"""Concurrency and safety tests for JSON advisory locks."""

import json
import multiprocessing
import os
import stat
import threading

import pytest


def _append_worker(root_dir: str, worker_id: int, count: int, start_event) -> None:
    from xcrawler.storage.json_store import JsonStore

    store = JsonStore(root_dir, lock_timeout=10.0)
    start_event.wait()
    for index in range(count):
        store.append_json_record("events.json", {"worker": worker_id, "index": index})


class TestJsonFileLock:
    def test_append_is_atomic_across_processes(self, tmp_path):
        worker_count = 4
        records_per_worker = 10
        context = multiprocessing.get_context("spawn")
        start_event = context.Event()
        processes = [
            context.Process(
                target=_append_worker,
                args=(str(tmp_path), worker_id, records_per_worker, start_event),
            )
            for worker_id in range(worker_count)
        ]

        for process in processes:
            process.start()
        start_event.set()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0

        records = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))
        assert len(records) == worker_count * records_per_worker
        assert {(record["worker"], record["index"]) for record in records} == {
            (worker_id, index)
            for worker_id in range(worker_count)
            for index in range(records_per_worker)
        }

    def test_timeout_preserves_primary_file(self, tmp_path):
        from xcrawler.storage.file_lock import file_lock
        from xcrawler.storage.json_store import JsonLockTimeout, save_json

        path = tmp_path / "data.json"
        save_json(str(path), {"version": 1})

        with file_lock(str(path)):
            with pytest.raises(JsonLockTimeout, match="获取文件锁超时"):
                save_json(str(path), {"version": 2}, lock_timeout=0.05)

        assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}

    def test_multi_file_transactions_use_stable_lock_order(self, tmp_path):
        from xcrawler.storage.json_store import load_json, replace_json_files_atomically

        first = str(tmp_path / "first.json")
        second = str(tmp_path / "second.json")
        barrier = threading.Barrier(2)
        failures: list[BaseException] = []

        def update_pair(marker: str, reverse: bool) -> None:
            try:
                barrier.wait(timeout=5)
                for sequence in range(10):
                    pairs = [
                        (first, {"marker": marker, "sequence": sequence}),
                        (second, {"marker": marker, "sequence": sequence}),
                    ]
                    if reverse:
                        pairs.reverse()
                    replace_json_files_atomically(dict(pairs), lock_timeout=5.0)
            except BaseException as error:
                failures.append(error)

        threads = [
            threading.Thread(target=update_pair, args=("a", False)),
            threading.Thread(target=update_pair, args=("b", True)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert not failures
        assert all(not thread.is_alive() for thread in threads)
        assert load_json(first) == load_json(second)

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission semantics")
    def test_lock_file_uses_private_permissions(self, tmp_path):
        from xcrawler.storage.json_store import save_json

        path = tmp_path / "data.json"
        save_json(str(path), {"safe": True})

        lock_path = tmp_path / "data.json.lock"
        assert lock_path.is_file()
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

    @pytest.mark.skipif(os.name != "posix", reason="POSIX symlink semantics")
    def test_symlinked_lock_file_is_rejected(self, tmp_path):
        from xcrawler.paths import UnsafePathError
        from xcrawler.storage.json_store import save_json

        path = tmp_path / "data.json"
        outside = tmp_path / "outside.lock"
        outside.write_text("keep", encoding="utf-8")
        (tmp_path / "data.json.lock").symlink_to(outside)

        with pytest.raises(UnsafePathError, match="符号链接锁文件"):
            save_json(str(path), {"unsafe": True})
        assert outside.read_text(encoding="utf-8") == "keep"
        assert not path.exists()

    @pytest.mark.skipif(os.name != "posix", reason="POSIX hard-link semantics")
    def test_hard_linked_lock_file_is_rejected_without_chmod(self, tmp_path):
        from xcrawler.paths import UnsafePathError
        from xcrawler.storage.json_store import save_json

        path = tmp_path / "data.json"
        outside = tmp_path / "outside.lock"
        outside.write_text("keep", encoding="utf-8")
        outside.chmod(0o644)
        os.link(outside, tmp_path / "data.json.lock")

        with pytest.raises(UnsafePathError, match="普通文件"):
            save_json(str(path), {"unsafe": True})
        assert stat.S_IMODE(outside.stat().st_mode) == 0o644
        assert outside.read_text(encoding="utf-8") == "keep"

    @pytest.mark.parametrize("timeout", [-0.001, -1.0])
    def test_negative_timeout_is_rejected(self, tmp_path, timeout):
        from xcrawler.storage.json_store import JsonStore, load_json

        with pytest.raises(ValueError, match="timeout"):
            JsonStore(str(tmp_path), lock_timeout=timeout)
        with pytest.raises(ValueError, match="timeout"):
            load_json(str(tmp_path / "data.json"), lock_timeout=timeout)
