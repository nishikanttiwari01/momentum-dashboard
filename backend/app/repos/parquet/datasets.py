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
from typing import Iterable, Optional, Tuple, Union

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import re

# Optional: if you also use Polars in other places
try:
    import polars as pl  # type: ignore
except Exception:  # pragma: no cover
    pl = None  # Polars is optional for now

# -----------------------------
# Configuration helpers
# -----------------------------

def get_parquet_root() -> Path:
    # Allow override via env; default to ./parquet
    return Path(os.getenv("PARQUET_ROOT", "./parquet")).resolve()

TABLES = {"universe", "prices", "indicators", "scores", "meta"}

def _table_root(table: str) -> Path:
    assert table in TABLES or table == "meta", f"Unknown table: {table}"
    root = get_parquet_root() / table
    root.mkdir(parents=True, exist_ok=True)
    return root

def _run_partition(table: str, run_id: str) -> Path:
    # Partition style: table/run_id=YYYYMMDDTHHMMSSZ
    return _table_root(table) / f"run_id={run_id}"

def _dt_partition(parent: Path, dt: str) -> Path:
    # Used under prices/run_id=.../dt=YYYY-MM-DD
    return parent / f"dt={dt}"


_RUN_ID_RE = re.compile(r"^\d{8}(T?\d{6}Z?)$")  # accepts YYYYMMDDHHMMSS or YYYYMMDDTHHMMSSZ

def _is_valid_run_id(run_id: str) -> bool:
    """
    Valid run_id formats:
      - 'YYYYMMDDHHMMSS'            (e.g., 20250912 034903)
      - 'YYYYMMDDTHHMMSSZ'          (e.g., 20250912T034903Z)  <-- what the CLI emits
    """
    return bool(_RUN_ID_RE.match(run_id))

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
                return
            except FileExistsError:
                if time.time() - start > self.timeout:
                    raise TimeoutError(f"Lock timeout: {self.lock_path}")
                time.sleep(self.poll)

    def release(self) -> None:
        try:
            shutil.rmtree(self.lock_path)
        except FileNotFoundError:
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
    def __init__(self, table: str, run_id: str, cfg: WriterConfig):
        self.table = table
        self.run_id = run_id
        self.cfg = cfg
        self.root = _table_root(table)
        self.final_dir = _run_partition(table, run_id)
        self.tmp_dir = self.root / "tmp" / uuid.uuid4().hex
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.parts_written = 0
        self.rows_written = 0
        self._closed = False

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

    def _write_markers(self) -> None:
        (self.tmp_dir / "rowcount.txt").write_text(str(self.rows_written))
        (self.tmp_dir / "_SUCCESS").write_text("")

    def abort(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            shutil.rmtree(self.tmp_dir)
        except FileNotFoundError:
            pass

    def commit(self) -> None:
        """
        Atomically promote tmp_dir → final partition:
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
            self.abort()
            return

        # Write markers in tmp
        self._write_markers()

        # Lock path is alongside the final dir
        lock_path = self.final_dir.parent / f".lock-{self.final_dir.name}"
        with FileLock(lock_path):
            if self.final_dir.exists():
                # Another writer beat us; discard tmp
                self.abort()
                return
            # Move tmp to final (atomic on same filesystem)
            os.replace(self.tmp_dir, self.final_dir)

def begin_atomic_write(table: str, run_id: str, cfg: Optional[WriterConfig] = None) -> AtomicWriter:
    assert table in TABLES, f"Unknown table {table}"
    assert _is_valid_run_id(run_id), f"Bad run_id format: {run_id}"
    return AtomicWriter(table, run_id, cfg or WriterConfig())

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
        return pl.DataFrame() if (as_polars and pl is not None) else pa.table({})

    part_root = _run_partition(table, rid)

    # Verify committed
    if not (part_root / "_SUCCESS").exists():
        # Not committed: treat as empty
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
    about AtomicWriter lifecycle. Creates ≥1 part-*.parquet, rowcount.txt, _SUCCESS.

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
            pass

        w = begin_atomic_write(table, run_id)

        # Normalize rows -> pa.Table and write at least one part
        if isinstance(rows, pa.Table) or (pl is not None and "polars" in str(type(rows)).lower()):
            w.write_df(rows)  # _ensure_pa_table will convert polars
        else:
            # Assume iterable of dicts (possibly empty)
            try:
                # from_pylist handles empty list → 0-row table (valid parquet)
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
