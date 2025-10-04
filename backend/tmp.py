from pathlib import Path
path = Path('app/pipeline/news_provider.py')
lines = path.read_text().splitlines()
# run_intraday logs
for i, line in enumerate(lines):
    if line.strip().startswith('def run_intraday('):
        lines.insert(i + 1, '    log.info("news.provider.intraday_start", extra={"since_expr": since_expr, "top_gainers": top_gainers, "top_losers": top_losers, "symbol_limit": symbol_limit, "provider_cmd": provider_cmd})')
        break
for i, line in enumerate(lines):
    if line.strip().startswith('_ingest_batch_via_api('):
        # ensure we add log only for intraday function by verifying indentation (4 spaces). We'll insert after this call if inside intraday.
        if line.startswith('    _ingest_batch_via_api'):
            lines.insert(i + 1, '    log.info("news.provider.intraday_ingested", extra={"symbols": len(cohorts.union()), "items": len(batch.items)})')
            break
# run_backfill logs
for i, line in enumerate(lines):
    if line.strip().startswith('def run_backfill('):
        lines.insert(i + 1, '    log.info("news.provider.backfill_start", extra={"trading_day": trading_day.isoformat(), "symbol_limit": symbol_limit, "provider_cmd": provider_cmd})')
        break
for i, line in enumerate(lines):
    if line.strip().startswith('batch = _run_provider_cmd('):
        # The first occurrence is intraday; the second within backfill; we want ones with indentation 4 spaces? For backfill it's 4 spaces, for intraday it's 4 spaces as well but earlier. We'll differentiate by context. We'll insert for backfill by checking preceding lines for 'provider_cmd_clean' maybe not. We'll instead insert log after the call that belongs to backfill by checking nearest previous line containing 'symbols_all_file'. Simpler: track index around run_backfill by scanning from run_backfill definition.
        pass
