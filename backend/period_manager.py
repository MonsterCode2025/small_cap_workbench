"""区间管理模块：管理研究/验证/封存区间，避免过拟合。

对应设计文档：独立验证原则，区间分离。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class Period:
    """时间区间定义。"""
    name: str
    start_date: str
    end_date: str
    purpose: Literal["research", "validation", "reserved"]
    locked: bool
    description: str


class PeriodManager:
    """区间管理器：管理历史回测区间的分配和锁定。"""

    def __init__(self, config_path: Path | None = None):
        """初始化区间管理器。

        Args:
            config_path: 配置文件路径，默认为 backend/../data/periods.json
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "data" / "periods.json"

        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.periods: dict[str, Period] = {}
        self._load_config()

    def _load_config(self):
        """加载配置文件。"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for name, period_data in data.get("periods", {}).items():
                    self.periods[name] = Period(**period_data)

            except Exception as e:
                print(f"警告：加载区间配置失败: {e}")
                self.periods = {}
        else:
            # 初始化默认配置
            self._initialize_default_periods()

    def _save_config(self):
        """保存配置文件。"""
        data = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "periods": {
                name: asdict(period)
                for name, period in self.periods.items()
            }
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _initialize_default_periods(self):
        """初始化默认区间配置。"""
        # 默认区间划分示例
        self.periods = {
            "research_2020_2022": Period(
                name="research_2020_2022",
                start_date="2020-01-01",
                end_date="2022-12-31",
                purpose="research",
                locked=False,
                description="研究区间：用于策略开发和参数调优"
            ),
            "validation_2023": Period(
                name="validation_2023",
                start_date="2023-01-01",
                end_date="2023-12-31",
                purpose="validation",
                locked=False,
                description="验证区间：独立验证策略效果"
            ),
            "reserved_2024": Period(
                name="reserved_2024",
                start_date="2024-01-01",
                end_date="2024-12-31",
                purpose="reserved",
                locked=False,
                description="封存区间：保留作为真正的样本外测试"
            )
        }
        self._save_config()

    def define_period(
        self,
        name: str,
        start_date: str,
        end_date: str,
        purpose: Literal["research", "validation", "reserved"],
        description: str = ""
    ) -> Period:
        """定义一个新的时间区间。

        Args:
            name: 区间名称（唯一标识）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            purpose: 区间用途
            description: 描述

        Returns:
            Period
        """
        if name in self.periods:
            raise ValueError(f"区间 '{name}' 已存在")

        period = Period(
            name=name,
            start_date=start_date,
            end_date=end_date,
            purpose=purpose,
            locked=False,
            description=description
        )

        self.periods[name] = period
        self._save_config()

        print(f"✓ 已定义区间: {name} ({start_date} 至 {end_date}, {purpose})")
        return period

    def lock_period(self, name: str) -> Period:
        """锁定一个区间，防止修改。

        Args:
            name: 区间名称

        Returns:
            Period
        """
        if name not in self.periods:
            raise ValueError(f"区间 '{name}' 不存在")

        period = self.periods[name]

        if period.locked:
            print(f"⚠️ 区间 '{name}' 已经被锁定")
            return period

        period.locked = True
        self._save_config()

        print(f"🔒 已锁定区间: {name} ({period.start_date} 至 {period.end_date})")
        print(f"   用途: {period.purpose}")
        print(f"   描述: {period.description}")

        return period

    def unlock_period(self, name: str, force: bool = False) -> Period:
        """解锁一个区间（需要明确确认）。

        Args:
            name: 区间名称
            force: 强制解锁

        Returns:
            Period
        """
        if name not in self.periods:
            raise ValueError(f"区间 '{name}' 不存在")

        period = self.periods[name]

        if not period.locked:
            print(f"⚠️ 区间 '{name}' 未被锁定")
            return period

        if not force:
            raise ValueError(f"区间 '{name}' 已锁定，解锁需要设置 force=True")

        period.locked = False
        self._save_config()

        print(f"🔓 已解锁区间: {name}")
        return period

    def get_period(self, name: str) -> Period:
        """获取区间信息。

        Args:
            name: 区间名称

        Returns:
            Period
        """
        if name not in self.periods:
            raise ValueError(f"区间 '{name}' 不存在")

        return self.periods[name]

    def list_periods(self, purpose: str | None = None) -> list[Period]:
        """列出所有区间。

        Args:
            purpose: 可选，按用途过滤

        Returns:
            区间列表
        """
        periods = list(self.periods.values())

        if purpose:
            periods = [p for p in periods if p.purpose == purpose]

        # 按开始日期排序
        periods.sort(key=lambda p: p.start_date)

        return periods

    def validate_backtest_request(
        self,
        start_date: str,
        end_date: str,
        allowed_purposes: list[str] | None = None
    ) -> dict:
        """验证回测请求是否在允许的区间内。

        Args:
            start_date: 请求的开始日期
            end_date: 请求的结束日期
            allowed_purposes: 允许的区间用途列表，None表示允许所有

        Returns:
            验证结果字典
        """
        matching_periods = []
        warnings = []

        for period in self.periods.values():
            # 检查日期是否在区间内
            if start_date >= period.start_date and end_date <= period.end_date:
                matching_periods.append(period)

        if not matching_periods:
            return {
                "valid": False,
                "message": f"请求的日期范围 {start_date} 至 {end_date} 不在任何已定义的区间内",
                "matching_periods": []
            }

        # 检查用途限制
        if allowed_purposes:
            valid_periods = [p for p in matching_periods if p.purpose in allowed_purposes]
            if not valid_periods:
                return {
                    "valid": False,
                    "message": f"请求的日期范围仅匹配到不允许的区间用途",
                    "matching_periods": [asdict(p) for p in matching_periods]
                }
            matching_periods = valid_periods

        # 检查锁定状态
        for period in matching_periods:
            if period.locked and period.purpose == "reserved":
                warnings.append(f"⚠️ 区间 '{period.name}' 已锁定为封存区间，使用后将不再是真正的样本外数据")

        return {
            "valid": True,
            "message": "请求的日期范围有效",
            "matching_periods": [asdict(p) for p in matching_periods],
            "warnings": warnings
        }

    def print_summary(self):
        """打印区间配置摘要。"""
        print("\n" + "="*60)
        print("历史回测区间配置")
        print("="*60)

        if not self.periods:
            print("  暂无已定义的区间")
        else:
            for purpose in ["research", "validation", "reserved"]:
                periods = [p for p in self.periods.values() if p.purpose == purpose]
                if periods:
                    purpose_names = {
                        "research": "研究区间",
                        "validation": "验证区间",
                        "reserved": "封存区间"
                    }
                    print(f"\n【{purpose_names[purpose]}】")
                    for period in sorted(periods, key=lambda p: p.start_date):
                        lock_icon = "🔒" if period.locked else "🔓"
                        print(f"  {lock_icon} {period.name}")
                        print(f"     时间: {period.start_date} 至 {period.end_date}")
                        print(f"     描述: {period.description}")

        print("\n" + "="*60 + "\n")

    def get_config_summary(self) -> dict:
        """获取配置摘要（用于API返回）。"""
        return {
            "total_periods": len(self.periods),
            "by_purpose": {
                "research": len([p for p in self.periods.values() if p.purpose == "research"]),
                "validation": len([p for p in self.periods.values() if p.purpose == "validation"]),
                "reserved": len([p for p in self.periods.values() if p.purpose == "reserved"])
            },
            "locked_periods": [p.name for p in self.periods.values() if p.locked],
            "periods": [asdict(p) for p in sorted(self.periods.values(), key=lambda p: p.start_date)]
        }
