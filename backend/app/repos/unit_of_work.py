from __future__ import annotations
from contextlib import AbstractContextManager
from typing import Protocol, Optional
from sqlalchemy.orm import Session, sessionmaker

from .interfaces.base import (
    IAlertsRepo,
    IWatchlistRepo,
    IHistoryRepo,
    IJobsRepo,
    ISettingsRepo,
    IPositionsRepo,
    ISnapshotPinsRepo,
)

from .sql.alerts_repo import SqlAlertsRepo
from .sql.watchlist_repo import SqlWatchlistRepo
from .sql.history_repo import SqlHistoryRepo
from .sql.jobs_repo import SqlJobsRepo
from .sql.settings_repo import SqlSettingsRepo
from .sql.positions_repo import SqlPositionsRepo
from .sql.snapshot_pins_repo import SqlSnapshotPinsRepo



class IUnitOfWork(Protocol, AbstractContextManager["IUnitOfWork"]):
    alerts: IAlertsRepo
    watchlist: IWatchlistRepo
    history: IHistoryRepo
    jobs: IJobsRepo
    settings: ISettingsRepo
    positions: IPositionsRepo
    snapshot_pins: ISnapshotPinsRepo

    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class SqliteUnitOfWork:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory
        self._session: Optional[Session] = None

    def __enter__(self):
        self._session = self._session_factory()
        self.alerts = SqlAlertsRepo(self._session)
        self.watchlist = SqlWatchlistRepo(self._session)
        self.history = SqlHistoryRepo(self._session)
        self.jobs = SqlJobsRepo(self._session)
        self.settings = SqlSettingsRepo(self._session)
        self.positions = SqlPositionsRepo(self._session)
        self.snapshot_pins = SqlSnapshotPinsRepo(self._session)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc:
                self._session.rollback()
            else:
                self._session.commit()
        finally:
            self._session.close()
            self._session = None

    def commit(self) -> None:
        assert self._session is not None
        self._session.commit()

    def rollback(self) -> None:
        assert self._session is not None
        self._session.rollback()
