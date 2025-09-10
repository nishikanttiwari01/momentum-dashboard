from __future__ import annotations
import argparse
from datetime import datetime, timedelta

from app.core.db import init_sqlite, get_sessionmaker
from app.repos.unit_of_work import SqliteUnitOfWork
from app.repos.interfaces.base import AlertRuleVO


def seed_sqlite():
    init_sqlite("./data/local.db")
    uow = SqliteUnitOfWork(get_sessionmaker())

    with uow:
        # watchlist
        for sym in ["RELIANCE", "TCS", "INFY"]:
            uow.watchlist.upsert_symbol(sym, note="seed")

        # alerts
        uow.alerts.create_alert(
            AlertRuleVO(
                id=None,
                symbol="RELIANCE",
                rule_type="price_crosses",
                rule_value="3000",
                channels=["desktop", "email"],
                enabled=True,
                created_at=None,
                updated_at=None,
            )
        )

        # positions
        uow.positions.lock_entry("RELIANCE", 2999.0, 10)
        uow.positions.update_stop("RELIANCE", 2950.0)

        # pins
        uow.snapshot_pins.pin("RELIANCE", "20250909T120000Z")

        # history
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        # Minimal direct insert via repo (list_history is read-only; we’ll seed via session here)
        session = uow._session  # internal: available inside context
        from app.repos.models import History
        session.add(
            History(
                symbol="RELIANCE",
                as_of=today,
                outcome="profit",
                pnl_pct=3.5,
                run_id="20250909T120000Z",
                meta_json='{"note":"seed"}',
            )
        )

        # jobs
        from app.repos.sql.jobs_repo import SqlJobsRepo
        jr = SqlJobsRepo(session)
        jr.record_run("20250909T120000Z", started_at=today)
        jr.complete_run("20250909T120000Z", ended_at=today + timedelta(minutes=3), status="SUCCEEDED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-only", action="store_true", help="Seed only SQLite (default)")
    args = parser.parse_args()
    seed_sqlite()
    print("Seed complete.")


if __name__ == "__main__":
    main()
