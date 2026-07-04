import pyarrow.parquet as pq
import pandas as pd

# Read early file
early_path = r"d:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\parquet\scores\daily\as_of=2024-08-23\run_id=20250922140559\part-00000.parquet"

early_pf = pq.ParquetFile(early_path)
table = early_pf.read()
early_df = table.to_pandas()

print("=" * 80)
print("EARLY FILE (2024-08-23) - COLUMN LIST")
print("=" * 80)
print(f"\nTotal columns: {len(early_df.columns)}")
print(f"Total rows: {len(early_df)}\n")

print("All columns:")
for i, col in enumerate(early_df.columns, 1):
    print(f"  {i:3}. {col}")

print("\n" + "=" * 80)
print("SCHEMA COMPARISON: 2024-08-23 vs 2025-12-31")
print("=" * 80)

early_set = set(early_df.columns)
recent_set = set(['symbol', 'name', 'sector', 'last', 'change_pct', 'rsi14', 'adx14', 'ema10', 'ema20', 'ema50', 'ema200', 'relvol20', 'relvol20_raw', 'proximity_52w_high_pct', 'atr14_pct', 'atr10_pct', 'vol_z20', 'high_252', 'obv', 'obv_ma30', 'obv_slope_10', 'obv_above_ma', 'pivot_high_20', 'pivot_20d', 'pivot_clear_pct', 'base_len_bars', 'gap_up_pct', 'close_pos_in_bar', 'median_traded_value_20d', 'delivery_ratio_20d', 'prev_day_high', 'prev_day_high_clear', 'n_consecutive_up', 'n_consecutive_down', 'recent_failed_breakout_10d', 'adx_slope_pos', 'ret_1w', 'ret_5d', 'ret_1m', 'ret_3m', 'ret_6m', 'ret_12_1m', 'breadth_pct_50dma', 'nifty_regime', 'mansfield_rs_52', 'asm_gsm_flags', 'upper_circuit_hits_60d', 'score', 'score_full', 'score_basic', 'score_basic_normalized', 'score_source', 'data_gaps', 'stale', 'rules_version', 'score_scale', 'badges', 'recommendation', 'buy', 'reason', 'as_of', 'is_eod', 'run_id', 'score_band', 'reason_codes', 'score_reason_codes', 'score_breakdown', 'score_penalties', 'score_components_raw', 'rsi', 'adx', 'pct_from_52w_high', 'atr_pct', 'pct_today', 'minutes_since_open', 'in_lunch_window', 'candidate_pool_member', 'pre_gates_pass', 'next_action', 'next_action_code', 'next_action_reason_codes', 'liquidity', 'persistence_ok', 'buy_flag', 'buy_profile', 'buy_mode', 'buy_pass_count', 'buy_total_count', 'buy_checks', 'buy_failed_codes', 'buy_reasons_inline', 'buy_eval_ts', 'buy_enforced_checks', 'buy_check_details', 'reason_parts', 'buy_reason_parts', 'buy_selected', 'buy_selection_reason', 'buy_stop_price', 'buy_target_price', 'buy_r_multiple', 'buy_selection_run_id', 'buy_selection_trading_day', 'vol_spike', 'strength'])

added = recent_set - early_set
removed = early_set - recent_set

print(f"\nNew columns in 2025-12-31 ({len(added)}):")
for col in sorted(added):
    print(f"  + {col}")

print(f"\nRemoved columns from 2024-08-23 ({len(removed)}):")
for col in sorted(removed):
    print(f"  - {col}")

print(f"\nCommon columns: {len(early_set & recent_set)}")
