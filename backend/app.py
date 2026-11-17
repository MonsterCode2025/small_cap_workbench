"""FastAPI应用：小市值策略研究工作台后端服务。"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .data import OUTPUT_ROOT, SHANGHAI, write_json
from .selection import SelectionConfig
from .portfolio import FeeConfig
from .backtest import BacktestEngine
from .data_loader import QuickDataLoader

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="小市值策略研究工作台",
    version="1.0.0",
    description="Small cap quantitative strategy research workbench"
)

# CORS配置（仅本地开发）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（仅本地开发环境）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BacktestRequest(BaseModel):
    """回测请求。"""
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    initial_cash: float = Field(1_000_000, ge=100_000, le=10_000_000)
    target_stocks: int = Field(30, ge=5, le=100)
    target_budget: float = Field(0.9, ge=0.1, le=1.0)
    min_adv20: float = Field(20_000_000, ge=0)
    slippage_bps: float = Field(5.0, ge=0, le=50)
    commission_rate: float = Field(0.0003, ge=0, le=0.01)


@app.get("/api/health")
def health():
    """健康检查。"""
    return {
        "status": "ok",
        "strategy": "small_cap_v1",
        "mode": "research",
        "timestamp": datetime.now(SHANGHAI).isoformat()
    }


@app.get("/api/experiments")
def list_experiments():
    """列出历史实验。"""
    experiments = []
    for path in sorted(OUTPUT_ROOT.glob("*/result.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            experiments.append({
                "experiment_id": path.parent.name,
                "created_at": result.get("created_at"),
                "summary": result.get("summary"),
                "config": result.get("config")
            })
        except Exception:
            continue

    return {"experiments": experiments}


@app.post("/api/backtest")
def run_backtest(request: BacktestRequest):
    """运行回测。"""
    try:
        # 创建输出目录
        experiment_id = str(uuid4())
        output_dir = OUTPUT_ROOT / experiment_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # 配置
        selection_config = SelectionConfig(
            target_stocks=request.target_stocks,
            target_budget=request.target_budget,
            min_adv20=request.min_adv20
        )

        fee_config = FeeConfig(
            commission_rate=request.commission_rate
        )

        # 创建回测引擎
        engine = BacktestEngine(
            selection_config=selection_config,
            fee_config=fee_config,
            initial_cash=request.initial_cash,
            slippage_bps=request.slippage_bps
        )

        # 加载数据（简化版：最多20只股票）
        print(f"\n{'='*60}")
        print(f"[实验 {experiment_id[:8]}] 开始回测")
        print(f"{'='*60}")

        loader = QuickDataLoader()
        data = loader.load_backtest_data(
            start_date=request.start_date,
            end_date=request.end_date,
            max_symbols=20,
            use_cache=True
        )

        # 执行回测
        print(f"\n[回测引擎] 开始运行...")
        backtest_result = engine.run(
            trading_dates=data["trading_dates"],
            universe_data=data["universe_data"],
            market_data=data["market_data"],
            start_date=request.start_date,
            end_date=request.end_date
        )

        print(f"[回测完成] 总收益: {backtest_result['summary'].get('total_return', 0)*100:.2f}%")
        print(f"{'='*60}\n")

        # 构建结果
        result = {
            "experiment_id": experiment_id,
            "status": "completed",
            "message": "回测完成（简化版：20只股票）",
            "created_at": datetime.now(SHANGHAI).isoformat(),
            "config": {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "initial_cash": request.initial_cash,
                "selection": selection_config.__dict__,
                "slippage_bps": request.slippage_bps
            },
            "data_summary": data["summary"],
            "summary": backtest_result["summary"],
            "equity_curve": backtest_result["equity"][-50:],  # 最后50天
            "trades": backtest_result["trades"][-50:],  # 最后50笔
            "orders": backtest_result["orders"][-50:],  # 最后50单
            "note": "当前为简化版回测（20只股票）。完整版需要数据审计通过后开启。"
        }

        # 保存结果
        write_json(output_dir / "result.json", result)

        # 保存完整数据
        write_json(output_dir / "full_result.json", {
            **result,
            "equity_curve_full": backtest_result["equity"],
            "trades_full": backtest_result["trades"],
            "orders_full": backtest_result["orders"]
        })

        return result

    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n\n{traceback.format_exc()}"
        print(f"\n[错误] {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)


@app.get("/api/experiments/{experiment_id}")
def get_experiment(experiment_id: str):
    """获取实验详情。"""
    result_path = OUTPUT_ROOT / experiment_id / "result.json"

    if not result_path.exists():
        raise HTTPException(status_code=404, detail="实验不存在")

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取实验失败: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
