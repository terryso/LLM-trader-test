# DeepSeek Paper Trading Bot 系统架构说明（反向工程草稿）

> 本文档基于现有代码与 README 反向整理，描述当前系统的组件划分、数据流与外部依赖，为后续演进与重构提供参考。

> 当前单文件架构说明已根据 BMAD 架构模板思路拆分为一组分片文档，位于 `docs/architecture/` 目录中。本文件作为入口与总导航。

## 文档迁移说明

本仓库原始的 `docs/architecture.md` 内容已按章节拆分为多个 Markdown 文件，以便：

- 更好地被 BMAD 工作流（如 Architecture、Document Project）按「sharded architecture」形式消费。
- 支持后续针对不同章节做增量更新和细粒度评审。
- 让其他代理（例如 code-review、implementation-readiness）可以只读取相关部分。

原有内容已完整迁移，无语义删减。

## 快速导航

- [架构主索引（推荐阅读起点）](./architecture/index.md)
- [1. 架构概览与部署](./architecture/01-overview-and-deployment.md)
- [2. 组件视图](./architecture/02-components.md)
- [3. 数据流](./architecture/03-data-flow.md)
- [4. 外部依赖与集成点](./architecture/04-integrations.md)
- [5. 可扩展性与演进建议](./architecture/05-evolution.md)
 - [6. 项目结构与 PRD 映射](./architecture/06-project-structure-and-mapping.md)
 - [7. 实现模式与一致性规则](./architecture/07-implementation-patterns.md)
