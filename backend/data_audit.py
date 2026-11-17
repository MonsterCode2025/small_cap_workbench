"""数据审计模块：验证历史数据完整性和可靠性。

对应设计文档第一阶段：数据契约验证。
"""
from __future__ import annotations

import pandas as pd
from dataclasses import dataclass
from typing import Literal
from datetime import datetime

from .data import fetch_trading_calendar, fetch_stock_list


@dataclass
class AuditResult:
    """审计结果。"""
    passed: bool
    message: str
    details: dict
    timestamp: str


class DataAuditor:
    """数据审计器：检查历史数据的完整性和可靠性。"""

    def __init__(self):
        self.audit_history = []

    def audit_trading_calendar(
        self,
        start_date: str,
        end_date: str,
        min_expected_days: int = 200
    ) -> AuditResult:
        """审计交易日历的完整性。

        Args:
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            min_expected_days: 最小预期交易日数

        Returns:
            AuditResult
        """
        try:
            calendar = fetch_trading_calendar(start_date, end_date)
            trading_days = len(calendar)

            # 检查是否有足够的交易日
            passed = trading_days >= min_expected_days

            details = {
                "start_date": start_date,
                "end_date": end_date,
                "trading_days": trading_days,
                "min_expected_days": min_expected_days,
                "coverage": trading_days / min_expected_days if min_expected_days > 0 else 0
            }

            if passed:
                message = f"✓ 交易日历审计通过：{trading_days} 个交易日（预期 ≥{min_expected_days}）"
            else:
                message = f"✗ 交易日历审计失败：仅 {trading_days} 个交易日（预期 ≥{min_expected_days}）"

            result = AuditResult(
                passed=passed,
                message=message,
                details=details,
                timestamp=datetime.now().isoformat()
            )

            self.audit_history.append(("trading_calendar", result))
            return result

        except Exception as e:
            result = AuditResult(
                passed=False,
                message=f"✗ 交易日历审计异常: {str(e)}",
                details={"error": str(e)},
                timestamp=datetime.now().isoformat()
            )
            self.audit_history.append(("trading_calendar", result))
            return result

    def audit_stock_universe(
        self,
        min_symbols: int = 1000,
        required_exchanges: list[str] = None
    ) -> AuditResult:
        """审计股票池的完整性。

        Args:
            min_symbols: 最小股票数量
            required_exchanges: 必需的交易所列表

        Returns:
            AuditResult
        """
        if required_exchanges is None:
            required_exchanges = ["SH", "SZ"]

        try:
            stock_list = fetch_stock_list()
            total_symbols = len(stock_list)

            # 检查股票数量
            quantity_check = total_symbols >= min_symbols

            # 检查交易所覆盖
            exchanges = stock_list["exchange"].unique().tolist()
            exchange_check = all(ex in exchanges for ex in required_exchanges)

            # 统计各交易所股票数
            exchange_counts = stock_list["exchange"].value_counts().to_dict()

            passed = quantity_check and exchange_check

            details = {
                "total_symbols": total_symbols,
                "min_symbols": min_symbols,
                "exchanges": exchanges,
                "required_exchanges": required_exchanges,
                "exchange_counts": exchange_counts,
                "quantity_check": quantity_check,
                "exchange_check": exchange_check
            }

            if passed:
                message = f"✓ 股票池审计通过：{total_symbols} 只股票（预期 ≥{min_symbols}），覆盖交易所 {exchanges}"
            else:
                reasons = []
                if not quantity_check:
                    reasons.append(f"股票数不足（{total_symbols} < {min_symbols}）")
                if not exchange_check:
                    missing = set(required_exchanges) - set(exchanges)
                    reasons.append(f"缺少交易所 {missing}")
                message = f"✗ 股票池审计失败：{', '.join(reasons)}"

            result = AuditResult(
                passed=passed,
                message=message,
                details=details,
                timestamp=datetime.now().isoformat()
            )

            self.audit_history.append(("stock_universe", result))
            return result

        except Exception as e:
            result = AuditResult(
                passed=False,
                message=f"✗ 股票池审计异常: {str(e)}",
                details={"error": str(e)},
                timestamp=datetime.now().isoformat()
            )
            self.audit_history.append(("stock_universe", result))
            return result

    def audit_market_data_availability(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str,
        sample_size: int = 10,
        min_success_rate: float = 0.8
    ) -> AuditResult:
        """审计市场数据的可用性（抽样检查）。

        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            sample_size: 抽样数量
            min_success_rate: 最低成功率

        Returns:
            AuditResult
        """
        from .data import fetch_daily_quotes
        import random

        try:
            # 抽样
            sample_symbols = random.sample(symbols, min(sample_size, len(symbols)))

            success_count = 0
            failed_symbols = []
            data_records = {}

            for symbol in sample_symbols:
                try:
                    quotes = fetch_daily_quotes(symbol, start_date, end_date)
                    if not quotes.empty and len(quotes) > 0:
                        success_count += 1
                        data_records[symbol] = len(quotes)
                    else:
                        failed_symbols.append((symbol, "无数据"))
                except Exception as e:
                    failed_symbols.append((symbol, str(e)))

            success_rate = success_count / len(sample_symbols)
            passed = success_rate >= min_success_rate

            details = {
                "sample_size": len(sample_symbols),
                "success_count": success_count,
                "failed_count": len(failed_symbols),
                "success_rate": success_rate,
                "min_success_rate": min_success_rate,
                "failed_symbols": failed_symbols,
                "data_records": data_records
            }

            if passed:
                message = f"✓ 市场数据审计通过：成功率 {success_rate*100:.1f}%（{success_count}/{len(sample_symbols)}）"
            else:
                message = f"✗ 市场数据审计失败：成功率 {success_rate*100:.1f}%（预期 ≥{min_success_rate*100:.1f}%）"

            result = AuditResult(
                passed=passed,
                message=message,
                details=details,
                timestamp=datetime.now().isoformat()
            )

            self.audit_history.append(("market_data", result))
            return result

        except Exception as e:
            result = AuditResult(
                passed=False,
                message=f"✗ 市场数据审计异常: {str(e)}",
                details={"error": str(e)},
                timestamp=datetime.now().isoformat()
            )
            self.audit_history.append(("market_data", result))
            return result

    def run_full_audit(
        self,
        start_date: str,
        end_date: str,
        min_trading_days: int = 200,
        min_symbols: int = 1000
    ) -> dict:
        """运行完整的数据审计流程。

        Args:
            start_date: 开始日期
            end_date: 结束日期
            min_trading_days: 最小交易日数
            min_symbols: 最小股票数

        Returns:
            审计报告字典
        """
        print("\n" + "="*60)
        print("开始数据审计")
        print("="*60)

        # 1. 审计交易日历
        print("\n[1/3] 审计交易日历...")
        calendar_result = self.audit_trading_calendar(start_date, end_date, min_trading_days)
        print(f"  {calendar_result.message}")

        # 2. 审计股票池
        print("\n[2/3] 审计股票池...")
        universe_result = self.audit_stock_universe(min_symbols)
        print(f"  {universe_result.message}")

        # 3. 审计市场数据（如果股票池通过）
        print("\n[3/3] 审计市场数据可用性...")
        if universe_result.passed:
            stock_list = fetch_stock_list()
            symbols = stock_list["symbol"].tolist()
            market_data_result = self.audit_market_data_availability(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                sample_size=20,
                min_success_rate=0.7
            )
            print(f"  {market_data_result.message}")
        else:
            market_data_result = AuditResult(
                passed=False,
                message="✗ 跳过市场数据审计（股票池审计未通过）",
                details={"skipped": True},
                timestamp=datetime.now().isoformat()
            )

        # 汇总结果
        all_passed = all([
            calendar_result.passed,
            universe_result.passed,
            market_data_result.passed
        ])

        print("\n" + "="*60)
        if all_passed:
            print("✓ 数据审计通过 - 可以进行完整回测")
        else:
            print("✗ 数据审计未通过 - 请检查数据质量")
        print("="*60 + "\n")

        return {
            "passed": all_passed,
            "timestamp": datetime.now().isoformat(),
            "results": {
                "trading_calendar": calendar_result.__dict__,
                "stock_universe": universe_result.__dict__,
                "market_data": market_data_result.__dict__
            },
            "summary": {
                "total_checks": 3,
                "passed_checks": sum([
                    calendar_result.passed,
                    universe_result.passed,
                    market_data_result.passed
                ]),
                "trading_days": calendar_result.details.get("trading_days", 0),
                "total_symbols": universe_result.details.get("total_symbols", 0),
                "data_success_rate": market_data_result.details.get("success_rate", 0)
            }
        }

    def get_audit_report(self) -> dict:
        """获取审计历史报告。"""
        return {
            "total_audits": len(self.audit_history),
            "history": [
                {
                    "type": audit_type,
                    "passed": result.passed,
                    "message": result.message,
                    "timestamp": result.timestamp
                }
                for audit_type, result in self.audit_history
            ]
        }
