## 3. 数据流

### 3.1 实时交易路径

1. **行情与状态输入**：
   - Binance REST API → K 线数据
   - 本地 `portfolio_state` / `trade_history` → 当前仓位与历史表现
2. **特征与 Prompt 构建**：
   - 技术指标计算（EMA/RSI/MACD/ATR 等）。
   - 组合状态与风险参数 → 统一整理到 Prompt 上下文中。
3. **LLM 决策**：
   - 通过 OpenRouter 调用 DeepSeek，并获得 JSON 决策。
4. **本地校验与执行**：
   - Bot 校验 JSON 合约约束（结构与数值范围）。
   - 纸上路径：更新内存状态与 CSV/JSON。
   - 实盘路径：调用 HyperliquidTradingClient 下单并挂 SL/TP。
5. **输出与可视化**：
   - CSV/JSON → Streamlit 仪表盘 → 用户界面。
   - CSV/JSON → Replay 站点。

### 3.2 回测路径

1. **配置与数据准备**：
   - 通过环境变量描述回测时间段、间隔与 LLM 设置。
   - Binance K 线 → `data-backtest/cache/`。
2. **执行与日志**：
   - HistoricalBinanceClient 替换 `bot` 中的行情来源。
   - 其他流程与实时交易类似，但数据输出到 `data-backtest/run-*/`。
3. **分析与复用**：
   - 仪表盘或外部工具指向回测目录进行表现分析。
