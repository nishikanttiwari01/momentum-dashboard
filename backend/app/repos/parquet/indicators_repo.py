from __future__ import annotations
import pyarrow.compute as pc
from typing import Optional
from app.repos.parquet import datasets

class IndicatorsRepo:
    def read_one(self, *, symbol: str, run_id: str) -> dict | None:
        tab = datasets.scan("indicators", run_id=run_id, columns=None)
        if "symbol" not in tab.schema.names:
            return None
        t2 = tab.filter(pc.equal(tab["symbol"], symbol))
        if t2.num_rows == 0:
            return None
        return {name: t2[name][0].as_py() for name in t2.column_names}
