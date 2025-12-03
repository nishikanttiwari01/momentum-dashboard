from __future__ import annotations

from datetime import date
from typing import List, Optional
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.simulator_service import (
    SimulatorService,
    SimulationParams,
)

router = APIRouter(prefix="/simulator", tags=["Simulator"])
_service = SimulatorService()


class SimulationParamsPayload(BaseModel):
    min_score: Optional[float] = Field(None, description="Minimum score filter")
    min_adx: Optional[float] = Field(None, description="Minimum ADX filter")
    atr_pct_min: Optional[float] = Field(None, description="Minimum ATR% filter")
    atr_pct_max: Optional[float] = Field(None, description="Maximum ATR% filter")
    prox52w_min_pct: Optional[float] = Field(None, description="Minimum 52W proximity pct")
    pivot_clear_min_pct: Optional[float] = Field(None, description="Min pivot clear pct")
    pivot_clear_max_pct: Optional[float] = Field(None, description="Max pivot clear pct")
    base_len_min_bars: Optional[int] = Field(None, description="Minimum base length bars")
    relvol20_min: Optional[float] = Field(None, description="Minimum RelVol20")
    day_change_max_pct: Optional[float] = Field(None, description="Max day change pct")
    liquidity_min: Optional[float] = Field(None, description="Minimum median traded value 20d")
    stop_loss_pct: Optional[float] = Field(None, description="Stop-loss percent in decimal (0.05 = 5%)")
    max_hold_days: Optional[int] = Field(None, description="Maximum holding days before timed exit")
    top_n: Optional[int] = Field(None, description="Cap pool size per day")
    first_trade_only: Optional[bool] = Field(False, description="If true, ignore re-entries after one full cycle")


class SimulationRequest(BaseModel):
    start_date: date = Field(..., description="Inclusive start date for simulation window")
    end_date: date = Field(..., description="Inclusive end date for simulation window")
    params: Optional[SimulationParamsPayload] = None
    variants: Optional[List[SimulationParamsPayload]] = Field(None, description="Optional overrides to test multiple combos")
    manual_symbols: Optional[List[str]] = Field(None, description="Optional symbols to buy manually on start date")


class TradeOut(BaseModel):
    symbol: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    pnl_pct: float
    holding_days: int
    notes: Optional[str] = None


class SeriesPointOut(BaseModel):
    date: str
    close: Optional[float]


class SimulationRunOut(BaseModel):
    label: str
    params: SimulationParamsPayload
    summary: dict
    trades: List[TradeOut]
    charts: dict[str, List[SeriesPointOut]]


class SimulationResponse(BaseModel):
    runs: List[SimulationRunOut]


def _merge_params(base: SimulationParams, override: Optional[SimulationParamsPayload]) -> SimulationParams:
    if override is None:
        return base
    return SimulationParams(
        min_score=override.min_score if override.min_score is not None else base.min_score,
        min_adx=override.min_adx if override.min_adx is not None else base.min_adx,
        atr_pct_min=override.atr_pct_min if override.atr_pct_min is not None else base.atr_pct_min,
        atr_pct_max=override.atr_pct_max if override.atr_pct_max is not None else base.atr_pct_max,
        prox52w_min_pct=override.prox52w_min_pct if override.prox52w_min_pct is not None else base.prox52w_min_pct,
        pivot_clear_min_pct=override.pivot_clear_min_pct if override.pivot_clear_min_pct is not None else base.pivot_clear_min_pct,
        pivot_clear_max_pct=override.pivot_clear_max_pct if override.pivot_clear_max_pct is not None else base.pivot_clear_max_pct,
        base_len_min_bars=override.base_len_min_bars if override.base_len_min_bars is not None else base.base_len_min_bars,
        relvol20_min=override.relvol20_min if override.relvol20_min is not None else base.relvol20_min,
        day_change_max_pct=override.day_change_max_pct if override.day_change_max_pct is not None else base.day_change_max_pct,
        liquidity_min=override.liquidity_min if override.liquidity_min is not None else base.liquidity_min,
        stop_loss_pct=override.stop_loss_pct if override.stop_loss_pct is not None else base.stop_loss_pct,
        max_hold_days=override.max_hold_days if override.max_hold_days is not None else base.max_hold_days,
        top_n=override.top_n if override.top_n is not None else base.top_n,
        first_trade_only=override.first_trade_only if override.first_trade_only is not None else base.first_trade_only,
    )


@router.post("/run", response_model=SimulationResponse)
def run_simulation(payload: SimulationRequest) -> SimulationResponse:
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    base_params = _merge_params(_service.default_params(), payload.params)
    variant_defs = []
    if payload.variants:
        for idx, v in enumerate(payload.variants):
            variant_defs.append((f"variant_{idx+1}", _merge_params(base_params, v)))

    runs = _service.run_with_variants(
        start=payload.start_date,
        end=payload.end_date,
        base_params=base_params,
        variants=variant_defs,
        manual_symbols=payload.manual_symbols,
    )

    out_runs: List[SimulationRunOut] = []
    for run in runs:
        out_runs.append(
            SimulationRunOut(
                label=run.label,
                params=SimulationParamsPayload(**asdict(run.params)),  # type: ignore
                summary=run.summary,
                trades=[
                    TradeOut(
                        symbol=t.symbol,
                        entry_date=t.entry_date,
                        exit_date=t.exit_date,
                        entry_price=t.entry_price,
                        exit_price=t.exit_price,
                        pnl_pct=t.pnl_pct,
                        holding_days=t.holding_days,
                        notes=t.notes,
                    )
                    for t in run.trades
                ],
                charts={k: [SeriesPointOut(**asdict(p)) for p in v] for k, v in run.charts.items()},
            )
        )

    return SimulationResponse(runs=out_runs)
