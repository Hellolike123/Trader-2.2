# 📊 a-stock-data 对 Trader 2.3 系统的价值与接入方案评估

> **评估时间**：2026-05-28
> **目标项目**：[simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) (V3.1)
> **当前系统**：Trader 2.3

`simonlin1212/a-stock-data` 是一套专为 AI 编程助手（如 Claude Code, Codex, Gemini）优化设计的零依赖、轻量化 A 股数据获取引擎。经过深度代码审计和与我们当前 codebase（`Trader 2.3`）的对比，结论是：**它对我们极有帮助，能以极低的成本填补我们当前在「估值一致预期、题材催化归因、筹码集中度、风险预警」等关键维度上的空白。**

---

## 一、 核心价值：它能帮我们补充什么？

当前 `Trader 2.3` 拥有行业顶尖的**量化技术面分析层**（缠论、威科夫、筹码分布、HMM大势、ATR波动率等）和**多源热备行情层**（`mootdx` + `Tencent` + `Sina`）。

然而，在**投研深度、资金情绪和催化剂分析**上，我们存在几大空白。`a-stock-data` 的集成能完美补足这些短板：

| 维度 | Trader 2.3 当前现状 | `a-stock-data` 提供的增量价值 | 对交易决策的具体帮助 |
| :--- | :--- | :--- | :--- |
| **题材催化归因** | ❌ 仅通过均线/MACD等技术指标判断走强，不知道「为什么涨」 | **同花顺强势股题材归因** (`ths_hot_reason`) | **识别主线与龙头**：直接获取编辑部运营的题材标签（如「人形机器人/降本催化」），判断个股是跟风还是主线龙头，过滤无题材杂音。 |
| **基本面一致预期** | ❌ 仅有静态财务快照，缺乏机构未来预测，无法计算 PEG 或动态估值消化 | **同花顺一致预期 EPS** (`ths_eps_forecast`) + **东财研报预测** (`eastmoney_reports`) | **过滤伪成长股**：结合当前股价与机构一致预期的未来 2 年 EPS 增速计算 PEG，一票否决业绩暴雷或无机构覆盖的小盘垃圾股。 |
| **高频筹码集中度** | ⚠️ `chip_distribution.py` 通过日线换手进行数学估算，无法校准真实的持股结构 | **东财股东户数变动** (`RPT_F10_EH_FREEHOLDER_NUMBER`) | **验证机构建仓/派发**：股东户数环比减少意味着筹码流向主力（筹码集中），股东户数暴增代表筹码派发给散户。这是技术面筹码分布的最强外部验证器！ |
| **资金与杠杆面** | ❌ 缺乏对杠杆资金、大宗交易、龙虎榜游资的定量跟踪 | **两融明细** + **大宗交易** + **龙虎榜明细** + **分钟级资金流** | **主力追踪**：融资盘大幅流入表明杠杆散户或激进游资入场；龙虎榜顶级营业部与机构席位共振可显著提升突破信号置信度。 |
| **风险管理预警** | ❌ 缺乏前瞻性的筹码供给冲击预警 | **未来90天限售解禁日历** (`RPT_LSHJ_DECLEAR`) | **避开高危雷区**：若个股在未来 15 天内面临占流通股 10% 以上的大额解禁，决策融合层直接一票否决低吸或突破买入，规避闪崩。 |

---

## 二、 模块级接入方案设计

为了保持 `Trader 2.3` 高度松耦合的优雅架构，我们不应直接修改底层的 `light_data.py`，而是采用**“服务层解耦注入”**的形式来无缝接进来。

### 1. 接入路径：新增 `ExtendDataProvider`

我们在 `02-共享模块-shared/trader_shared/` 下创建一个名为 `extend_data.py` 的全新模块，将 `a-stock-data` 的核心无依赖 HTTP API 封装进去。

```
02-共享模块-shared/
├── 01-行情数据-market-data/
│   └── light_data.py (保持不变，专注行情HA)
├── trader_shared/
│   ├── data_provider.py (核心抽象)
│   ├── extend_data.py 👈 [NEW] 专门存放东财/同花顺等高阶投研 HTTP API
│   └── chip_distribution.py
```

### 2. 代码级集成：`extend_data.py` 骨架实现

由于 `a-stock-data` 已彻底移除了对 `akshare` 的依赖，全部接口改用原生 `requests`，我们可以将其核心代码完美提取并封装：

```python
# file:///Users/like/Downloads/项目/Trader 2.2 /02-共享模块-shared/trader_shared/extend_data.py
import requests
import pandas as pd
from io import StringIO
import time

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def eastmoney_datacenter(report_name: str, filter_str: str = "", page_size: int = 10, sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心接口封装"""
    params = {
        "reportName": report_name, "columns": "ALL",
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    try:
        r = requests.get(DATACENTER_URL, params=params, headers={"User-Agent": UA}, timeout=10)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception:
        pass
    return []

class ExtendDataProvider:
    """高阶投研数据提供器"""
    
    @staticmethod
    def get_shareholder_trend(code: str) -> dict:
        """获取最新股东户数变化情况"""
        data = eastmoney_datacenter(
            report_name="RPT_F10_EH_FREEHOLDER_NUMBER",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=4,
            sort_columns="HOLD_NOTICE_DATE"
        )
        if not data:
            return {"status": "数据不足", "change_pct": 0.0}
        
        # 计算环比变化
        try:
            latest = float(data[0].get("HOLDER_NUM", 0))
            prev = float(data[1].get("HOLDER_NUM", 0))
            change = (latest - prev) / prev * 100 if prev > 0 else 0.0
            return {
                "latest_notice_date": data[0].get("HOLD_NOTICE_DATE", "")[:10],
                "latest_holder_num": latest,
                "change_pct": round(change, 2),
                "status": "筹码集中" if change < 0 else "筹码松散" if change > 0 else "持平"
            }
        except Exception:
            return {"status": "解析失败", "change_pct": 0.0}

    @staticmethod
    def get_ths_consensus_eps(code: str) -> pd.DataFrame:
        """获取同花顺机构一致预期"""
        url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
        headers = {"User-Agent": UA, "Referer": "https://basic.10jqka.com.cn/"}
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.encoding = "gbk"
            dfs = pd.read_html(StringIO(r.text))
            for df in dfs:
                cols = [str(c) for c in df.columns]
                if any("每股收益" in c or "均值" in c for c in cols):
                    return df
        except Exception:
            pass
        return pd.DataFrame()

    @staticmethod
    def get_upcoming_unlocks(code: str) -> list[dict]:
        """查询个股未来 90 天待解禁信息"""
        data = eastmoney_datacenter(
            report_name="RPT_LSHJ_DECLEAR",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=5,
            sort_columns="FREE_DATE"
        )
        unlocks = []
        now = time.strftime("%Y-%m-%d")
        for row in data:
            free_date = row.get("FREE_DATE", "")[:10]
            if free_date >= now:
                unlocks.append({
                    "date": free_date,
                    "ratio": round(float(row.get("FREE_RATIO", 0)), 2),
                    "amount_wan": round(float(row.get("FREE_SHARES", 0)) / 10000, 2)
                })
        return unlocks
```

---

## 三、 三大应用场景：如何用它增强系统？

接入了这些高维度数据后，我们可以在 `Trader 2.3` 中实现极具杀伤力的增量功能：

### 📈 场景一：升级 `run_analysis.py` 报告面板（直观呈现）
在手机端 analysis 报告中，直接呈现「题材催化剂」与「筹码集中度」，让报告不仅有**骨架（缠论/威科夫价位）**，更有**灵魂（题材与基本面预估）**。

#### 💡 报告排版增强示意：
```markdown
分析报告 — 宁德时代（300750）

现价：185.20元（+2.30%）
MA5：182.10|MA10：180.50|MA20：178.20｜ATR 5.12 (3%)
提示：未来 15 天有大额解禁风险 (占流通股 8.2%) ⚠️

🔥 题材与共识
  · 主线题材：锂电池龙头｜固态电池突破催化 (同花顺题材)
  · 机构评级：买入 (24家覆盖)｜未来两年预期 EPS 增速 +25% (同花顺一致预期)
  · 筹码集中度：最新股东户数环比 -4.2% (筹码持续向机构集中) 🚀

🌍 中证1000
...
```

### 🧠 场景二：升级智能决策融合层 (`fusion_core.py`)
利用大宗交易、股东户数、一致预期在 `fusion_core.py` 中引入**「风控一票否决」**与**「信号乘数增强」**机制：

```python
# 伪代码：在决策融合层中动态消费高阶投研数据
def adjust_fusion_weights(base_action, confidence, code):
    # 1. 限售解禁风控 (一票否决)
    unlocks = ExtendDataProvider.get_upcoming_unlocks(code)
    for u in unlocks:
        if days_between(u["date"], today) <= 15 and u["ratio"] >= 5.0:
            # 15天内有超过 5% 的筹码解禁抛售压力，强制将“试探买”或“增持”降级为“观望”
            return "空仓/避开解禁期", 0.0
            
    # 2. 股东户数筹码验证 (置信度乘数)
    sh_trend = ExtendDataProvider.get_shareholder_trend(code)
    if sh_trend["status"] == "筹码集中" and base_action == "半仓试 (多方主导)":
        confidence *= 1.2  # 机构建仓期 + 缠论转强共振，大幅调高置信度！
        
    return base_action, confidence
```

### 🎯 场景三：选股池全生命周期管理 (`trader-pool`)
在 `trader-pool rank`（池内股票排序）中，目前仅能根据缠论结构和 HMM 大盘环境排序。有了新数据后，我们可以引入 **「PEG + 筹码集中度」** 综合评分模型，实现真正的**基本面排雷 + 资金面共振 + 技术面入场**的完美闭关。
