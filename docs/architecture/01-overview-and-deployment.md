## 1. 架构概览

### 1.1 高层视图

系统可以按职能分为三大子系统：

1. **交易执行子系统（Execution Core）**
   - `bot.py`：交易主循环、技术指标、LLM 决策、风险控制、纸上撮合。
   - `hyperliquid_client.py`：Hyperliquid 实盘执行适配器。
2. **分析与可视化子系统（Analytics & UI）**
   - `dashboard.py`：基于 `data/` 的组合表现可视化。
   - `replay/`：构建静态回放站点，用于回顾历史决策。
3. **历史评估与工具子系统（Backtesting & Tools）**
   - `backtest.py`：历史数据回放与评估。
   - `scripts/`：重算组合状态、Docker 回测脚本、Hyperliquid smoke test 等。

所有子系统围绕统一的数据目录（默认 `data/` 与 `data-backtest/`）进行解耦：

- 交易执行负责 **写入** 状态与日志。
- 仪表盘与回放负责 **读取** 并可视化这些数据。
- 回测通过独立目录 **复用同一执行逻辑** 产出另一套数据，以供同样的可视化与分析管线使用。

### 1.2 部署形态

典型部署方式：

- 单 Docker 镜像 `tradebot`，内部包含：
  - Python 运行时与依赖包
  - 源代码（`bot.py`、`backtest.py`、`dashboard.py` 等）
- 常见运行模式：
  - 容器 1：运行 `bot.py` 进行纸上/实盘交易。
  - 容器 2：同一镜像运行 `streamlit run dashboard.py` 暴露 8501 端口。

```
+--------------------------+         +------------------------------+
|      tradebot 容器       |         |         tradebot 容器        |
|  (bot.py - Trading Loop) |         | (dashboard.py - Streamlit)  |
+------------+-------------+         +---------------+--------------+
             |                                               |
             | 读/写 CSV/JSON                               | 只读 CSV/JSON
             v                                               v
        主机 ./data 目录  <----------------------------------+
```

可选：本地直接运行 Python 脚本，数据目录仍为仓库下 `data/`。
