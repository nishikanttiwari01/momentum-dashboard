#(.venv) D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\util>python parquet_to_json_intraday.py --root "D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\intraday" --out "D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\intraday\intraday_ndjson"
from __future__ import annotations
import os, io, sys, json, gzip, argparse, traceback
from pathlib import Path
from typing import Iterable, Tuple, Optional

def find_runs(root: Path):
    for date_dir in sorted(root.glob("date=*")):
        if not date_dir.is_dir(): 
            continue
        date_str = date_dir.name.split("=", 1)[-1]
        for run_dir in sorted(date_dir.glob("run_id=*")):
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name.split("=", 1)[-1]
            yield run_dir, date_str, run_id

def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)

def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(data)
    os.replace(tmp, path)

def iter_pyarrow(parquet_paths: list[Path], cols: Optional[list[str]]):
    import pyarrow.dataset as ds
    dataset = ds.dataset([str(p) for p in parquet_paths], format="parquet")
    for rec in dataset.to_table(columns=cols).to_pylist():
        yield rec

def iter_fastparquet(parquet_paths: list[Path], cols: Optional[list[str]]):
    from fastparquet import ParquetFile
    import pandas as pd
    for p in parquet_paths:
        pf = ParquetFile(str(p))
        it = pf.iter_row_groups(columns=cols) if cols else pf.iter_row_groups()
        for df in it:
            for rec in df.to_dict(orient="records"):
                yield rec

def write_ndjson(records, out_path: Path, compress: bool) -> int:
    lines = 0
    if compress:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=5) as gz:
            for rec in records:
                gz.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
                gz.write(b"\n")
                lines += 1
        atomic_write_bytes(out_path, buf.getvalue())
    else:
        buf = io.StringIO()
        for rec in records:
            buf.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False))
            buf.write("\n")
            lines += 1
        atomic_write_text(out_path, buf.getvalue())
    return lines

def convert_run(
    run_dir: Path, out_root: Path, date_str: str, run_id: str,
    columns: Optional[list[str]], compress: bool, overwrite: bool, pattern: str
) -> Tuple[bool, str]:
    parquet_files = sorted(run_dir.rglob(pattern))
    dest = out_root / f"date={date_str}" / f"run_id={run_id}"
    dest.mkdir(parents=True, exist_ok=True)
    out_path = dest / ("all.ndjson.gz" if compress else "all.ndjson")
    log_path = dest / "_convert.log"
    err_path = dest / "_error.txt"

    # reset logs
    for p in (log_path, err_path):
        if p.exists(): p.unlink()

    # 1) scan
    atomic_write_text(log_path, f"[SCAN] run_dir={run_dir}\nfound_files={len(parquet_files)}\npattern={pattern}\n")
    if not parquet_files:
        atomic_write_text(err_path, "No parquet files found under run_dir.")
        return False, "no_files"

    if out_path.exists() and not overwrite:
        atomic_write_text(log_path, f"[SKIP] out exists and --no-overwrite set: {out_path}\n")
        return True, "skipped"

    # 2) choose engine
    engine = None
    try:
        import pyarrow  # noqa
        engine = "pyarrow"
    except Exception:
        try:
            import fastparquet  # noqa
            engine = "fastparquet"
        except Exception:
            atomic_write_text(err_path, "Neither pyarrow nor fastparquet is installed.")
            return False, "no_engine"

    # 3) stream rows -> ndjson
    try:
        atomic_write_text(log_path, (log_path.read_text() + f"[ENGINE] {engine}\n[OUT] {out_path}\n"))
        if engine == "pyarrow":
            records = iter_pyarrow(parquet_files, columns)
        else:
            records = iter_fastparquet(parquet_files, columns)

        lines = write_ndjson(records, out_path, compress)
        manifest = {
            "date": date_str, "run_id": run_id, "engine": engine,
            "files": len(parquet_files), "columns": columns or "ALL",
            "output": str(out_path), "lines": lines,
        }
        atomic_write_text(dest / "manifest.json", json.dumps(manifest, indent=2))
        atomic_write_text(log_path, (log_path.read_text() + f"[DONE] lines={lines}\n"))
        if lines == 0:
            atomic_write_text(err_path, "0 lines written (empty parquet or columns filtered away).")
            return False, "zero_lines"
        return True, "ok"
    except Exception as e:
        tb = traceback.format_exc()
        atomic_write_text(err_path, f"Exception:\n{tb}")
        return False, "exception"

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Convert intraday parquet tree to NDJSON.")
    ap.add_argument("--root", required=True, help="Root: intraday/")
    ap.add_argument("--out", required=True, help="Output root for NDJSON")
    ap.add_argument("--columns", nargs="*", default=None, help="Optional subset of columns")
    ap.add_argument("--compress", action="store_true", help="Write .ndjson.gz")
    ap.add_argument("--no-overwrite", action="store_true", help="Skip outputs if already exist")
    ap.add_argument("--pattern", default="*.parquet", help="Glob pattern to pick parquet files (default: *.parquet)")
    args = ap.parse_args()

    root, out = Path(args.root), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    runs = list(find_runs(root))
    if not runs:
        print(f"[ERR] No runs under {root}")
        sys.exit(2)

    ok, fail = 0, 0
    for run_dir, date_str, run_id in runs:
        success, reason = convert_run(
            run_dir, out, date_str, run_id,
            columns=args.columns, compress=args.compress,
            overwrite=not args.no_overwrite, pattern=args.pattern
        )
        tag = "OK" if success else "ERR"
        print(f"[{tag}] {date_str} {run_id} — {reason}")
        ok += int(success); fail += int(not success)
    print(f"Done. ok={ok}, fail={fail}")
    sys.exit(0 if fail==0 else 1)

if __name__ == "__main__":
    main()
