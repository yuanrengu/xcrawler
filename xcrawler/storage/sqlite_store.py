from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from xcrawler.paths import ensure_private_dir, protect_private_file, reject_symlink
from xcrawler.storage.base import Storage
from xcrawler.storage.keys import ANALYSIS_RUNS_KEY, LLM_CALLS_KEY

SQLITE_SCHEMA_VERSION = 1


class SQLiteStoreError(RuntimeError):
    """Raised when the SQLite metadata store cannot complete an operation."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str) -> Any:
    return json.loads(value)


class SQLiteStore(Storage):
    """SQLite-backed metadata store with structured run and LLM call tables."""

    def __init__(self, path: str, *, timeout: float = 5.0):
        if not path:
            raise ValueError("SQLite path must not be empty")
        if timeout <= 0:
            raise ValueError("SQLite timeout must be > 0")
        self.path = path
        self.timeout = timeout
        if path != ":memory:":
            ensure_private_dir(os.path.dirname(os.path.abspath(path)))
            self._validate_files()
        self._memory_connection: sqlite3.Connection | None = None
        self._initialize()

    def _new_connection(self) -> sqlite3.Connection:
        if self.path != ":memory:":
            self._validate_files()
        connection = sqlite3.connect(self.path, timeout=self.timeout)
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {int(self.timeout * 1000)}")
        connection.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            self._protect_files()
        return connection

    def _managed_files(self) -> tuple[str, ...]:
        return (self.path, f"{self.path}-wal", f"{self.path}-shm")

    def _validate_files(self) -> None:
        for path in self._managed_files():
            reject_symlink(path, label="SQLite 文件")

    def _protect_files(self) -> None:
        for path in self._managed_files():
            protect_private_file(path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if self.path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = self._new_connection()
            yield self._memory_connection
            return

        connection = self._new_connection()
        try:
            yield connection
        finally:
            connection.close()
            self._protect_files()

    def _initialize(self) -> None:
        try:
            with self._connection() as connection:
                metadata_exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'store_metadata'"
                ).fetchone()
                if metadata_exists:
                    version_row = connection.execute(
                        "SELECT metadata_value FROM store_metadata WHERE metadata_key = 'schema_version'"
                    ).fetchone()
                    if version_row is None or version_row["metadata_value"] != str(SQLITE_SCHEMA_VERSION):
                        found = None if version_row is None else version_row["metadata_value"]
                        raise SQLiteStoreError(
                            f"不支持的 SQLite schema version: {found}; expected {SQLITE_SCHEMA_VERSION}"
                        )

                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS store_metadata (
                        metadata_key TEXT PRIMARY KEY,
                        metadata_value TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS json_documents (
                        storage_key TEXT PRIMARY KEY,
                        value_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS analysis_runs (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        id TEXT NOT NULL UNIQUE,
                        username TEXT,
                        analysis_type TEXT,
                        model TEXT,
                        started_at TEXT,
                        completed_at TEXT,
                        status TEXT,
                        duration_ms INTEGER,
                        error_type TEXT,
                        error_message TEXT,
                        llm_calls INTEGER,
                        total_tokens INTEGER,
                        failed_batches INTEGER,
                        params_json TEXT,
                        input_range_json TEXT,
                        config_json TEXT,
                        payload_json TEXT NOT NULL,
                        recorded_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_analysis_runs_username_started
                    ON analysis_runs(username, started_at);
                    CREATE INDEX IF NOT EXISTS idx_analysis_runs_type_status
                    ON analysis_runs(analysis_type, status);

                    CREATE TABLE IF NOT EXISTS llm_calls (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        id TEXT NOT NULL UNIQUE,
                        analysis_run_id TEXT,
                        username TEXT,
                        operation TEXT,
                        provider TEXT,
                        model TEXT,
                        started_at TEXT,
                        completed_at TEXT,
                        status TEXT,
                        attempt INTEGER,
                        latency_ms INTEGER,
                        prompt_tokens INTEGER,
                        completion_tokens INTEGER,
                        total_tokens INTEGER,
                        estimated_cost REAL,
                        error_type TEXT,
                        error_message TEXT,
                        payload_json TEXT NOT NULL,
                        recorded_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_llm_calls_run_started
                    ON llm_calls(analysis_run_id, started_at);
                    CREATE INDEX IF NOT EXISTS idx_llm_calls_username_started
                    ON llm_calls(username, started_at);
                    CREATE INDEX IF NOT EXISTS idx_llm_calls_provider_model
                    ON llm_calls(provider, model);
                    CREATE INDEX IF NOT EXISTS idx_llm_calls_status
                    ON llm_calls(status);
                    """
                )
                connection.execute(
                    """
                    INSERT INTO store_metadata(metadata_key, metadata_value)
                    VALUES ('schema_version', ?)
                    ON CONFLICT(metadata_key) DO NOTHING
                    """,
                    (str(SQLITE_SCHEMA_VERSION),),
                )
                connection.commit()
        except SQLiteStoreError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise SQLiteStoreError(f"无法初始化 SQLite Store: {self.path}") from error

    def load_json(self, key: str, default: Any = None) -> Any:
        try:
            with self._connection() as connection:
                if key == ANALYSIS_RUNS_KEY:
                    return self._load_payloads(connection, "analysis_runs")
                if key == LLM_CALLS_KEY:
                    return self._load_payloads(connection, "llm_calls")
                row = connection.execute(
                    "SELECT value_json FROM json_documents WHERE storage_key = ?",
                    (key,),
                ).fetchone()
                return default if row is None else _json_loads(row["value_json"])
        except (json.JSONDecodeError, sqlite3.Error) as error:
            raise SQLiteStoreError(f"无法读取 SQLite Storage key: {key}") from error

    def save_json(self, key: str, data: Any) -> None:
        try:
            with self._connection() as connection:
                with connection:
                    if key == ANALYSIS_RUNS_KEY:
                        self._replace_records(connection, "analysis_runs", data, self._insert_analysis_run)
                    elif key == LLM_CALLS_KEY:
                        self._replace_records(connection, "llm_calls", data, self._insert_llm_call)
                    else:
                        connection.execute(
                            """
                            INSERT INTO json_documents(storage_key, value_json, updated_at)
                            VALUES (?, ?, ?)
                            ON CONFLICT(storage_key) DO UPDATE SET
                                value_json = excluded.value_json,
                                updated_at = excluded.updated_at
                            """,
                            (key, _json_dumps(data), _utc_now_iso()),
                        )
        except (TypeError, ValueError, sqlite3.Error) as error:
            raise SQLiteStoreError(f"无法保存 SQLite Storage key: {key}") from error

    def append_json_record(self, key: str, record: dict[str, Any]) -> None:
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")
        try:
            with self._connection() as connection:
                with connection:
                    if key == ANALYSIS_RUNS_KEY:
                        self._insert_analysis_run(connection, record)
                    elif key == LLM_CALLS_KEY:
                        self._insert_llm_call(connection, record)
                    else:
                        row = connection.execute(
                            "SELECT value_json FROM json_documents WHERE storage_key = ?",
                            (key,),
                        ).fetchone()
                        records = [] if row is None else _json_loads(row["value_json"])
                        if not isinstance(records, list):
                            records = []
                        records.append(record)
                        connection.execute(
                            """
                            INSERT INTO json_documents(storage_key, value_json, updated_at)
                            VALUES (?, ?, ?)
                            ON CONFLICT(storage_key) DO UPDATE SET
                                value_json = excluded.value_json,
                                updated_at = excluded.updated_at
                            """,
                            (key, _json_dumps(records), _utc_now_iso()),
                        )
        except (json.JSONDecodeError, TypeError, ValueError, sqlite3.Error) as error:
            raise SQLiteStoreError(f"无法追加 SQLite Storage record: {key}") from error

    def query_analysis_runs(
        self,
        *,
        username: str | None = None,
        analysis_type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._query_payloads(
            "analysis_runs",
            {"username": username, "analysis_type": analysis_type, "status": status},
            limit,
        )

    def query_llm_calls(
        self,
        *,
        analysis_run_id: str | None = None,
        username: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._query_payloads(
            "llm_calls",
            {
                "analysis_run_id": analysis_run_id,
                "username": username,
                "provider": provider,
                "model": model,
                "status": status,
            },
            limit,
        )

    @staticmethod
    def _load_payloads(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
        rows = connection.execute(f"SELECT payload_json FROM {table} ORDER BY sequence").fetchall()
        return [_json_loads(row["payload_json"]) for row in rows]

    def _query_payloads(
        self,
        table: str,
        filters: dict[str, str | None],
        limit: int | None,
    ) -> list[dict[str, Any]]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be >= 1")
        clauses = []
        values: list[Any] = []
        for column, value in filters.items():
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = " LIMIT ?" if limit is not None else ""
        if limit is not None:
            values.append(limit)
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    f"SELECT payload_json FROM {table}{where} ORDER BY sequence DESC{limit_sql}",
                    values,
                ).fetchall()
                return [_json_loads(row["payload_json"]) for row in rows]
        except (json.JSONDecodeError, sqlite3.Error) as error:
            raise SQLiteStoreError(f"无法查询 SQLite table: {table}") from error

    @staticmethod
    def _replace_records(connection, table, data, insert_record) -> None:
        if not isinstance(data, list) or not all(isinstance(record, dict) for record in data):
            raise ValueError(f"{table} data must be a list of dict records")
        connection.execute(f"DELETE FROM {table}")
        for record in data:
            insert_record(connection, record)

    @staticmethod
    def _require_id(record: dict[str, Any], table: str) -> str:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"{table} record requires a non-empty string id")
        return record_id

    def _insert_analysis_run(self, connection: sqlite3.Connection, record: dict[str, Any]) -> None:
        record_id = self._require_id(record, "analysis_runs")
        connection.execute(
            """
            INSERT INTO analysis_runs(
                id, username, analysis_type, model, started_at, completed_at, status,
                duration_ms, error_type, error_message, llm_calls, total_tokens,
                failed_batches, params_json, input_range_json, config_json,
                payload_json, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                record.get("username"),
                record.get("analysis_type"),
                record.get("model"),
                record.get("started_at"),
                record.get("completed_at"),
                record.get("status"),
                record.get("duration_ms"),
                record.get("error_type"),
                record.get("error_message"),
                record.get("llm_calls"),
                record.get("total_tokens"),
                record.get("failed_batches"),
                _json_dumps(record.get("params", {})),
                _json_dumps(record.get("input_range", {})),
                _json_dumps(record.get("config", {})),
                _json_dumps(record),
                _utc_now_iso(),
            ),
        )

    def _insert_llm_call(self, connection: sqlite3.Connection, record: dict[str, Any]) -> None:
        record_id = self._require_id(record, "llm_calls")
        connection.execute(
            """
            INSERT INTO llm_calls(
                id, analysis_run_id, username, operation, provider, model, started_at,
                completed_at, status, attempt, latency_ms, prompt_tokens,
                completion_tokens, total_tokens, estimated_cost, error_type,
                error_message, payload_json, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                record.get("analysis_run_id"),
                record.get("username"),
                record.get("operation"),
                record.get("provider"),
                record.get("model"),
                record.get("started_at"),
                record.get("completed_at"),
                record.get("status"),
                record.get("attempt"),
                record.get("latency_ms"),
                record.get("prompt_tokens"),
                record.get("completion_tokens"),
                record.get("total_tokens"),
                record.get("estimated_cost"),
                record.get("error_type"),
                record.get("error_message"),
                _json_dumps(record),
                _utc_now_iso(),
            ),
        )
