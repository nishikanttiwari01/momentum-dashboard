import pyarrow.parquet as pq
import pandas as pd

# Read recent file directly
recent_path = r"d:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\as_of=2025-12-31\run_id=20260105090910\part-00000.parquet"

recent_pf = pq.ParquetFile(recent_path)
print("=" * 80)
print("RECENT FILE (2025-12-31):")
print("=" * 80)

print(f"\nAll Columns ({len(recent_pf.schema.names)}):")
for i, col in enumerate(recent_pf.schema.names, 1):
    print(f"  {i}. {col}")

print(f"\nNumber of rows: {recent_pf.metadata.num_rows}")

# Read the table directly
table = recent_pf.read()
recent_df = table.to_pandas()

print(f"\nDataFrame shape: {recent_df.shape}")
print(f"\n\nSample data - First 5 rows:")
print(recent_df.head(5))
