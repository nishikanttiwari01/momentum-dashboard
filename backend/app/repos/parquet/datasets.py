# app/repos/parquet/datasets.py
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union, List

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import re
import logging

try:
    from app.core.config import load as load_settings
except Exception:  # pragma: no cover
    load_settings = None  # type: ignore



# Optional: if you also use Polars in other places
try:
    import polars as pl  # type: ignore
except Exception:  # pragma: no cover
    pl = None  # Polars is optional for now

# -----------------------------
# Configuration helpers
# -----------------------------
log = logging.getLogger("app.repos.parquet")


def _storage_settings():
    if load_settings is None:  # pragma: no cover
        return None
    try:
        return load_settings().storage
    except Exception:
        return None


# Log the resolved parquet root once per process (for easy diagnostics)
_ROOT_LOGGED_ONCE = False
def _log_resolved_root_once(p: Path) -> None:
    global _ROOT_LOGGED_ONCE
    if not _ROOT_LOGGED_ONCE:
        try:
            log.info("parquet_root_resolved", extra={"parquet_root": str(p)})
        except Exception:
            pass
        _ROOT_LOGGED_ONCE = True

def _parquet_root_abs() -> Path:
    """
    Resolve the parquet root:
      1) If PARQUET_ROOT env is set â†’ use it (expanded + absolute).
      2) Else anchor to the repository's backend dir:
         <repo>/backend/parquet   (derived from this file's location)
    This avoids accidental paths like 'backend/backend/parquet' when the process
    starts with CWD=backend/.
    """
    env_root = os.getenv("PARQUET_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
    else:
        storage_cfg = _storage_settings()
        if storage_cfg and getattr(storage_cfg, "parquet_root", None):
            p = Path(storage_cfg.parquet_root).expanduser().resolve()
        else:
            # datasets.py is at backend/app/repos/parquet/datasets.py
            backend_dir = Path(__file__).resolve().parents[3]  # .../backend
            p = (backend_dir / "parquet").resolve()

    _log_resolved_root_once(p)

    if not p.exists():
        # Don't mkdir here; writers will create as needed. Just log once.
        try:
            log.info("parquet_root_missing_will_create_on_write", extra={"parquet_root": str(p)})
        except Exception:
            pass
    return p

def get_parquet_root() -> Path:
    # Single source of truth
    return _parquet_root_abs()

# Register known tables (phase-compatible)
TABLES = {"universe", "prices", "indicators", "scores", "scores_v2", "meta"}

def _table_root(table: str) -> Path:
    assert table in TABLES or table == "meta", f"Unknown table: {table}"
    root = get_parquet_root() / table
    root.mkdir(parents=True, exist_ok=True)
    try:
        log.debug("table_root_resolved", extra={"table": table, "target_dir": str(root)})
    except Exception:
        pass
    return root

def _run_partition(table: str, run_id: str) -> Path:
    # Partition style: table/run_id=YYYYMMDDTHHMMSSZ
    p = _table_root(table) / f"run_id={run_id}"
    try:
        log.debug("run_partition_resolved", extra={"table": table, "run_id": run_id, "target_dir": str(p)})
    except Exception:
        pass
    return p

def _dt_partition(parent: Path, dt: str) -> Path:
    # Used under prices/run_id=.../dt=YYYY-MM-DD
    p = parent / f"dt={dt}"
    try:
        log.debug("dt_partition_resolved", extra={"dt": dt, "target_dir": str(p)})
    except Exception:
        pass
    return p


_RUN_ID_RE = re.compile(r"^\d{8}(T?\d{6}Z?)$")  # accepts YYYYMMDDHHMMSS / YYYYMMDDTHHMMSS / ...Z
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _is_valid_run_id(run_id: str) -> bool:
    """
    Valid run_id formats:
      - 'YYYYMMDDHHMMSS'
      - 'YYYYMMDDTHHMMSS'
      - 'YYYYMMDDHHMMSSZ'
      - 'YYYYMMDDTHHMMSSZ'   (CLI-friendly ISO-ish)
    """
    return bool(_RUN_ID_RE.match(run_id))

def _is_valid_date(date_str: str) -> bool:
    return bool(_DATE_RE.match(date_str))

# -----------------------------
# Simple file lock (directory-based)
# -----------------------------

class FileLock:
    """
    Cross-platform cooperative lock using an atomic mkdir on a lock directory.
    """
    def __init__(self, lock_path: Path, poll_interval: float = 0.25, timeout: float = 30.0):
        self.lock_path = Path(lock_path)
        self.poll = poll_interval
        self.timeout = timeout

    def acquire(self) -> None:
        start = time.time()
        while True:
            try:
                self.lock_path.mkdir(parents=True, exist_ok=False)
                # Write owner metadata
                (self.lock_path / "owner.txt").write_text(
                    f"pid={os.getpid()} at={datetime.utcnow().isoformat()}Z\n"
                )
                try:
                    log.debug("file_lock_acquired", extra={"lock_dir": str(self.lock_path)})
                except Exception:
                    pass
                return
            except FileExistsError:
                if time.time() - start > self.timeout:
                    try:
                        log.error("file_lock_timeout", extra={"lock_dir": str(self.lock_path), "timeout_s": self.timeout})
                    except Exception:
                        pass
                    raise TimeoutError(f"Lock timeout: {self.lock_path}")
                time.sleep(self.poll)

    def release(self) -> None:
        try:
            shutil.rmtree(self.lock_path)
            try:
                log.debug("file_lock_released", extra={"lock_dir": str(self.lock_path)})
            except Exception:
                pass
        except FileNotFoundError:
            pass
        except Exception as e:
            # Non-fatal; log and continue
            try:
                log.warning("file_lock_release_failed", extra={"lock_dir": str(self.lock_path), "error": repr(e)})
            except Exception:
                pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()

# -----------------------------
# Atomic writer
# -----------------------------

def _ensure_pa_table(df_or_tab: Union[pa.Table, "pl.DataFrame", "pd.DataFrame"]) -> pa.Table:
    if isinstance(df_or_tab, pa.Table):
        return df_or_tab
    # Polars first if available
    if pl is not None and "polars" in str(type(df_or_tab)).lower():  # cheap duck type
        return df_or_tab.to_arrow()
    # Fallback to pandas if present
    try:
        import pandas as pd  # type: ignore
        if isinstance(df_or_tab, pd.DataFrame):
            return pa.Table.from_pandas(df_or_tab, preserve_index=False)
    except Exception:
        pass
    raise TypeError("Unsupported frame type; pass pyarrow.Table, polars.DataFrame, or pandas.DataFrame")

@dataclass
class WriterConfig:
    compression: str = "zstd"
    use_dictionary: bool = True
    write_statistics: bool = True
    file_target_mb: int = 128  # rotate/shard around this size if needed

class AtomicWriter:
    """
    Usage:
      w = begin_atomic_write("scores", run_id)
      w.write_df(df1)
      w.write_df(df2)  # optional multiple parts
      w.commit()
    """
    def __init__(
        self,
        table: str,
        run_id: str,
        cfg: WriterConfig,
        custom_final_dir: Optional[Path] = None,  # <--- non-breaking extension
    ):
        self.table = table
        self.run_id = run_id
        self.cfg = cfg
        self.root = _table_root(table)
        self.final_dir = custom_final_dir or _run_partition(table, run_id)
        storage_cfg = _storage_settings()
        tmp_base = None
        if storage_cfg and getattr(storage_cfg, "write_temp_dir", None):
            tmp_base = Path(storage_cfg.write_temp_dir).expanduser().resolve()
        if tmp_base:
            tmp_base.mkdir(parents=True, exist_ok=True)
            self.tmp_dir = tmp_base / uuid.uuid4().hex
        else:
            self.tmp_dir = self.root / "tmp" / uuid.uuid4().hex
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.parts_written = 0
        self.rows_written = 0
        self._closed = False
        # Minimal, high-signal log
        try:
            log.info(
                "writer_init",
                extra={
                    "table": table,
                    "run_id": run_id,
                    "final_dir": str(self.final_dir),
                    "parquet_root": str(self.root),
                },
            )
        except Exception:
            pass

    def write_df(self, df_or_tab: Union[pa.Table, "pl.DataFrame", "pd.DataFrame"]) -> None:
        assert not self._closed, "Writer closed"
        tab = _ensure_pa_table(df_or_tab)
        # Embed run_id and schema_version in file metadata
        # (schema version stored/controlled separately in meta/, but also mirrored here)
        md = tab.schema.metadata or {}
        md = dict(md)
        md.setdefault(b"run_id", self.run_id.encode())
        # Optional: read current schema version from meta
        sv = read_schema_version(self.table)
        if sv is not None:
            md[b"schema_version"] = str(sv).encode()
        tab = tab.replace_schema_metadata(md)

        # Write a single file per write_df call (simple & predictable)
        part_path = self.tmp_dir / f"part-{self.parts_written:05d}.parquet"
        pq.write_table(
            tab,
            part_path,
            compression=self.cfg.compression,
            use_dictionary=self.cfg.use_dictionary,
            write_statistics=self.cfg.write_statistics,
        )
        self.parts_written += 1
        self.rows_written += tab.num_rows
        try:
            log.debug("writer_part_written", extra={
                "table": self.table, "run_id": self.run_id, "part": int(self.parts_written - 1),
                "rows": int(tab.num_rows), "tmp_dir": str(self.tmp_dir)
            })
        except Exception:
            pass

    def _write_markers(self) -> None:
        (self.tmp_dir / "rowcount.txt").write_text(str(self.rows_written))
        (self.tmp_dir / "_SUCCESS").write_text("")

    def abort(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            shutil.rmtree(self.tmp_dir)
            try:
                log.info("writer_abort_cleanup_done", extra={
                    "table": self.table, "run_id": self.run_id, "tmp_dir": str(self.tmp_dir)
                })
            except Exception:
                pass
        except FileNotFoundError:
            pass
        except Exception as e:
            try:
                log.warning("writer_abort_cleanup_failed", extra={
                    "table": self.table, "run_id": self.run_id, "tmp_dir": str(self.tmp_dir), "error": repr(e)
                })
            except Exception:
                pass

    def commit(self) -> None:
        """
        Atomically promote tmp_dir â†’ final partition:
          table/run_id=.../  with parts, _SUCCESS, rowcount.txt
        Uses a directory lock to ensure single-writer to the same run_id.
        """
        if self._closed:
            return
        self._closed = True

        # Ensure target parent exists
        self.final_dir.parent.mkdir(parents=True, exist_ok=True)

        # Safety: must not already exist
        if self.final_dir.exists():
            # If someone already wrote it, treat as success and discard tmp
            try:
                log.info("writer_commit_noop_exists", extra={"target_dir": str(self.final_dir)})
            except Exception:
                pass
            self.abort()
            return

        # Write markers in tmp
        self._write_markers()

        # Lock path is alongside the final dir
        lock_path = self.final_dir.parent / f".lock-{self.final_dir.name}"
        with FileLock(lock_path):
            if self.final_dir.exists():
                # Another writer beat us; discard tmp
                try:
                    log.info("writer_commit_noop_raced", extra={"target_dir": str(self.final_dir)})
                except Exception:
                    pass
                self.abort()
                return
            # Move tmp to final (atomic on same filesystem)
            try:
                os.replace(self.tmp_dir, self.final_dir)
            except Exception as e1:
                # Fallback for Windows oddities or FS peculiarities
                try:
                    shutil.move(str(self.tmp_dir), str(self.final_dir))
                except Exception as e2:
                    try:
                        log.error("writer_commit_move_failed", extra={
                            "target_dir": str(self.final_dir),
                            "tmp_dir": str(self.tmp_dir),
                            "error_primary": repr(e1),
                            "error_fallback": repr(e2),
                        })
                    except Exception:
                        pass
                    # Best-effort cleanup
                    self.abort()
                    raise
            try:
                log.info(
                    "writer_commit_done",
                    extra={
                        "target_dir": str(self.final_dir),
                        "rows": int(self.rows_written),
                        "parts": int(self.parts_written),
                    },
                )
            except Exception:
                pass

def _writer_config_from_settings() -> WriterConfig:
    storage_cfg = _storage_settings()
    if storage_cfg:
        return WriterConfig(
            compression=getattr(storage_cfg, "compression", "zstd"),
            use_dictionary=getattr(storage_cfg, "use_dictionary", True),
            write_statistics=getattr(storage_cfg, "write_statistics", True),
        )
    return WriterConfig()


def begin_atomic_write(table: str, run_id: str, cfg: Optional[WriterConfig] = None) -> AtomicWriter:
    assert table in TABLES, f"Unknown table {table}"
    assert _is_valid_run_id(run_id), f"Bad run_id format: {run_id}"
    # Minimal trace for legacy single-partition writes
    try:
        log.info("begin_atomic_write", extra={"table": table, "run_id": run_id, "parquet_root": str(get_parquet_root())})
    except Exception:
        pass
    return AtomicWriter(table, run_id, cfg or _writer_config_from_settings())

# -----------------------------
# Daily & Intraday helpers for "scores"
# -----------------------------

def scores_daily_dir(as_of: str) -> Path:
    assert _is_valid_date(as_of), f"Bad as_of date: {as_of}"
    p = _table_root("scores") / "daily" / f"as_of={as_of}"
    p.mkdir(parents=True, exist_ok=True)
    try:
        log.debug("scores_daily_dir_resolved", extra={"as_of": as_of, "target_dir": str(p)})
    except Exception:
        pass
    return p

def scores_intraday_run_dir(date_str: str, run_id: str) -> Path:
    assert _is_valid_date(date_str), f"Bad date: {date_str}"
    assert _is_valid_run_id(run_id), f"Bad run_id format: {run_id}"
    p = _table_root("scores") / "intraday" / f"date={date_str}" / f"run_id={run_id}"
    p.parent.mkdir(parents=True, exist_ok=True)  # ensure date dir exists
    try:
        log.debug("scores_intraday_run_dir_resolved", extra={
            "date": date_str, "run_id": run_id, "target_dir": str(p)
        })
    except Exception:
        pass
    return p

def _has_committed_run_under(path: Path) -> bool:
    """
    True if 'path' contains any child directory with a _SUCCESS marker
    (used to enforce one EOD snapshot per day).
    """
    if not path.exists():
        return False
    for child in path.glob("run_id=*"):
        if child.is_dir() and (child / "_SUCCESS").exists():
            return True
    return False

def _has_any_run_under(path: Path) -> bool:
    """
    True if 'path' contains any child directory named run_id=* (regardless of _SUCCESS).
    This satisfies the stricter "do not override if folder for that day already exists"
    requirement for daily scores.
    """
    if not path.exists():
        return False
    for child in path.glob("run_id=*"):
        if child.is_dir():
            return True
    return False

class _NullWriter:
    """No-op writer used when a daily partition already exists (no-overwrite policy)."""
    def __init__(self, final_dir: Path):
        self.final_dir = final_dir
        self.parts_written = 0
        self.rows_written = 0
        self._closed = True  # treat as already closed

    def write_df(self, *_args, **_kwargs) -> None:
        return

    def commit(self) -> None:
        # Trace no-op commits explicitly so it's visible in logs
        try:
            log.info("writer_commit_noop_daily_immutable", extra={"target_dir": str(self.final_dir)})
        except Exception:
            pass
        return

    def abort(self) -> None:
        return

def begin_atomic_write_scores_daily(as_of: str, run_id: str, cfg: Optional[WriterConfig] = None) -> AtomicWriter | _NullWriter:
    """
    Create a writer under scores/daily/as_of=YYYY-MM-DD/run_id=<run_id>.

    Policy (per user request):
      - If that as_of ALREADY HAS ANY run folder, skip (immutable per-day).
        This is stricter than only checking for _SUCCESS markers.
    """
    as_of_root = scores_daily_dir(as_of)

    # Strict immutability: skip if any run_id=* exists under as_of
    if _has_any_run_under(as_of_root):
        try:
            log.info("scores_daily_begin_noop_exists", extra={"as_of": as_of, "as_of_dir": str(as_of_root)})
        except Exception:
            pass
        return _NullWriter(final_dir=as_of_root)

    final_dir = as_of_root / f"run_id={run_id}"
    assert _is_valid_run_id(run_id), f"Bad run_id format: {run_id}"
    try:
        log.info("scores_daily_begin", extra={"as_of": as_of, "run_id": run_id, "target_dir": str(final_dir)})
    except Exception:
        pass
    return AtomicWriter("scores", run_id, cfg or _writer_config_from_settings(), custom_final_dir=final_dir)

def begin_atomic_write_scores_intraday(date_str: str, run_id: str, cfg: Optional[WriterConfig] = None) -> AtomicWriter:
    """
    Create a writer under scores/intraday/date=YYYY-MM-DD/run_id=<run_id>.
    Multiple runs per day are allowed.
    """
    final_dir = scores_intraday_run_dir(date_str, run_id)
    try:
        log.info("scores_intraday_begin", extra={"date": date_str, "run_id": run_id, "target_dir": str(final_dir)})
    except Exception:
        pass
    return AtomicWriter("scores", run_id, cfg or _writer_config_from_settings(), custom_final_dir=final_dir)

def list_intraday_runs(date_str: str) -> List[str]:
    """
    Return all committed intraday run_ids for the given trading date, sorted ascending.
    """
    root = _table_root("scores") / "intraday" / f"date={date_str}"
    if not root.exists():
        return []
    runs: List[str] = []
    for child in root.glob("run_id=*"):
        if not child.is_dir():
            continue
        rid = child.name.split("run_id=", 1)[-1]
        if _is_valid_run_id(rid) and (child / "_SUCCESS").exists():
            runs.append(rid)
    runs.sort()
    return runs

def latest_intraday(date_str: str) -> Optional[str]:
    """
    Return the latest run_id for an intraday date if any committed runs exist.
    """
    root = _table_root("scores") / "intraday" / f"date={date_str}"
    if not root.exists():
        return None
    cands: list[str] = []
    for child in root.glob("run_id=*"):
        if not child.is_dir():
            continue
        rid = child.name.split("run_id=", 1)[-1]
        if _is_valid_run_id(rid) and (child / "_SUCCESS").exists():
            cands.append(rid)
    return sorted(cands)[-1] if cands else None

def latest_daily_at_or_before(date_str: str) -> Optional[str]:
    """
    Return the latest as_of (YYYY-MM-DD) â‰¤ date_str with a committed run present.
    """
    root = _table_root("scores") / "daily"
    if not root.exists():
        return None
    cands: list[str] = []
    for child in root.glob("as_of=*"):
        if not child.is_dir():
            continue
        as_of = child.name.split("as_of=", 1)[-1]
        if not _is_valid_date(as_of):
            continue
        if as_of <= date_str and _has_committed_run_under(child):
            cands.append(as_of)
    return sorted(cands)[-1] if cands else None

def scan_scores_daily(as_of: str, columns: Optional[Iterable[str]] = None, filters: Optional[ds.Expression] = None) -> pa.Table:
    """
    Read the daily partition for a given as_of (recursively includes its run dir).
    Returns empty table if not present/committed.
    """
    root = scores_daily_dir(as_of)
    if not _has_committed_run_under(root):
        try:
            log.info("scan_scores_daily_empty_or_uncommitted", extra={"as_of": as_of, "as_of_dir": str(root)})
        except Exception:
            pass
        return pa.table({c: [] for c in (columns or [])}) if columns else pa.table({})
    # dataset() scans recursively; will include files under run_id=...
    dataset = ds.dataset(root, format="parquet", partitioning="hive", exclude_invalid_files=True)
    return dataset.to_table(columns=list(columns) if columns else None, filter=filters)

def scan_scores_intraday(date_str: str, run_id: str, columns: Optional[Iterable[str]] = None, filters: Optional[ds.Expression] = None) -> pa.Table:
    """
    Read a specific intraday run partition: date=YYYY-MM-DD/run_id=YYYYMMDDHHMMSS.
    Returns empty table if not present/committed.
    """
    part_root = scores_intraday_run_dir(date_str, run_id)
    if not (part_root / "_SUCCESS").exists():
        try:
            log.info("scan_scores_intraday_empty_or_uncommitted", extra={"date": date_str, "run_id": run_id, "target_dir": str(part_root)})
        except Exception:
            pass
        return pa.table({c: [] for c in (columns or [])}) if columns else pa.table({})
    dataset = ds.dataset(part_root, format="parquet", partitioning="hive", exclude_invalid_files=True)
    return dataset.to_table(columns=list(columns) if columns else None, filter=filters)

# -----------------------------
# Schema version helpers (meta/)
# -----------------------------

def _meta_path(name: str) -> Path:
    m = _table_root("meta")  # ensures meta dir exists
    return m / name

def read_schema_version(table: str) -> Optional[int]:
    p = _meta_path(f"{table}_schema_version.json")
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text())
        return int(obj.get("version"))
    except Exception:
        return None

def write_schema_version(table: str, version: int) -> None:
    p = _meta_path(f"{table}_schema_version.json")
    p.write_text(json.dumps({"version": int(version)}, indent=2))

# -----------------------------
# Snapshot discovery & scanning
# -----------------------------

def latest_snapshot(table: str) -> Optional[str]:
    root = _table_root(table)
    candidates = []
    for child in root.glob("run_id=*"):
        if not child.is_dir():
            continue
        run_id = child.name.split("run_id=", 1)[-1]
        if _is_valid_run_id(run_id):
            # Only count if fully committed
            if (child / "_SUCCESS").exists():
                candidates.append(run_id)
    if not candidates:
        return None
    return sorted(candidates)[-1]

def _scan_dataset(path: Path, columns: Optional[Iterable[str]] = None, filters: Optional[ds.Expression] = None) -> pa.Table:
    if not path.exists():
        # Return empty table (no files)
        try:
            log.info("scan_dataset_missing_path", extra={"target_dir": str(path)})
        except Exception:
            pass
        return pa.table({c: [] for c in (columns or [])}) if columns else pa.table({})
    dataset = ds.dataset(path, format="parquet", partitioning="hive", exclude_invalid_files=True)
    return dataset.to_table(columns=list(columns) if columns else None, filter=filters)

def scan(
    table: str,
    run_id: Optional[str] = None,
    dt_range: Optional[Tuple[str, str]] = None,  # ('YYYY-MM-DD','YYYY-MM-DD') for prices
    columns: Optional[Iterable[str]] = None,
    filters: Optional[dict] = None,  # reserved for Phase 7 DSL pushdown
    as_polars: bool = False,
) -> Union[pa.Table, "pl.DataFrame"]:
    """
    Read a partition (or range) with predicate pushdown via pyarrow.dataset.
    For prices: dt_range prunes partitions (dt=YYYY-MM-DD).
    """
    assert table in TABLES, f"Unknown table {table}"

    # Resolve run_id
    rid = run_id or latest_snapshot(table)
    if rid is None:
        try:
            log.info("scan_empty_no_snapshot", extra={"table": table})
        except Exception:
            pass
        return pl.DataFrame() if (as_polars and pl is not None) else pa.table({})

    part_root = _run_partition(table, rid)

    # Verify committed
    if not (part_root / "_SUCCESS").exists():
        # Not committed: treat as empty
        try:
            log.info("scan_uncommitted_partition", extra={"table": table, "run_id": rid, "target_dir": str(part_root)})
        except Exception:
            pass
        return pl.DataFrame() if (as_polars and pl is not None) else pa.table({})

    # Build filter
    expr = None
    if table == "prices" and dt_range:
        lo, hi = dt_range
        # Partition columns are strings; pyarrow treats hive partition keys as strings
        expr = (ds.field("dt") >= lo) & (ds.field("dt") <= hi)

    tab = _scan_dataset(part_root, columns=columns, filters=expr)

    if as_polars and pl is not None:
        return pl.from_arrow(tab)
    return tab

# -----------------------------
# Phase-9 compatibility helper
# -----------------------------
def write_atomic_snapshot(
    *,
    root_dir: Optional[str] = None,
    table: str,
    run_id: str,
    rows: Iterable[dict] | pa.Table | "pl.DataFrame" = (),
    schema_version: str | int = "1",
    as_of: str | None = None,  # accepted for parity; not persisted separately here
) -> Path:
    """
    Thin wrapper so services can do a one-shot snapshot write without knowing
    about AtomicWriter lifecycle. Creates â‰¥1 part-*.parquet, rowcount.txt, _SUCCESS.

    - If root_dir is provided, it temporarily overrides PARQUET_ROOT for this call.
    - rows may be: list[dict], pyarrow.Table, or polars.DataFrame.
    - schema_version is recorded in meta/<table>_schema_version.json and mirrored into file metadata.

    Returns the final snapshot directory path: {PARQUET_ROOT}/{table}/run_id={run_id}
    """
    prev_env = os.environ.get("PARQUET_ROOT")
    try:
        if root_dir:
            os.environ["PARQUET_ROOT"] = root_dir

        # Persist/refresh schema version used by writer metadata
        try:
            write_schema_version(table, int(schema_version))
        except Exception:
            # Non-fatal: keep going with whatever meta exists
            try:
                log.warning("write_schema_version_failed_nonfatal", extra={"table": table, "schema_version": schema_version})
            except Exception:
                pass

        w = begin_atomic_write(table, run_id)

        # Normalize rows -> pa.Table and write at least one part
        if isinstance(rows, pa.Table) or (pl is not None and "polars" in str(type(rows)).lower()):
            w.write_df(rows)  # _ensure_pa_table will convert polars
        else:
            # Assume iterable of dicts (possibly empty)
            try:
                # from_pylist handles empty list â†’ 0-row table (valid parquet)
                tab = pa.Table.from_pylist(list(rows))
            except Exception:
                # Fallback: guaranteed-empty schema
                tab = pa.table({"_rows": pa.array([], type=pa.int32())})
            w.write_df(tab)

        w.commit()
        return _run_partition(table, run_id)
    finally:
        # Restore env override if we changed it
        if root_dir is not None:
            if prev_env is None:
                os.environ.pop("PARQUET_ROOT", None)
            else:
                os.environ["PARQUET_ROOT"] = prev_env

