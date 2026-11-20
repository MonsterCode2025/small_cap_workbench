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
from .data_loader import DataLoader
from .data_audit import DataAuditor
from .period_manager import PeriodManager
from .factor_analysis import FactorAnalyzer
from .reports import AnalysisReport

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# 初始化数据审计器和区间管理器
auditor = DataAuditor()
period_manager = PeriodManager()

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
    stock_filter: str = Field("mainboard", description="股票过滤: all/mainboard/sample")
    max_symbols: int | None = Field(None, description="最大股票数限制，None表示不限制")


class FactorAnalysisRequest(BaseModel):
    """因子分析请求。"""
    experiment_id: str = Field(..., description="关联的回测实验ID")
    include_html_report: bool = Field(True, description="是否生成HTML报告")


@app.get("/api/health")
def health():
    """健康检查。"""
    return {
        "status": "ok",
        "strategy": "small_cap_v1",
        "mode": "production",
        "version": "1.0.0",
        "timestamp": datetime.now(SHANGHAI).isoformat()
    }


@app.get("/api/audit")
def run_audit(start_date: str, end_date: str):
    """运行数据审计。"""
    try:
        audit_report = auditor.run_full_audit(
            start_date=start_date,
            end_date=end_date,
            min_trading_days=200,
            min_symbols=1000
        )
        return audit_report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"审计失败: {str(e)}")


@app.get("/api/periods")
def list_periods():
    """列出所有回测区间。"""
    return period_manager.get_config_summary()


@app.post("/api/periods/lock")
def lock_period(period_name: str):
    """锁定指定区间。"""
    try:
        period = period_manager.lock_period(period_name)
        return {
            "success": True,
            "message": f"区间 '{period_name}' 已锁定",
            "period": period.__dict__
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    """运行回测（完整版）。"""
    try:
        # 创建输出目录
        experiment_id = str(uuid4())
        output_dir = OUTPUT_ROOT / experiment_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # 验证区间（可选：如果需要强制检查）
        validation = period_manager.validate_backtest_request(
            start_date=request.start_date,
            end_date=request.end_date,
            allowed_purposes=["research", "validation"]  # 不允许直接使用封存区间
        )

        warnings = validation.get("warnings", [])

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

        # 加载数据（完整版）
        print(f"\n{'='*60}")
        print(f"[实验 {experiment_id[:8]}] 开始回测")
        print(f"{'='*60}")

        loader = DataLoader()
        data = loader.load_backtest_data(
            start_date=request.start_date,
            end_date=request.end_date,
            stock_filter=request.stock_filter,
            max_symbols=request.max_symbols,
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
            "message": f"回测完成（{data['summary']['successful_symbols']} 只股票）",
            "created_at": datetime.now(SHANGHAI).isoformat(),
            "config": {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "initial_cash": request.initial_cash,
                "selection": selection_config.__dict__,
                "slippage_bps": request.slippage_bps,
                "stock_filter": request.stock_filter,
                "max_symbols": request.max_symbols
            },
            "data_summary": data["summary"],
            "summary": backtest_result["summary"],
            "equity_curve": backtest_result["equity"][-100:],  # 最后100天
            "trades": backtest_result["trades"][-100:],  # 最后100笔
            "orders": backtest_result["orders"][-100:],  # 最后100单
            "warnings": warnings
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

        return {**result, "equity_curve": backtest_result["equity"]}

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
        full_result_path = result_path.with_name("full_result.json")
        if full_result_path.exists():
            full_result = json.loads(full_result_path.read_text(encoding="utf-8"))
            if "equity_curve_full" in full_result:
                result["equity_curve"] = full_result["equity_curve_full"]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取实验失败: {e}")


@app.post("/api/factor-analysis")
def run_factor_analysis(request: FactorAnalysisRequest):
    """运行因子分析。

    对关联的回测实验进行 IC、分组收益、暴露和 Alpha 分析，
    并生成 JSON 和 HTML 报告。
    """
    try:
        # 读取对应的回测结果
        result_path = OUTPUT_ROOT / request.experiment_id / "full_result.json"

        if not result_path.exists():
            raise HTTPException(status_code=404, detail=f"实验不存在: {request.experiment_id}")

        backtest_result = json.loads(result_path.read_text(encoding="utf-8"))

        # 重新加载市场数据
        start_date = backtest_result["config"]["start_date"]
        end_date = backtest_result["config"]["end_date"]

        print(f"\n{'='*60}")
        print(f"[因子分析 {request.experiment_id[:8]}] 开始分析")
        print(f"{'='*60}")

        loader = DataLoader()
        data = loader.load_backtest_data(
            start_date=start_date,
            end_date=end_date,
            stock_filter=backtest_result["config"].get("stock_filter", "mainboard"),
            max_symbols=backtest_result["config"].get("max_symbols"),
            use_cache=True
        )

        # 执行因子分析
        analyzer = FactorAnalyzer()

        # 构造简单的行业映射（默认所有为同一行业）
        symbol_industry = {
            s: "C34" for s in data["market_data"].keys()
        }

        analysis_result = analyzer.analyze_full(
            backtest_result=backtest_result,
            market_data=data["market_data"],
            symbol_industry=symbol_industry
        )

        print(f"[因子分析完成] IC样本数: {len(analysis_result.get('rank_ic_series', []))}")

        # 生成报告
        report = AnalysisReport(analysis_result)

        # 创建输出目录
        output_dir = OUTPUT_ROOT / request.experiment_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # 保存 JSON 报告
        json_report_path = output_dir / "factor_analysis.json"
        report.save_json(json_report_path)

        # 如果需要，保存 HTML 报告
        if request.include_html_report:
            html_report_path = output_dir / "factor_report.html"
            report.save_html(html_report_path)

        # 构建响应
        response = {
            "success": True,
            "experiment_id": request.experiment_id,
            "analysis": analysis_result,
            "report_paths": {
                "json": str(json_report_path.relative_to(Path.cwd())),
            }
        }

        if request.include_html_report:
            response["report_paths"]["html"] = str(html_report_path.relative_to(Path.cwd()))

        print(f"{'='*60}\n")

        return response

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n\n{traceback.format_exc()}"
        print(f"\n[因子分析错误] {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
