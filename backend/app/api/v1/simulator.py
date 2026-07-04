from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4

from app.services.simulator_service import (
    SimulatorService,
    SimulationParams,
)

router = APIRouter(prefix="/simulator", tags=["Simulator"])
_service = SimulatorService()

_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_JOBS: Dict[str, dict] = {}
_JOBS_LOCK = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_job(job_id: str) -> Optional[dict]:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def _set_job(job_id: str, payload: dict) -> None:
    with _JOBS_LOCK:
        _JOBS[job_id] = payload


def _update_job(job_id: str, **updates: object) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = _now_iso()


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
    take_profit_pct: Optional[float] = Field(None, description="Take-profit percent in decimal (0.10 = 10%)")
    round_trip_cost_pct: Optional[float] = Field(None, description="Round-trip costs and slippage in decimal (0.0035 = 0.35%)")
    max_hold_days: Optional[int] = Field(None, description="Maximum holding days before timed exit")
    top_n: Optional[int] = Field(None, description="Cap pool size per day")
    first_trade_only: Optional[bool] = Field(False, description="If true, ignore re-entries after one full cycle")
    recommendation_only: Optional[bool] = Field(True, description="If true, require recommendation/next_action buy signals")


class SimulationSweep(BaseModel):
    enabled: bool = Field(False, description="Enable automatic sweep across parameter ranges")
    min_runs: int = Field(20, ge=1, le=5000, description="Minimum total runs before early-stop checks")
    max_runs: int = Field(200, ge=1, le=5000, description="Maximum total runs (including baseline)")
    seed: int = Field(42, ge=0, description="Seed for sweep sampling")
    target_total_return_pct: float = Field(10.0, ge=-1000, le=1000, description="Target total return percent to stop early")
    prefer_profitable: bool = Field(True, description="If true, rank/return profitable runs first when available")
    ranges: Optional[dict[str, List[float]]] = Field(
        None,
        description="Optional parameter ranges for sweep; keys match SimulationParamsPayload fields",
    )


class SimulationRequest(BaseModel):
    start_date: date = Field(..., description="Inclusive start date for simulation window")
    end_date: date = Field(..., description="Inclusive end date for simulation window")
    params: Optional[SimulationParamsPayload] = None
    variants: Optional[List[SimulationParamsPayload]] = Field(None, description="Optional overrides to test multiple combos")
    manual_symbols: Optional[List[str]] = Field(None, description="Optional symbols to buy manually on start date")
    sweep: Optional[SimulationSweep] = Field(None, description="Optional auto-sweep configuration")


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
    meta: Optional[dict] = None


class SimulationJobStart(BaseModel):
    job_id: str


class SimulationJobProgress(BaseModel):
    completed: int = 0
    total: int = 0
    label: Optional[str] = None


class SimulationJobStatus(BaseModel):
    job_id: str
    status: str
    progress: SimulationJobProgress
    meta: Optional[dict] = None
    error: Optional[str] = None


def _serialize_runs(runs: List, meta: Optional[dict]) -> SimulationResponse:
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
    return SimulationResponse(runs=out_runs, meta=meta)


def _merge_params(base: SimulationParams, override: Optional[SimulationParamsPayload]) -> SimulationParams:
    if override is None:
        return base
    fields_set = getattr(override, "model_fields_set", None)
    if fields_set is None:
        fields_set = getattr(override, "__fields_set__", set())

    def use(field: str, fallback: object) -> object:
        if field in fields_set:
            return getattr(override, field)
        return fallback

    return SimulationParams(
        min_score=use("min_score", base.min_score),
        min_adx=use("min_adx", base.min_adx),
        atr_pct_min=use("atr_pct_min", base.atr_pct_min),
        atr_pct_max=use("atr_pct_max", base.atr_pct_max),
        prox52w_min_pct=use("prox52w_min_pct", base.prox52w_min_pct),
        pivot_clear_min_pct=use("pivot_clear_min_pct", base.pivot_clear_min_pct),
        pivot_clear_max_pct=use("pivot_clear_max_pct", base.pivot_clear_max_pct),
        base_len_min_bars=use("base_len_min_bars", base.base_len_min_bars),
        relvol20_min=use("relvol20_min", base.relvol20_min),
        day_change_max_pct=use("day_change_max_pct", base.day_change_max_pct),
        liquidity_min=use("liquidity_min", base.liquidity_min),
        stop_loss_pct=use("stop_loss_pct", base.stop_loss_pct),
        take_profit_pct=use("take_profit_pct", base.take_profit_pct),
        round_trip_cost_pct=use("round_trip_cost_pct", base.round_trip_cost_pct),
        max_hold_days=use("max_hold_days", base.max_hold_days),
        top_n=use("top_n", base.top_n),
        first_trade_only=use("first_trade_only", base.first_trade_only),
        recommendation_only=use("recommendation_only", base.recommendation_only),
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

    sweep_cfg = None
    if payload.sweep and payload.sweep.enabled:
        sweep_cfg = payload.sweep.model_dump()

    runs, meta = _service.run_with_variants(
        start=payload.start_date,
        end=payload.end_date,
        base_params=base_params,
        variants=variant_defs,
        sweep=sweep_cfg,
        manual_symbols=payload.manual_symbols,
    )

    return _serialize_runs(runs, meta)


@router.post("/run_async", response_model=SimulationJobStart)
def run_simulation_async(payload: SimulationRequest) -> SimulationJobStart:
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    base_params = _merge_params(_service.default_params(), payload.params)
    variant_defs = []
    if payload.variants:
        for idx, v in enumerate(payload.variants):
            variant_defs.append((f"variant_{idx+1}", _merge_params(base_params, v)))

    sweep_cfg = None
    if payload.sweep and payload.sweep.enabled:
        sweep_cfg = payload.sweep.model_dump()

    job_id = uuid4().hex
    _set_job(
        job_id,
        {
            "job_id": job_id,
            "status": "running",
            "progress": {"completed": 0, "total": 0, "label": None},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "meta": None,
            "error": None,
            "result": None,
        },
    )

    def _progress_cb(completed: int, total: int, label: str) -> None:
        _update_job(job_id, progress={"completed": completed, "total": total, "label": label})

    def _work() -> None:
        try:
            runs, meta = _service.run_with_variants(
                start=payload.start_date,
                end=payload.end_date,
                base_params=base_params,
                variants=variant_defs,
                sweep=sweep_cfg,
                manual_symbols=payload.manual_symbols,
                progress_cb=_progress_cb,
            )
            result = _serialize_runs(runs, meta).model_dump()
            job = _get_job(job_id) or {}
            progress = job.get("progress") or {"completed": len(runs), "total": len(runs), "label": None}
            completed = int(progress.get("completed", len(runs)) or len(runs))
            total = int(progress.get("total", len(runs)) or len(runs))
            if completed < total and meta and meta.get("stopped_early"):
                total = completed
            _update_job(job_id, status="done", result=result, meta=meta, progress={"completed": completed, "total": total, "label": progress.get("label")})
        except Exception as exc:
            _update_job(job_id, status="error", error=str(exc))

    _EXECUTOR.submit(_work)

    return SimulationJobStart(job_id=job_id)


@router.get("/status/{job_id}", response_model=SimulationJobStatus)
def get_simulation_status(job_id: str) -> SimulationJobStatus:
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return SimulationJobStatus(
        job_id=job_id,
        status=job.get("status"),
        progress=SimulationJobProgress(**(job.get("progress") or {})),
        meta=job.get("meta"),
        error=job.get("error"),
    )


@router.get("/result/{job_id}", response_model=SimulationResponse)
def get_simulation_result(job_id: str) -> SimulationResponse:
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.get("status") != "done":
        raise HTTPException(status_code=202, detail="job not complete")
    result = job.get("result") or {}
    return SimulationResponse(**result)
