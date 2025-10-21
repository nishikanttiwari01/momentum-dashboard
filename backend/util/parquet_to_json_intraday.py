# python parquet_to_json_intraday.py --root "D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\as_of=2025-10-20" --out "D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\daily_ndjson" --format ndjson
# python parquet_to_json_intraday.py --root "D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\as_of=2025-10-20" --out "D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\daily_ndjson" --format csv
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Iterable, Optional, Tuple


def _detect_layout(root: Path) -> Optional[str]:
    """
    Determine whether the directory tree represents intraday partitions
    (date=.../run_id=...) or daily partitions (as_of=.../run_id=...). Returns
    one of {"intraday", "daily"} or None when it cannot be inferred.
    """
    name = root.name
    if name.startswith("date="):
        return "intraday"
    if name.startswith("as_of="):
        return "daily"
    if name.startswith("run_id="):
        parent = root.parent
        if parent.name.startswith("date="):
            return "intraday"
        if parent.name.startswith("as_of="):
            return "daily"
    has_date = any(child.is_dir() and child.name.startswith("date=") for child in root.iterdir())
    has_asof = any(child.is_dir() and child.name.startswith("as_of=") for child in root.iterdir())
    if has_date and not has_asof:
        return "intraday"
    if has_asof and not has_date:
        return "daily"
    if has_date and has_asof:
        return "intraday"
    return None


def find_runs(root: Path, layout: str) -> list[Tuple[Path, str, str, str]]:
    """
    Enumerate parquet run folders.

    Returns a list of tuples (run_dir, partition_key, partition_value, run_id)
    where partition_key is either "date" (intraday) or "as_of" (daily).
    """
    if root.name.startswith("run_id="):
        run_id = root.name.split("=", 1)[-1]
        partition_dir = root.parent
        detected = _detect_layout(partition_dir) or "intraday"
        partition_key = "date" if detected == "intraday" else "as_of"
        partition_value = partition_dir.name.split("=", 1)[-1] if "=" in partition_dir.name else partition_dir.name
        return [(root, partition_key, partition_value, run_id)]

    if root.name.startswith("date=") or root.name.startswith("as_of="):
        partition_key = "date" if root.name.startswith("date=") else "as_of"
        partition_value = root.name.split("=", 1)[-1]
        runs: list[Tuple[Path, str, str, str]] = []
        for run_dir in sorted(root.glob("run_id=*")):
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name.split("=", 1)[-1]
            runs.append((run_dir, partition_key, partition_value, run_id))
        return runs

    if layout == "auto":
        detected = _detect_layout(root)
        if not detected:
            return []
        layout = detected

    if layout == "intraday":
        partition_key = "date"
        pattern = "date=*"
    elif layout == "daily":
        partition_key = "as_of"
        pattern = "as_of=*"
    else:
        raise ValueError(f"Unsupported layout '{layout}'. Expected intraday, daily, or auto.")

    runs: list[Tuple[Path, str, str, str]] = []
    for part_dir in sorted(root.glob(pattern)):
        if not part_dir.is_dir():
            continue
        part_value = part_dir.name.split("=", 1)[-1]
        for run_dir in sorted(part_dir.glob("run_id=*")):
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name.split("=", 1)[-1]
            runs.append((run_dir, partition_key, part_value, run_id))
    return runs


def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def iter_pyarrow(parquet_paths: list[Path], columns: Optional[list[str]]):
    import pyarrow.dataset as ds

    dataset = ds.dataset([str(p) for p in parquet_paths], format="parquet")
    table = dataset.to_table(columns=columns)
    for record in table.to_pylist():
        yield record


def iter_fastparquet(parquet_paths: list[Path], columns: Optional[list[str]]):
    from fastparquet import ParquetFile

    for path in parquet_paths:
        pf = ParquetFile(str(path))
        iterator = pf.iter_row_groups(columns=columns) if columns else pf.iter_row_groups()
        for frame in iterator:
            for record in frame.to_dict(orient="records"):
                yield record


def write_ndjson(records: Iterable[dict], out_path: Path, compress: bool) -> int:
    lines = 0
    if compress:
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=5) as gz:
            for record in records:
                gz.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
                gz.write(b"\n")
                lines += 1
        atomic_write_bytes(out_path, buffer.getvalue())
    else:
        buffer = io.StringIO()
        for record in records:
            buffer.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
            buffer.write("\n")
            lines += 1
        atomic_write_text(out_path, buffer.getvalue())
    return lines


def write_csv(records: Iterable[dict], out_path: Path, compress: bool) -> Tuple[int, list[str]]:
    rows = list(records)
    if not rows:
        if compress:
            atomic_write_bytes(out_path, b"")
        else:
            atomic_write_text(out_path, "")
        return 0, []

    header: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in header:
                header.append(key)

    buffer = io.StringIO()
    buffer.write(",".join(header) + "\n")
    for row in rows:
        fields = []
        for key in header:
            val = row.get(key)
            if val is None:
                fields.append("")
            elif isinstance(val, (int, float)):
                fields.append(str(val))
            else:
                text = str(val)
                if any(ch in text for ch in [",", "\"", "\n", "\r"]):
                    text = "\"" + text.replace("\"", "\"\"") + "\""
                fields.append(text)
        buffer.write(",".join(fields) + "\n")

    data = buffer.getvalue().encode("utf-8")
    if compress:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=5) as gz:
            gz.write(data)
        atomic_write_bytes(out_path, buf.getvalue())
    else:
        atomic_write_text(out_path, buffer.getvalue())
    return len(rows), header


def convert_run(
    run_dir: Path,
    out_root: Path,
    partition_key: str,
    partition_value: str,
    run_id: str,
    columns: Optional[list[str]],
    compress: bool,
    overwrite: bool,
    pattern: str,
    output_format: str,
) -> Tuple[bool, str]:
    parquet_files = sorted(run_dir.rglob(pattern))
    dest = out_root / f"{partition_key}={partition_value}" / f"run_id={run_id}"
    dest.mkdir(parents=True, exist_ok=True)

    if output_format == "csv":
        out_filename = "all.csv.gz" if compress else "all.csv"
    else:
        out_filename = "all.ndjson.gz" if compress else "all.ndjson"
    out_path = dest / out_filename
    log_path = dest / "_convert.log"
    err_path = dest / "_error.txt"

    for path in (log_path, err_path):
        if path.exists():
            path.unlink()

    atomic_write_text(log_path, f"[SCAN] run_dir={run_dir}\nfound_files={len(parquet_files)}\npattern={pattern}\n")
    if not parquet_files:
        atomic_write_text(err_path, "No parquet files found under run_dir.")
        return False, "no_files"

    if out_path.exists() and not overwrite:
        atomic_write_text(log_path, f"[SKIP] out exists and --no-overwrite set: {out_path}\n")
        return True, "skipped"

    engine = None
    try:
        import pyarrow  # noqa: F401

        engine = "pyarrow"
    except Exception:
        try:
            import fastparquet  # noqa: F401

            engine = "fastparquet"
        except Exception:
            atomic_write_text(err_path, "Neither pyarrow nor fastparquet is installed.")
            return False, "no_engine"

    try:
        atomic_write_text(log_path, log_path.read_text() + f"[ENGINE] {engine}\n[OUT] {out_path}\n")
        if engine == "pyarrow":
            iterator = iter_pyarrow(parquet_files, columns)
        else:
            iterator = iter_fastparquet(parquet_files, columns)

        records = list(iterator)
        if output_format == "csv":
            lines, header = write_csv(records, out_path, compress)
        else:
            lines = write_ndjson(records, out_path, compress)
            header = []

        manifest = {
            partition_key: partition_value,
            "run_id": run_id,
            "engine": engine,
            "files": len(parquet_files),
            "columns": columns or "ALL",
            "output": str(out_path),
            "format": output_format,
            "compressed": bool(compress),
            "lines": lines,
        }
        if header:
            manifest["csv_columns"] = header
        atomic_write_text(dest / "manifest.json", json.dumps(manifest, indent=2))
        atomic_write_text(log_path, log_path.read_text() + f"[DONE] lines={lines}\n")
        if lines == 0:
            atomic_write_text(err_path, "0 lines written (empty parquet or columns filtered away).")
            return False, "zero_lines"
        return True, "ok"
    except Exception:
        tb = traceback.format_exc()
        atomic_write_text(err_path, f"Exception:\n{tb}")
        return False, "exception"


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert parquet scores (intraday or daily) to NDJSON or CSV.")
    parser.add_argument("--root", required=True, help="Root directory (scores/intraday or scores/daily)")
    parser.add_argument("--out", required=True, help="Output root for converted files")
    parser.add_argument("--columns", nargs="*", default=None, help="Optional subset of columns to include")
    parser.add_argument("--compress", action="store_true", help="Gzip the output (adds .gz extension)")
    parser.add_argument("--no-overwrite", action="store_true", help="Skip runs whose outputs already exist")
    parser.add_argument("--pattern", default="*.parquet", help="Glob pattern for parquet files (default: *.parquet)")
    parser.add_argument(
        "--layout",
        choices=["intraday", "daily", "auto"],
        default="auto",
        help="Parquet layout. Auto-detect inspects child folders (default: auto).",
    )
    parser.add_argument(
        "--format",
        choices=["ndjson", "csv"],
        default="ndjson",
        help="Output format (default: ndjson).",
    )
    args = parser.parse_args()

    root = Path(args.root)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    runs = find_runs(root, args.layout)
    if not runs:
        print(f"[ERR] No runs under {root}")
        sys.exit(2)

    ok, fail = 0, 0
    for run_dir, partition_key, partition_value, run_id in runs:
        success, reason = convert_run(
            run_dir=run_dir,
            out_root=out_root,
            partition_key=partition_key,
            partition_value=partition_value,
            run_id=run_id,
            columns=args.columns,
            compress=args.compress,
            overwrite=not args.no_overwrite,
            pattern=args.pattern,
            output_format=args.format,
        )
        tag = "OK" if success else "ERR"
        print(f"[{tag}] {partition_key}={partition_value} {run_id} - {reason}")
        ok += int(success)
        fail += int(not success)

    print(f"Done. ok={ok}, fail={fail}")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
