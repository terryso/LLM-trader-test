# DeepSeek Paper Trading Bot 系统架构说明（反向工程草稿）

## Executive Summary

本文档基于现有代码与 README 反向整理，描述当前系统的组件划分、数据流与外部依赖，为后续演进与重构提供参考。

当前仓库实现的是一个基于 DeepSeek 的加密货币交易机器人，围绕交易执行、可视化与回测三个子系统构建，并通过统一的数据目录解耦，使实时交易、历史回测与数据分析共享同一套逻辑与数据结构。

## 决策总览（Decision Summary）

| Category | Decision | Version | Rationale |
| -------- | -------- | ------- | --------- |
| Runtime | 使用 Python 3.13.3 作为统一运行时 | 3.13.3 | 与 Docker 基础镜像一致（`python:3.13.3-slim`），便于在本地与容器环境保持行为一致。 |
| Data Persistence | 以 `data/` / `data-backtest/` 下的 CSV/JSON 作为主持久化层 | - | 对于个人/小团队实验场景，文件存储足够简单透明，利于回溯与调试；未来可按数据量迁移至数据库。 |
| Trading Architecture | 单进程循环 + 依赖注入式回测（HistoricalBinanceClient） | - | 保持实现简单，复用一套指标/决策/执行逻辑于 live 与 backtest，降低维护成本。 |
| Live Execution | 默认纸上交易，可选 Hyperliquid 实盘（通过 `hyperliquid_client.py` 适配） | hyperliquid-python-sdk >=0.9.0 | 将所有实盘细节封装在适配层，Bot 只感知抽象接口，便于在未来替换执行端。 |
| Visualization | 使用 Streamlit 仪表盘展示组合表现 | streamlit==1.38.0 | 利用成熟的可视化框架快速搭建监控界面，而无需手工写前端。 |
| LLM Provider | 默认使用 OpenRouter → DeepSeek Chat V3.1 | deepseek/deepseek-chat-v3.1 | 通过 OpenRouter 统一接入，便于将来切换/对比不同模型；模型标注在环境变量与 PRD 中。 |
| Libraries | 交易与数据处理依赖 python-binance、pandas、numpy 等 | 见 `requirements.txt` | 选用成熟生态中的主流库，优先稳定性与社区支持（详见实现模式章节的版本列表）。 |

> 详细的项目结构与 PRD 映射见：`06-project-structure-and-mapping.md`；实现模式与版本策略见：`07-implementation-patterns.md`。

## 文档结构

- [1. 架构概览与部署](./01-overview-and-deployment.md)
- [2. 组件视图](./02-components.md)
- [3. 数据流](./03-data-flow.md)
- [4. 外部依赖与集成点](./04-integrations.md)
- [5. 可扩展性与演进建议](./05-evolution.md)
- [6. 项目结构与 PRD 映射](./06-project-structure-and-mapping.md)
- [7. 实现模式与一致性规则](./07-implementation-patterns.md)
