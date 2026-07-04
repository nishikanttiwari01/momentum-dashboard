import pyarrow.parquet as pq
import pandas as pd

# Find files with actual data in recent dates
import os
from pathlib import Path

print("Checking for non-empty parquet files in 2025...")
base_path = r"d:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily"

# Check recent files
recent_files = []
for date_dir in sorted(Path(base_path).glob("as_of=2025-*"))[::-1]:
    run_dir = list(date_dir.glob("run_id=*"))
    if run_dir:
        parquet_file = run_dir[0] / "part-00000.parquet"
        if parquet_file.exists():
            pf = pq.ParquetFile(str(parquet_file))
            num_rows = pf.metadata.num_rows
            if num_rows > 0:
                print(f"{date_dir.name}: {num_rows} rows")
                if len(recent_files) == 0:
                    recent_files.append((str(parquet_file), date_dir.name))

if recent_files:
    recent_path, recent_date = recent_files[0]
    print(f"\n\nUsing recent file: {recent_date}")
    recent_pf = pq.ParquetFile(recent_path)
    recent_df = pq.read_table(recent_path).to_pandas()
    
    print(f"\nShape: {recent_df.shape}")
    print(f"\nAll columns ({len(recent_df.columns)}):")
    for col in recent_df.columns:
        print(f"  - {col}")
    
    print(f"\n\nFirst 5 rows (selected columns):")
    cols_to_show = ['symbol', 'score', 'last', 'ret_1w', 'ret_1m', 'ret_3m', 'proximity_52w_high_pct', 
                   'relvol20', 'atr_pct', 'pivot_clear_pct', 'adx14', 'rsi14', 'obv_above_ma', 
                   'obv_slope_10', 'buy', 'pct_from_52w_high', 'vol_z20', 'ema10', 'ema20', 'ema50', 'ema200']
    available_cols = [c for c in cols_to_show if c in recent_df.columns]
    print(recent_df[available_cols].head())
else:
    print("No recent file with data found")
