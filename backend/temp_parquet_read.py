import pyarrow.parquet as pq
import pandas as pd

# Read recent file (2025-10-15)
recent_path = r"d:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\as_of=2025-10-15\run_id=20251211045927\part-00000.parquet"
recent_pf = pq.ParquetFile(recent_path)

print("=" * 80)
print("RECENT FILE (2025-10-15):")
print("=" * 80)
print(f"\nSchema:")
print(recent_pf.schema)

print(f"\n\nColumns: {recent_pf.schema.names}")
print(f"Number of rows: {recent_pf.metadata.num_rows}")

# Read the actual data
recent_df = pq.read_table(recent_path).to_pandas()
print(f"\nDataFrame shape: {recent_df.shape}")
if len(recent_df) > 0:
    print(f"\nFirst 5 rows:")
    print(recent_df.head())
    print(f"\nAvailable columns: {list(recent_df.columns)}")
else:
    print("No data in recent file")

print("\n" + "=" * 80)
print("EARLY FILE (2024-08-23):")
print("=" * 80)

# Read early file
early_path = r"d:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\as_of=2024-08-23\run_id=20250922140559\part-00000.parquet"
early_pf = pq.ParquetFile(early_path)

print(f"\nSchema:")
print(early_pf.schema)

print(f"\n\nColumns: {early_pf.schema.names}")
print(f"Number of rows: {early_pf.metadata.num_rows}")

try:
    early_df = early_pf.read()
    print(f"\nDataFrame shape: {early_df.shape}")
    early_df_pd = early_df.to_pandas()
    print(f"\nFirst 5 rows:")
    print(early_df_pd.head())
except Exception as e:
    print(f"Error reading data: {e}")
    print("Just showing columns from schema")
