import pyarrow.parquet as pq
import pandas as pd

# Read recent file directly
recent_path = r"d:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\as_of=2025-12-31\run_id=20260105090910\part-00000.parquet"

recent_pf = pq.ParquetFile(recent_path)
table = recent_pf.read()
recent_df = table.to_pandas()

print("=" * 80)
print("RECENT FILE (2025-12-31) - DETAILED COLUMN LIST")
print("=" * 80)
print(f"\nTotal columns: {len(recent_df.columns)}")
print(f"Total rows: {len(recent_df)}\n")

print("All columns:")
for i, col in enumerate(recent_df.columns, 1):
    print(f"  {i:3}. {col}")

print("\n" + "=" * 80)
print("SAMPLE DATA FOR REQUESTED FIELDS (First 5 rows)")
print("=" * 80)

requested_cols = ['symbol', 'score', 'last', 'ret_5d', 'ret_1m', 'ret_3m', 'proximity_52w_high_pct', 
                  'relvol20', 'atr_pct', 'pivot_clear_pct', 'adx14', 'rsi14', 'obv_above_ma', 
                  'obv_slope_10', 'buy_flag', 'nifty_regime', 'vol_z20', 'ema10', 'ema20', 'ema50', 
                  'ema200', 'mansfield_rs_52', 'sector']

available_cols = [c for c in requested_cols if c in recent_df.columns]
missing_cols = [c for c in requested_cols if c not in recent_df.columns]

print(f"\nAvailable columns: {len(available_cols)} / {len(requested_cols)}")
if missing_cols:
    print(f"Missing columns: {missing_cols}")

print(f"\nData sample (first 5 rows, selected columns):")
print(recent_df[available_cols].head(5).to_string())
