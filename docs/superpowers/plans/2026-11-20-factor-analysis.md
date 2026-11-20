# 阶段三：因子分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建小市值策略的因子分析模块，通过 IC、分组收益、暴露分析和行业中性 Alpha 评估策略的真实表现和超额收益来源。

**Architecture:** 
- 核心分析模块 (`FactorAnalyzer`) 计算 Rank IC、分组收益、因子暴露
- 报告生成器 (`AnalysisReport`) 输出 JSON 和离线 HTML
- 后端 API 端点集成回测结果和因子分析
- 前端可视化面板展示关键指标

**Tech Stack:** 
- pandas/numpy - 数据处理和统计计算
- scipy.stats - 秩相关和统计检验
- jinja2 - HTML 模板生成
- FastAPI - API 端点

**Spec:** 无独立设计文档，基于 README.md 中的阶段三需求和用户的方案 C 确认

## Global Constraints

- Python 3.10+
- 与现有 backtest.py 和 data.py 的接口保持一致
- 所有金融计算精确到分 (money())
- 文档与代码实时同步更新

## Review Focus

1. **IC 计算的时间对齐** - 信号日与持股期间的数据一致性，避免数据穿越
2. **分组权重计算** - 等权分组与实际执行的目标持仓映射关系
3. **行业分类** - 行业代码的准确性和缺失处理
4. **基准选择** - 全市场等权基准在缺失数据时的降级策略
5. **极端值处理** - 停牌/退市股票对 IC 和收益的影响

---

## File Structure

### 创建文件
```
backend/
├── factor_analysis.py          # 核心分析模块（400-500行）
│   ├── FactorAnalyzer          # 主分析类
│   ├── RankICResult            # IC 结果数据类
│   ├── GroupReturnsResult      # 分组结果数据类
│   └── ExposureResult          # 暴露结果数据类
│
├── reports.py                  # 报告生成器（300-400行）
│   ├── AnalysisReport          # 报告数据类
│   ├── HTMLReporter            # HTML 生成
│   └── templates/              # Jinja2 HTML 模板
│       └── factor_report.html
│
tests/
└── test_factor_analysis.py     # 单元测试（300-400行）

docs/
└── 因子分析说明.md              # 功能文档
```

### 修改文件
```
backend/app.py                  # 添加 POST /api/factor-analysis 端点
README.md                       # 更新阶段三进度和 API 文档
docs/更新总结.md                # 增加因子分析版本记录
```

---

## Task Decomposition

### Task 1: 核心数据类和 Rank IC 计算

**Files:**
- Create: `backend/factor_analysis.py`
- Test: `tests/test_factor_analysis.py`

**Interfaces:**
- Consumes: 
  - `backtest_result` (dict) 包含 equity/trades/orders 记录
  - `market_data` (dict[symbol, pd.DataFrame]) 日线行情数据
  
- Produces:
  ```python
  class FactorAnalyzer:
      def compute_rank_ic(
          self,
          signal_date: str,
          candidates: list[StockCandidate],  # 候选股票及市值
          returns: dict[str, float]  # {symbol: period_return}
      ) -> RankICResult
  
  @dataclass
  class RankICResult:
      signal_date: str
      ic: float                    # Spearman 秩相关系数
      p_value: float              # 统计显著性
      sample_size: int            # 有效样本数
      market_cap_ranks: dict[str, int]  # {symbol: rank}
  ```

- [ ] **Step 1: 写入失败测试 - 测试 compute_rank_ic 基本逻辑**

```python
def test_rank_ic_basic():
    """测试 Rank IC 计算的基本逻辑。"""
    from backend.factor_analysis import FactorAnalyzer
    from backend.selection import StockCandidate
    
    analyzer = FactorAnalyzer()
    
    # 构造测试候选（固定市值排序）
    candidates = [
        StockCandidate("SZ.000001", 1e8, 20e6, rank=1, percentile=0.2, close=10.0),
        StockCandidate("SZ.000002", 2e8, 20e6, rank=2, percentile=0.4, close=10.0),
        StockCandidate("SZ.000003", 3e8, 20e6, rank=3, percentile=0.6, close=10.0),
    ]
    
    # 构造收益（与市值反向，验证秩相关）
    returns = {
        "SZ.000001": 0.05,  # 最小市值，收益最高
        "SZ.000002": 0.03,
        "SZ.000003": 0.01,  # 最大市值，收益最低
    }
    
    result = analyzer.compute_rank_ic("2024-02-29", candidates, returns)
    
    assert result.ic < -0.5  # 负相关
    assert result.signal_date == "2024-02-29"
    assert result.sample_size == 3
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd D:\lgl\code\quant\strategy\small_cap_workbench
pytest tests/test_factor_analysis.py::test_rank_ic_basic -v
```

Expected: FAIL (FactorAnalyzer 未定义)

- [ ] **Step 3: 在 backend/factor_analysis.py 中实现 FactorAnalyzer 和 compute_rank_ic**

实现方式：
- 用 `scipy.stats.spearmanr()` 计算秩相关系数和 p-value
- 从 candidates 的 market_cap 字段提取市值排名
- 从 returns 字典提取对应的收益
- 处理缺失数据：剔除没有收益数据的股票，记录有效样本数

关键实现点：
```python
from scipy.stats import spearmanr
from dataclasses import dataclass

@dataclass
class RankICResult:
    signal_date: str
    ic: float
    p_value: float
    sample_size: int
    market_cap_ranks: dict[str, int]

class FactorAnalyzer:
    def compute_rank_ic(self, signal_date: str, candidates, returns):
        # 1. 构建市值排序数组（升序，最小市值 rank=1）
        mc_ranks = [(c.symbol, i+1) for i, c in enumerate(candidates)]
        
        # 2. 对应的收益数组（只包含有收益数据的）
        # 3. 用 spearmanr 计算秩相关
        # 4. 返回 RankICResult
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_factor_analysis.py::test_rank_ic_basic -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/factor_analysis.py tests/test_factor_analysis.py
git commit -m "feat(factor): implement Rank IC calculation"
```

---

### Task 2: 五分组收益计算

**Files:**
- Modify: `backend/factor_analysis.py`
- Modify: `tests/test_factor_analysis.py`

**Interfaces:**
- Consumes:
  - `candidates: list[StockCandidate]` 候选股票列表
  - `returns: dict[str, dict[str, float]]` 每个月末调仓日期的收益数据
  - `rebalance_dates: list[str]` 所有月末调仓日期

- Produces:
  ```python
  @dataclass
  class GroupReturnsResult:
      groups: dict[int, GroupStats]  # {group_id: stats}
      
  @dataclass
  class GroupStats:
      group_id: int                  # 1-5，1=最小市值
      avg_return: float              # 平均收益
      cumulative_return: float       # 累计收益
      symbols_count: int             # 组内股票数
      avg_market_cap: float          # 组内平均市值
      monotonicity_check: bool       # 是否单调递减
      group1_excess_return: float    # 第1组 vs 第5组的超额收益
  ```

- [ ] **Step 1: 写入测试 - 测试 5 分组的等权重分配和收益计算**

```python
def test_group_returns_basic():
    """测试五分组收益计算。"""
    from backend.factor_analysis import FactorAnalyzer
    from backend.selection import StockCandidate
    
    analyzer = FactorAnalyzer()
    
    # 10 只股票，市值升序，应分为 5 组，每组 2 只
    candidates = [
        StockCandidate(f"SZ.{str(i).zfill(6)}", float(i)*1e8, 20e6, 
                      rank=i+1, percentile=(i+1)*0.1, close=10.0)
        for i in range(10)
    ]
    
    # 所有股票同一个月的收益（模拟最小市值组收益最高）
    returns_by_group = {
        1: {c.symbol: 0.05 for c in candidates[0:2]},  # 组1: 5%
        2: {c.symbol: 0.04 for c in candidates[2:4]},  # 组2: 4%
        3: {c.symbol: 0.03 for c in candidates[4:6]},  # 组3: 3%
        4: {c.symbol: 0.02 for c in candidates[6:8]},  # 组4: 2%
        5: {c.symbol: 0.01 for c in candidates[8:10]}, # 组5: 1%
    }
    
    result = analyzer.compute_group_returns(candidates, returns_by_group)
    
    assert len(result.groups) == 5
    assert result.groups[1].avg_return > result.groups[5].avg_return  # 单调性
    assert result.groups[1].group1_excess_return == pytest.approx(0.04, abs=0.001)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_factor_analysis.py::test_group_returns_basic -v
```

Expected: FAIL (compute_group_returns 方法未定义)

- [ ] **Step 3: 在 FactorAnalyzer 中实现 compute_group_returns**

实现方式：
- 按 market_cap 升序排列候选股票
- 分成 5 个等权重组（每组 len(candidates) // 5 只）
- 对每组计算平均收益和累计收益
- 检验单调性（是否递减）
- 计算第1组 vs 第5组的超额收益

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_factor_analysis.py::test_group_returns_basic -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/factor_analysis.py tests/test_factor_analysis.py
git commit -m "feat(factor): implement quintile group returns analysis"
```

---

### Task 3: 行业暴露分析

**Files:**
- Modify: `backend/factor_analysis.py`
- Modify: `tests/test_factor_analysis.py`

**Interfaces:**
- Consumes:
  - `portfolio_weights: dict[str, float]` 策略持仓权重 {symbol: weight}
  - `benchmark_weights: dict[str, float]` 基准持仓权重（全市场等权）
  - `symbol_industry: dict[str, str]` 股票行业映射 {symbol: industry_code}

- Produces:
  ```python
  @dataclass
  class ExposureResult:
      strategy_industry_weights: dict[str, float]  # 策略行业权重
      benchmark_industry_weights: dict[str, float] # 基准行业权重
      industry_overweight: dict[str, float]        # 超配权重
      avg_market_cap: float                        # 策略平均市值
      benchmark_avg_market_cap: float              # 基准平均市值
      volatility: float                            # 策略波动率
      benchmark_volatility: float                  # 基准波动率
      avg_adv: float                               # 策略平均 ADV
      benchmark_avg_adv: float                     # 基准平均 ADV
  ```

- [ ] **Step 1: 写入测试 - 测试行业权重聚合和超配计算**

```python
def test_industry_exposure():
    """测试行业暴露分析。"""
    from backend.factor_analysis import FactorAnalyzer
    
    analyzer = FactorAnalyzer()
    
    # 策略持仓（5 只，都是制造业）
    portfolio_weights = {
        "SZ.000001": 0.2,
        "SZ.000002": 0.2,
        "SZ.000003": 0.2,
        "SZ.000004": 0.2,
        "SZ.000005": 0.2,
    }
    
    # 基准持仓（10 只，5 只制造业 + 5 只其他）
    benchmark_weights = {
        "SZ.000001": 0.1, "SZ.000002": 0.1, "SZ.000003": 0.1,
        "SZ.000004": 0.1, "SZ.000005": 0.1,  # 制造业
        "SH.600001": 0.1, "SH.600002": 0.1, "SH.600003": 0.1,
        "SH.600004": 0.1, "SH.600005": 0.1,  # 金融业
    }
    
    symbol_industry = {
        "SZ.000001": "C34", "SZ.000002": "C34", "SZ.000003": "C34",
        "SZ.000004": "C34", "SZ.000005": "C34",  # 制造业代码
        "SH.600001": "J66", "SH.600002": "J66", "SH.600003": "J66",
        "SH.600004": "J66", "SH.600005": "J66",  # 金融业代码
    }
    
    result = analyzer.compute_exposure(portfolio_weights, benchmark_weights, symbol_industry)
    
    # 策略 100% 制造业，基准 50% 制造业，所以超配 50%
    assert result.strategy_industry_weights["C34"] == pytest.approx(1.0)
    assert result.benchmark_industry_weights["C34"] == pytest.approx(0.5)
    assert result.industry_overweight["C34"] == pytest.approx(0.5)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_factor_analysis.py::test_industry_exposure -v
```

Expected: FAIL

- [ ] **Step 3: 在 FactorAnalyzer 中实现 compute_exposure**

实现方式：
- 按行业代码聚合策略和基准权重
- 计算超配权重差 = 策略权重 - 基准权重
- 如果缺少行业分类，用 "Unknown" 代替
- 计算平均市值：从 market_cap 字段取 weighted average
- 计算波动率：需要从历史收益计算 std
- 计算平均 ADV：从 adv20 字段取 weighted average

注意：ADV 和市值数据需要从回测中传入

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_factor_analysis.py::test_industry_exposure -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/factor_analysis.py tests/test_factor_analysis.py
git commit -m "feat(factor): implement industry exposure analysis"
```

---

### Task 4: 行业中性 Alpha 计算

**Files:**
- Modify: `backend/factor_analysis.py`
- Modify: `tests/test_factor_analysis.py`

**Interfaces:**
- Consumes:
  - `strategy_returns: float` 策略总收益
  - `benchmark_returns: float` 基准总收益
  - `industry_weights: dict[str, float]` 策略的行业权重
  - `industry_excess_returns: dict[str, float]` 每个行业的超额收益 {industry: excess_return}

- Produces:
  ```python
  @dataclass
  class AlphaResult:
      total_excess_return: float         # 策略 vs 基准的超额收益
      industry_attribution: float        # 行业配置贡献的超额收益
      security_selection_alpha: float    # 行业中性选股 Alpha
      alpha_ratio: float                 # Alpha / Total Excess Return
  ```

- [ ] **Step 1: 写入测试 - 测试行业中性 Alpha 归因分解**

```python
def test_industry_neutral_alpha():
    """测试行业中性 Alpha 计算。"""
    from backend.factor_analysis import FactorAnalyzer
    
    analyzer = FactorAnalyzer()
    
    # 假设策略总收益 10%，基准 8%，超额收益 2%
    strategy_returns = 0.10
    benchmark_returns = 0.08
    
    # 策略行业权重（100% 制造业）
    industry_weights = {"C34": 1.0}
    
    # 制造业超额收益 1%（策略制造业 12% vs 基准制造业 11%）
    industry_excess_returns = {"C34": 0.01}
    
    result = analyzer.compute_industry_neutral_alpha(
        strategy_returns, benchmark_returns, 
        industry_weights, industry_excess_returns
    )
    
    # 总超额收益 = 2%
    assert result.total_excess_return == pytest.approx(0.02)
    
    # 行业贡献 = 1% * 100% = 1%
    assert result.industry_attribution == pytest.approx(0.01)
    
    # 选股 Alpha = 2% - 1% = 1%
    assert result.security_selection_alpha == pytest.approx(0.01)
    
    # Alpha ratio = 1% / 2% = 50%
    assert result.alpha_ratio == pytest.approx(0.5)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_factor_analysis.py::test_industry_neutral_alpha -v
```

Expected: FAIL

- [ ] **Step 3: 在 FactorAnalyzer 中实现 compute_industry_neutral_alpha**

实现方式：
- 计算总超额收益 = strategy_returns - benchmark_returns
- 计算行业归因 = Σ(industry_weight * industry_excess_return)
- 计算选股 Alpha = 总超额收益 - 行业归因
- 计算 Alpha 比率 = 选股 Alpha / 总超额收益（避免除以零）

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_factor_analysis.py::test_industry_neutral_alpha -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/factor_analysis.py tests/test_factor_analysis.py
git commit -m "feat(factor): implement industry-neutral alpha decomposition"
```

---

### Task 5: 主分析接口和数据整合

**Files:**
- Modify: `backend/factor_analysis.py`

**Interfaces:**
- Consumes:
  - `backtest_result` (dict) 来自 backtest.py 的完整结果
  - `market_data` (dict[symbol, pd.DataFrame]) 历史行情

- Produces:
  ```python
  class FactorAnalyzer:
      def analyze_full(
          self,
          backtest_result: dict,
          market_data: dict[str, pd.DataFrame],
          symbol_industry: dict[str, str]
      ) -> dict
      # 返回：{
      #   "rank_ic_series": list[RankICResult],
      #   "group_returns": GroupReturnsResult,
      #   "exposure": ExposureResult,
      #   "alpha": AlphaResult,
      #   "summary": {...}
      # }
  ```

- [ ] **Step 1: 写入测试 - 测试完整分析流程**

```python
def test_analyze_full_integration():
    """测试完整因子分析流程。"""
    from backend.factor_analysis import FactorAnalyzer
    from tests.fixtures import create_sample_backtest_result, create_sample_market_data
    
    analyzer = FactorAnalyzer()
    
    # 使用 fixture 创建样本回测结果和行情数据
    backtest_result = create_sample_backtest_result()
    market_data = create_sample_market_data()
    symbol_industry = {s: "C34" for s in market_data.keys()}
    
    result = analyzer.analyze_full(backtest_result, market_data, symbol_industry)
    
    assert "rank_ic_series" in result
    assert "group_returns" in result
    assert "exposure" in result
    assert "alpha" in result
    assert len(result["rank_ic_series"]) > 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_factor_analysis.py::test_analyze_full_integration -v
```

Expected: FAIL

- [ ] **Step 3: 在 FactorAnalyzer 中实现 analyze_full**

实现方式：
- 从 backtest_result 提取：equity_history、trades、orders
- 遍历每个月末调仓日期
  - 获取该日期的候选股票和市值
  - 计算后续持股期间的收益（日级别）
  - 调用 compute_rank_ic
- 整个回测期计算 compute_group_returns
- 从 equity_history 提取策略权重和基准权重
- 调用 compute_exposure 和 compute_industry_neutral_alpha
- 聚合返回

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_factor_analysis.py::test_analyze_full_integration -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/factor_analysis.py tests/test_factor_analysis.py
git commit -m "feat(factor): implement full factor analysis workflow"
```

---

### Task 6: 报告生成器（JSON + HTML）

**Files:**
- Create: `backend/reports.py`
- Create: `backend/templates/factor_report.html`
- Modify: `tests/test_factor_analysis.py`

**Interfaces:**
- Consumes:
  - `analysis_result` (dict) 来自 FactorAnalyzer.analyze_full()

- Produces:
  ```python
  class AnalysisReport:
      def __init__(self, analysis_result: dict)
      def to_json() -> str                 # JSON 字符串
      def to_html() -> str                # HTML 字符串
  ```

- [ ] **Step 1: 写入测试 - 测试 JSON 和 HTML 生成**

```python
def test_report_generation():
    """测试报告生成。"""
    from backend.reports import AnalysisReport
    from tests.fixtures import create_sample_analysis_result
    
    result = create_sample_analysis_result()
    report = AnalysisReport(result)
    
    # 测试 JSON 生成
    json_str = report.to_json()
    json_obj = json.loads(json_str)
    assert "rank_ic_series" in json_obj
    assert "group_returns" in json_obj
    
    # 测试 HTML 生成
    html_str = report.to_html()
    assert "<html>" in html_str.lower()
    assert "因子分析" in html_str
    assert "Rank IC" in html_str
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_factor_analysis.py::test_report_generation -v
```

Expected: FAIL

- [ ] **Step 3: 在 backend/reports.py 中实现 AnalysisReport**

实现方式：
- `to_json()` - 使用 json.dumps() 序列化整个 analysis_result
- `to_html()` - 用 jinja2 渲染模板，传入分析结果数据

HTML 模板 (`backend/templates/factor_report.html`) 包含：
- 标题和时间戳
- Rank IC 时间序列图表（纯 HTML 表格）
- 五分组收益对比表
- 行业权重对比表
- Alpha 分解表

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_factor_analysis.py::test_report_generation -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/reports.py backend/templates/factor_report.html tests/test_factor_analysis.py
git commit -m "feat(reports): implement JSON and HTML report generation"
```

---

### Task 7: API 端点和集成

**Files:**
- Modify: `backend/app.py`
- Modify: `tests/test_factor_analysis.py` (添加集成测试)

**Interfaces:**
- Consumes: POST 请求
  ```python
  class FactorAnalysisRequest(BaseModel):
      experiment_id: str = Field(..., description="关联的回测实验ID")
      include_html_report: bool = Field(True, description="是否生成HTML报告")
  ```

- Produces: 
  ```python
  {
    "success": true,
    "analysis": {
      "rank_ic_series": [...],
      "group_returns": {...},
      "exposure": {...},
      "alpha": {...}
    },
    "report_url": "/outputs/{experiment_id}/factor_report.html"
  }
  ```

- [ ] **Step 1: 写入测试 - 测试 API 端点**

```python
def test_api_factor_analysis(test_client):
    """测试因子分析 API 端点。"""
    # 先运行一个回测获得 experiment_id
    backtest_result = test_client.post("/api/backtest", json={
        "start_date": "2023-01-01",
        "end_date": "2023-03-31",
        "initial_cash": 1000000,
        "target_stocks": 30,
        "stock_filter": "sample"
    })
    assert backtest_result.status_code == 200
    experiment_id = backtest_result.json()["experiment_id"]
    
    # 调用因子分析 API
    analysis_result = test_client.post("/api/factor-analysis", json={
        "experiment_id": experiment_id,
        "include_html_report": True
    })
    
    assert analysis_result.status_code == 200
    data = analysis_result.json()
    assert data["success"] == True
    assert "rank_ic_series" in data["analysis"]
    assert "report_url" in data
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_factor_analysis.py::test_api_factor_analysis -v
```

Expected: FAIL (端点未定义)

- [ ] **Step 3: 在 backend/app.py 中添加 POST /api/factor-analysis 端点**

实现步骤：
- 从 `experiment_id` 读取对应的回测结果 JSON
- 加载市场数据
- 创建 FactorAnalyzer 实例并调用 analyze_full()
- 创建 AnalysisReport 实例
- 生成 JSON 结果
- 如果 include_html_report=True，生成 HTML 报告并保存到 outputs/{experiment_id}/
- 返回 JSON 响应

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_factor_analysis.py::test_api_factor_analysis -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app.py tests/test_factor_analysis.py
git commit -m "feat(api): add POST /api/factor-analysis endpoint"
```

---

### Task 8: 完整单元测试覆盖

**Files:**
- Modify: `tests/test_factor_analysis.py` (添加更多测试用例)

**Interfaces:** (无新接口，仅测试现有接口)

- [ ] **Step 1: 添加边界条件测试**

添加以下测试用例：
- `test_rank_ic_with_missing_data()` - IC 计算时缺失收益数据
- `test_group_returns_insufficient_candidates()` - 候选股票少于 5 只
- `test_exposure_with_unknown_industry()` - 缺失行业分类
- `test_alpha_with_zero_excess_return()` - 无超额收益时的 Alpha 计算

```bash
pytest tests/test_factor_analysis.py -v
```

Expected: 所有测试通过，覆盖率 > 85%

- [ ] **Step 2: 运行所有测试**

```bash
pytest tests/test_factor_analysis.py -v --cov=backend.factor_analysis --cov-report=term-missing
```

Expected: PASS，覆盖率 > 85%

- [ ] **Step 3: 提交**

```bash
git add tests/test_factor_analysis.py
git commit -m "test: add comprehensive unit tests for factor analysis"
```

---

### Task 9: 文档更新

**Files:**
- Create: `docs/因子分析说明.md` (新文档，500-800行)
- Modify: `README.md` (更新阶段三进度)
- Modify: `docs/更新总结.md` (添加版本记录)

**Interfaces:** (无代码接口，纯文档)

- [ ] **Step 1: 创建因子分析功能文档**

`docs/因子分析说明.md` 应包含：

```markdown
# 因子分析模块

## 概述
- 模块目的：评估小市值策略的真实表现和超额收益来源
- 核心指标：Rank IC、分组收益、因子暴露、行业中性 Alpha

## 1. Rank IC 时间序列

### 计算方法
- 每个月末调仓日期，计算市值因子与后续持股期间收益的秩相关
- 日级别 IC：用调仓日的收盘价作为市值参考，计算次日至下一月末的日收益秩相关

### 解读
- IC 值范围 [-1, 1]，越大越好
- t-stat = IC / std(IC_series)，t-stat > 2 表示统计显著
- IC < 0 表示小市值反向预测收益

### API 使用
```python
analyzer = FactorAnalyzer()
ic_result = analyzer.compute_rank_ic(signal_date, candidates, returns)
print(f"IC: {ic_result.ic:.4f}, p-value: {ic_result.p_value:.4f}")
```

## 2. 五分组收益分析

### 分组方法
- 按市值升序排列所有候选股票
- 平均分成 5 组，每组等权重

### 关键指标
- 平均收益：每组的平均收益率
- 单调性：组 1 收益是否 > 组 2 > ... > 组 5
- 超额收益：组 1 vs 组 5 的收益差异

### 解读
- 单调性递减表示小市值溢价显著
- 第1组超额收益越大，策略效果越好

## 3. 因子暴露分析

### 三大维度
- 行业权重对比：策略 vs 全市场等权基准
- 波动率对比：策略波动率 vs 基准波动率
- 流动性对比：策略平均 ADV vs 基准平均 ADV

### 解读
- 行业超配：表示集中度高，单因子暴露强
- 波动率高：小市值股票本身波动大

## 4. 行业中性 Alpha

### 分解公式
```
总超额收益 = 行业配置贡献 + 选股 Alpha

行业配置贡献 = Σ(行业权重 × 行业超额收益)
选股 Alpha = 总超额收益 - 行业配置贡献
```

### 解读
- Alpha > 0 表示真实的选股能力
- Alpha ratio = 选股 Alpha / 总超额收益，越高越好

## API 使用示例

### 运行完整因子分析
```bash
curl -X POST http://127.0.0.1:8001/api/factor-analysis \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_id": "abc123",
    "include_html_report": true
  }'
```

### 响应示例
```json
{
  "success": true,
  "analysis": {
    "rank_ic_series": [
      {"signal_date": "2023-01-31", "ic": 0.15, "p_value": 0.08},
      {"signal_date": "2023-02-28", "ic": 0.22, "p_value": 0.03}
    ],
    "group_returns": {
      "groups": {
        "1": {"avg_return": 0.05, "cumulative_return": 0.65},
        ...
      }
    },
    "exposure": {...},
    "alpha": {...}
  },
  "report_url": "/outputs/abc123/factor_report.html"
}
```

## 常见问题

Q: IC 计算时包含停牌股票吗？
A: 不包含。缺失收益数据的股票会被剔除，样本数会相应减少。

Q: 分组时如何处理候选不足 5 组的情况？
A: 如果候选少于 5 只，则按实际数量分组。

Q: 基准权重如何计算？
A: 全市场等权，即每只股票权重 = 1 / 全市场股票数。
```

- [ ] **Step 2: 更新 README.md**

在 README.md 中：
- 将阶段三的所有 `[ ]` 改为 `[x]`
- 更新"当前状态"部分，标记因子分析为✅完成
- 在模块概览表中添加因子分析模块的行
- 更新快速开始中的 API 接口示例

- [ ] **Step 3: 更新 docs/更新总结.md**

添加新版本记录：
```markdown
## v1.1.0 - 因子分析

**发布日期**: 2026-11-20

### 新增功能
- 阶段三因子分析模块实现
  - Rank IC 时间序列分析
  - 五分组收益对比
  - 行业波动流动性暴露
  - 行业中性 Alpha 分解
- 后端 API 端点 POST /api/factor-analysis
- HTML 离线报告生成
- 完整的单元测试和集成测试

### 文件变更
- 新增: backend/factor_analysis.py (500+ 行)
- 新增: backend/reports.py (300+ 行)
- 新增: backend/templates/factor_report.html
- 新增: docs/因子分析说明.md
- 修改: backend/app.py (添加 API 端点)
- 修改: tests/test_factor_analysis.py (新增 20+ 测试)
```

- [ ] **Step 4: 验证文档可读性**

```bash
# 检查 Markdown 格式
cd D:\lgl\code\quant\strategy\small_cap_workbench
cat docs/因子分析说明.md | head -50
```

- [ ] **Step 5: 提交**

```bash
git add docs/因子分析说明.md README.md docs/更新总结.md
git commit -m "docs: add factor analysis documentation and update version"
```

---

## Review Focus Verification

以下是规范中最可能出现的 5 个问题，每个都有对应的测试验证：

| 风险 | 验证测试 |
|------|---------|
| **IC 计算的数据穿越** | `test_rank_ic_basic()` - 验证市值在信号日、收益在后续期间 |
| **分组权重与实际持仓偏差** | `test_group_returns_basic()` - 验证等权分组与回测一致性 |
| **行业分类缺失导致崩溃** | `test_industry_exposure()` - 处理未知行业代码 |
| **基准权重计算错误** | `test_analyze_full_integration()` - 全流程验证基准与策略对比 |
| **极端值（停牌/退市）污染结果** | `test_rank_ic_with_missing_data()` - 缺失数据处理 |

---

## Execution Notes

- 所有任务按顺序执行，Task 1 完成后再进行 Task 2，以保证接口一致性
- 每个 Task 都包含"运行测试"验证失败，这是重要的 TDD 步骤，不可跳过
- 代码提交频率：每个 Task 一次，共 9 次提交
- 文档更新（Task 9）在所有代码完成后统一进行
- 估计总耗时：6-8 小时（包括测试和文档）
