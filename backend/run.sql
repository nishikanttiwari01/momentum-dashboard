SELECT run_id, symbol, score, channels_sent, created_at
FROM alert_events
ORDER BY id DESC
LIMIT 10;
