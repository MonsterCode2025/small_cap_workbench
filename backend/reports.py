"""报告生成模块：JSON 和 HTML 报告。"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from jinja2 import Template


class AnalysisReport:
    """因子分析报告类。"""

    def __init__(self, analysis_result: dict):
        """初始化报告。

        Args:
            analysis_result: 来自 FactorAnalyzer.analyze_full() 的结果字典
        """
        self.analysis_result = analysis_result
        self.timestamp = datetime.now().isoformat()

    def to_json(self) -> str:
        """生成 JSON 格式报告。

        Returns:
            JSON 字符串
        """
        report_dict = {
            "timestamp": self.timestamp,
            "analysis": self.analysis_result,
        }
        return json.dumps(report_dict, ensure_ascii=False, indent=2)

    def to_html(self) -> str:
        """生成 HTML 格式报告。

        Returns:
            HTML 字符串
        """
        template_str = REPORT_TEMPLATE

        # 准备模板数据
        rank_ic_series = self.analysis_result.get("rank_ic_series", [])
        group_returns = self.analysis_result.get("group_returns", {})
        exposure = self.analysis_result.get("exposure", {})
        alpha = self.analysis_result.get("alpha", {})
        summary = self.analysis_result.get("summary", {})

        # 计算 IC 统计
        ic_values = [ic.get("ic", 0) for ic in rank_ic_series]
        avg_ic = sum(ic_values) / len(ic_values) if ic_values else 0
        ic_std = (
            (sum((ic - avg_ic) ** 2 for ic in ic_values) / len(ic_values)) ** 0.5
            if ic_values
            else 0
        )
        ic_tstat = avg_ic / ic_std if ic_std > 0 else 0

        # 生成 IC 时间序列表格 HTML
        ic_table_html = _generate_ic_table(rank_ic_series)

        # 生成分组收益表格 HTML
        groups_table_html = _generate_groups_table(group_returns)

        # 生成行业权重对比表 HTML
        industry_table_html = _generate_industry_table(exposure)

        # 生成 Alpha 分解表 HTML
        alpha_table_html = _generate_alpha_table(alpha)

        template = Template(template_str)
        html = template.render(
            timestamp=self.timestamp,
            avg_ic=f"{avg_ic:.4f}",
            ic_std=f"{ic_std:.4f}",
            ic_tstat=f"{ic_tstat:.4f}",
            ic_count=len(rank_ic_series),
            ic_table=ic_table_html,
            groups_table=groups_table_html,
            industry_table=industry_table_html,
            alpha_table=alpha_table_html,
            group1_excess_return=f"{group_returns.get('group1_excess_return', 0):.4f}",
            monotonicity=group_returns.get("monotonicity_check", False),
            avg_market_cap=f"{exposure.get('avg_market_cap', 0):.0f}",
            benchmark_avg_market_cap=f"{exposure.get('benchmark_avg_market_cap', 0):.0f}",
            total_excess_return=f"{alpha.get('total_excess_return', 0):.4f}",
            security_alpha=f"{alpha.get('security_selection_alpha', 0):.4f}",
            alpha_ratio=f"{alpha.get('alpha_ratio', 0):.4f}",
        )

        return html

    def save_json(self, filepath: Path | str):
        """保存 JSON 报告到文件。

        Args:
            filepath: 文件路径
        """
        Path(filepath).write_text(self.to_json(), encoding="utf-8")

    def save_html(self, filepath: Path | str):
        """保存 HTML 报告到文件。

        Args:
            filepath: 文件路径
        """
        Path(filepath).write_text(self.to_html(), encoding="utf-8")


def _generate_ic_table(rank_ic_series: list) -> str:
    """生成 IC 时间序列表格。"""
    if not rank_ic_series:
        return "<p>无 IC 数据</p>"

    rows = []
    for ic in rank_ic_series:
        rows.append(
            f"""
        <tr>
            <td>{ic.get('signal_date', '')}</td>
            <td>{ic.get('ic', 0):.4f}</td>
            <td>{ic.get('p_value', 1):.4f}</td>
            <td>{ic.get('sample_size', 0)}</td>
        </tr>
        """
        )

    return f"""
    <table border="1" cellpadding="5" cellspacing="0" style="width:100%">
        <tr style="background-color:#f2f2f2">
            <th>信号日期</th>
            <th>IC 值</th>
            <th>P-Value</th>
            <th>样本数</th>
        </tr>
        {''.join(rows)}
    </table>
    """


def _generate_groups_table(group_returns: dict) -> str:
    """生成分组收益表格。"""
    groups = group_returns.get("groups", {})
    if not groups:
        return "<p>无分组数据</p>"

    rows = []
    for gid in sorted(groups.keys()):
        g = groups[gid]
        rows.append(
            f"""
        <tr>
            <td>第{g.get('group_id', gid)}组</td>
            <td>{g.get('avg_return', 0):.4f}</td>
            <td>{g.get('cumulative_return', 0):.4f}</td>
            <td>{g.get('symbols_count', 0)}</td>
            <td>{g.get('avg_market_cap', 0):.0f}</td>
        </tr>
        """
        )

    return f"""
    <table border="1" cellpadding="5" cellspacing="0" style="width:100%">
        <tr style="background-color:#f2f2f2">
            <th>分组</th>
            <th>平均收益</th>
            <th>累计收益</th>
            <th>股票数</th>
            <th>平均市值</th>
        </tr>
        {''.join(rows)}
    </table>
    """


def _generate_industry_table(exposure: dict) -> str:
    """生成行业权重对比表格。"""
    strategy_ind = exposure.get("strategy_industry_weights", {})
    benchmark_ind = exposure.get("benchmark_industry_weights", {})

    if not strategy_ind and not benchmark_ind:
        return "<p>无行业数据</p>"

    all_industries = set(strategy_ind.keys()) | set(benchmark_ind.keys())
    rows = []

    for ind in sorted(all_industries):
        st_weight = strategy_ind.get(ind, 0)
        bm_weight = benchmark_ind.get(ind, 0)
        overweight = st_weight - bm_weight

        rows.append(
            f"""
        <tr>
            <td>{ind or 'Unknown'}</td>
            <td>{st_weight:.4f}</td>
            <td>{bm_weight:.4f}</td>
            <td>{overweight:+.4f}</td>
        </tr>
        """
        )

    return f"""
    <table border="1" cellpadding="5" cellspacing="0" style="width:100%">
        <tr style="background-color:#f2f2f2">
            <th>行业代码</th>
            <th>策略权重</th>
            <th>基准权重</th>
            <th>超配权重</th>
        </tr>
        {''.join(rows)}
    </table>
    """


def _generate_alpha_table(alpha: dict) -> str:
    """生成 Alpha 分解表格。"""
    return f"""
    <table border="1" cellpadding="5" cellspacing="0" style="width:100%">
        <tr style="background-color:#f2f2f2">
            <th>指标</th>
            <th>值</th>
        </tr>
        <tr>
            <td>总超额收益</td>
            <td>{alpha.get('total_excess_return', 0):.4f}</td>
        </tr>
        <tr>
            <td>行业归因</td>
            <td>{alpha.get('industry_attribution', 0):.4f}</td>
        </tr>
        <tr>
            <td>选股 Alpha</td>
            <td>{alpha.get('security_selection_alpha', 0):.4f}</td>
        </tr>
        <tr>
            <td>Alpha 比率</td>
            <td>{alpha.get('alpha_ratio', 0):.4f}</td>
        </tr>
    </table>
    """


# HTML 模板
REPORT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>小市值策略因子分析报告</title>
    <style>
        body {
            font-family: "Microsoft YaHei", Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }
        h2 {
            color: #555;
            margin-top: 30px;
            margin-bottom: 15px;
            border-left: 4px solid #007bff;
            padding-left: 10px;
        }
        .summary {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 30px;
        }
        .summary-card {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #007bff;
        }
        .summary-card .label {
            font-size: 12px;
            color: #666;
            font-weight: bold;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        .summary-card .value {
            font-size: 24px;
            color: #007bff;
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background-color: white;
        }
        th {
            background-color: #f2f2f2;
            padding: 12px;
            text-align: left;
            font-weight: bold;
            color: #333;
            border: 1px solid #ddd;
        }
        td {
            padding: 10px 12px;
            border: 1px solid #ddd;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        tr:hover {
            background-color: #f0f0f0;
        }
        .timestamp {
            text-align: right;
            color: #999;
            font-size: 12px;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
        .section-note {
            color: #666;
            font-size: 12px;
            margin-top: 10px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 3px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 小市值策略因子分析报告</h1>

        <!-- IC 摘要 -->
        <h2>Rank IC 分析</h2>
        <div class="summary">
            <div class="summary-card">
                <div class="label">平均 IC</div>
                <div class="value">{{ avg_ic }}</div>
            </div>
            <div class="summary-card">
                <div class="label">IC 标准差</div>
                <div class="value">{{ ic_std }}</div>
            </div>
            <div class="summary-card">
                <div class="label">IC T-Stat</div>
                <div class="value">{{ ic_tstat }}</div>
            </div>
            <div class="summary-card">
                <div class="label">IC 样本数</div>
                <div class="value">{{ ic_count }}</div>
            </div>
        </div>
        <div class="section-note">
            ℹ️ IC（Information Coefficient）衡量市值因子与收益的秩相关系数。平均 IC > 0.1 表示因子具有预测能力。
        </div>

        <!-- IC 时间序列表 -->
        <h3>IC 时间序列</h3>
        {{ ic_table }}

        <!-- 五分组收益 -->
        <h2>五分组收益分析</h2>
        <div class="summary">
            <div class="summary-card">
                <div class="label">第1组超额收益</div>
                <div class="value">{{ group1_excess_return }}</div>
            </div>
            <div class="summary-card">
                <div class="label">单调性检验</div>
                <div class="value">{% if monotonicity %}✓ 通过{% else %}✗ 不通过{% endif %}</div>
            </div>
        </div>
        <div class="section-note">
            ℹ️ 按市值升序分为 5 组，第1组为最小市值组。单调性通过表示小市值溢价显著。
        </div>

        <h3>各分组收益对比</h3>
        {{ groups_table }}

        <!-- 因子暴露 -->
        <h2>因子暴露分析</h2>
        <div class="summary">
            <div class="summary-card">
                <div class="label">策略平均市值</div>
                <div class="value">{{ avg_market_cap }}</div>
            </div>
            <div class="summary-card">
                <div class="label">基准平均市值</div>
                <div class="value">{{ benchmark_avg_market_cap }}</div>
            </div>
        </div>
        <div class="section-note">
            ℹ️ 显示策略与全市场等权基准在行业、市值、流动性等维度的暴露差异。
        </div>

        <h3>行业权重对比</h3>
        {{ industry_table }}

        <!-- 行业中性 Alpha -->
        <h2>行业中性 Alpha 分解</h2>
        <div class="summary">
            <div class="summary-card">
                <div class="label">总超额收益</div>
                <div class="value">{{ total_excess_return }}</div>
            </div>
            <div class="summary-card">
                <div class="label">选股 Alpha</div>
                <div class="value">{{ security_alpha }}</div>
            </div>
            <div class="summary-card">
                <div class="label">Alpha 比率</div>
                <div class="value">{{ alpha_ratio }}</div>
            </div>
        </div>
        <div class="section-note">
            ℹ️ 分解公式：总超额收益 = 行业配置贡献 + 选股 Alpha。Alpha 比率越高表示选股能力越强。
        </div>

        <h3>Alpha 分解表</h3>
        {{ alpha_table }}

        <div class="timestamp">
            报告生成时间: {{ timestamp }}
        </div>
    </div>
</body>
</html>
"""
