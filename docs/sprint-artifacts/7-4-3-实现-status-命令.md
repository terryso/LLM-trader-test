# Story 7.4.3: 实现 status 命令
 
Status: done
 
## Story

As a user,
I want to check current risk control status via Telegram,
so that I can monitor the bot's risk state and decide when to intervene.

## Acceptance Criteria

1. **AC1 – /status 返回完整风控快照（对齐 Epic 7.4.3，PRD FR1–FR4, FR19–FR21）**  
   - 在已正确配置 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`、且 Bot 正常运行时：  
     - 当收到来自授权 Chat 的 `/status` 命令：  
       - 从当前 `RiskControlState` 与组合状态中读取以下字段：  
         - Kill-Switch 状态：`kill_switch_active`、`kill_switch_reason`、`kill_switch_triggered_at`；  
         - 每日亏损状态：`daily_loss_pct`、`daily_start_equity`、`daily_start_date`、`daily_loss_triggered`；  
         - 每日亏损限制阈值：来源于 `DAILY_LOSS_LIMIT_PCT` 配置；  
         - 当前持仓数量：基于现有持仓结构统计；  
         - 当前总权益：与 PRD / 仪表盘使用的权益定义保持一致。  
       - 返回一条结构化 Markdown 文本，清晰展示上述字段，且不会抛出异常。  

2. **AC2 – 文案与格式（对齐 PRD「成功标准」「Telegram 命令集成」）**  
   - `/status` 回复遵循以下格式约束：  
     - 使用带 emoji 的标题行，例如：`📊 *风控状态*`；  
     - 使用粗体标签 + 数值的形式展示关键字段（Kill-Switch、每日亏损、阈值、持仓数量、当前权益）；  
     - 当 Kill-Switch 激活或每日亏损限制已触发时，在文案中清晰标注风险状态（如 `🔴 已暂停` / `⚠️ 日亏限制已触发`）；  
     - 对数值字段（亏损百分比、阈值、权益）使用固定小数位展示（例如亏损与阈值保留 2 位小数，权益保留 2 位小数），与现有通知文案保持一致风格。  
   - 当 Bot 未启用风控（`RISK_CONTROL_ENABLED=false`）或关键字段缺失时：  
     - `/status` 回复中需明确提示「风控系统未启用或状态不可用」，而不是返回误导性数值。  

3. **AC3 – 安全性与健壮性（对齐 PRD FR22–FR24, NFR3–NFR6）**  
   - 仅当命令来自配置的 `TELEGRAM_CHAT_ID` 时才返回状态：  
     - 其它 Chat ID 的 `/status` 命令被静默丢弃，并记录 `WARNING` 日志（沿用 7.4.1 行为）；  
   - `/status` 命令执行过程中：  
     - 不会修改任何风控状态字段（只读）；  
     - 网络错误或 Telegram 回复失败不会影响本地风控逻辑，仅记录 `WARNING/ERROR` 日志；  
     - 任意异常都不会中断 `_run_iteration()`，最多导致本轮 `/status` 调用失败。  

4. **AC4 – 日志与审计（对齐 PRD FR19–FR21）**  
   - 每次成功处理 `/status` 命令时：  
     - 在日志中记录一条结构化记录，至少包含：`command="status"`、`chat_id`、`kill_switch_active`、`daily_loss_pct`、`daily_loss_triggered`、`equity` 等关键字段；  
     - 在 `ai_decisions.csv` 或等价审计通道中可选记录一条 `action="RISK_CONTROL"` 的审计事件（例如 `detail="status via telegram"`），与 7.4.2 中 `/kill`、`/resume` 的审计事件保持一致风格。  
   - 当 `/status` 命令处理失败（例如内部异常）时：  
     - 记录 `ERROR` 级别日志，包含异常简要信息；  
     - 可返回一条通用错误提示给用户（例如「暂时无法获取风控状态，请稍后重试」），不泄露敏感内部细节。  

5. **AC5 – 单元测试与回归（对齐 Epic 7.4.3、PRD 成功标准）**  
   - 在 `tests/test_notifications_telegram_commands.py` 或等价测试文件中新增/扩展测试用例，至少覆盖：  
     - Kill-Switch 未激活、每日亏损未触发时 `/status` 文案的正常路径；  
     - Kill-Switch 激活、每日亏损限制已触发时 `/status` 文案中的状态与数值展示；  
     - 风控关闭或状态无效时 `/status` 文案中的降级提示；  
     - 未授权 `chat_id` 下 `/status` 命令不会返回内容且仅记录日志；  
     - `/status` 处理过程中发生异常时不会中断其他命令或交易循环。  
   - 运行 `./scripts/run_tests.sh` 时，所有既有测试与本 Story 新增测试均通过。

## Tasks / Subtasks
 
- [x] **Task 1 – 设计 /status 命令处理接口与返回格式（AC1, AC2）**  
  - [x] 1.1 在现有命令处理入口（例如 `process_telegram_commands` 或 `handle_command`）中增加对 `command == "status"` 的分支。  
  - [x] 1.2 设计一个专门的 `handle_status_command(...)` helper 或等价封装：从 `RiskControlState`、当前持仓与权益中汇总状态，并返回 Markdown 字符串。  
  - [x] 1.3 明确 `/status` 文案模板与数值格式规范，确保与 PRD 与前序通知文案风格一致。  
 
- [x] **Task 2 – 集成到命令处理与主循环（AC1, AC3）**  
  - [x] 2.1 在 `notifications/telegram_commands.py` 中复用 7.4.1/7.4.2 已有的命令分发与 chat 过滤逻辑，为 `/status` 命令挂接处理函数。  
  - [x] 2.2 在 `bot.py` 的 `_run_iteration()` 或等价调用链中，确保 `/status` 命令的执行不改变既有风控与交易生命周期，仅作为只读查询。  
  - [x] 2.3 为 `/status` 路径补充必要的错误捕获与日志记录，遵循 7.4.1/7.4.2 的错误处理模式。  
 
- [x] **Task 3 – 日志与审计集成（AC4）**  
  - [x] 3.1 在 `/status` 处理路径中添加结构化日志，字段与 `/kill` / `/resume` 的风险事件日志保持兼容，便于统一检索。  
  - [x] 3.2 视需要在 `ai_decisions.csv` 或等价审计通道中记录 `RISK_CONTROL` 类型事件，并确保不会干扰现有决策记录格式。  
 
- [x] **Task 4 – 单元测试与回归（AC5）**  
  - [x] 4.1 在 `tests/test_notifications_telegram_commands.py` 中新增 `/status` 相关测试用例，覆盖正常场景与异常场景。  
  - [x] 4.2 使用 fake / mock 的 `RiskControlState`、持仓与权益数据，验证不同状态组合下 `/status` 文案输出是否正确。  
  - [x] 4.3 运行 `./scripts/run_tests.sh`，确保全部测试通过，并在 Change Log 中记录一次成功运行（由后续 Dev Story 更新）。  

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.4: Telegram 命令集成** 的第三个实现 Story，对应 `sprint-status.yaml` 中的 key：`7-4-3-实现-status-命令`。  
- 需求主要来源：  
  - Epic 文档 `docs/epic-risk-control-enhancement.md` 中 **Story 7.4.3: 实现 /status 命令** 的拆解：  
    - 要求 `/status` 命令汇总 Kill-Switch、每日亏损、阈值、持仓数量与当前权益等信息；  
    - 给出了 `handle_status_command()` 示例，返回一段结构化 Markdown 文本。[Source: docs/epic-risk-control-enhancement.md#Story-7.4.3-实现-status-命令]  
  - PRD 文档 `docs/prd-risk-control-enhancement.md` 中：  
    - **FR1–FR4** 定义了全局风控状态 `RiskControlState` 的字段及持久化；  
    - **FR12–FR18** 定义了每日亏损限制与相关字段；  
    - **FR19–FR21** 明确要求通过 `/status` 命令查看当前风控状态并记录日志/审计。[Source: docs/prd-risk-control-enhancement.md#风控状态管理]  
  - `docs/epics.md` 中 **Epic 7.4: Telegram 命令集成（Post-MVP）** 的范围说明：  
    - 本 Epic 负责为 Kill-Switch、每日亏损限制等能力提供远程控制入口；  
    - 7.4.3 关注「可观测性」——向用户暴露当前风险状态，而不改变状态本身。[Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]
- 与前序 Stories 的关系：  
  - Epic 7.1 / 7.2 / 7.3 已提供 `RiskControlState`、Kill-Switch 激活/解除、每日亏损限制与通知通路；  
  - Story 7.4.1 实现命令接收与解析；Story 7.4.2 实现 `/kill` 与 `/resume` 命令及其日志/审计逻辑；  
  - 本 Story 在此基础上，为现有风控功能补充「查询接口」，完成 PRD FR21 所描述的 `/status` 能力。

### Architecture & Implementation Constraints

- **模块边界与职责：**  
  - `notifications/telegram_commands.py`：  
    - 继续负责命令接收、解析与分发；本 Story 在其中扩展 `/status` 分支及对应处理 helper；  
    - 复用已有的 `TelegramCommand` 数据结构与 `TelegramCommandHandler` 轮询逻辑。  
  - `notifications/telegram.py`：  
    - 仍专注于发送通知，本 Story 仅在需要发送 `/status` 回复时复用其发送 helper，不在此处写业务逻辑。  
  - `core/risk_control.py` / `core/state.py`：  
    - 提供 `RiskControlState` 与组合状态读取能力；`/status` 只读这些状态，不进行修改。  
  - `bot.py`：  
    - 继续作为主循环装配点，通过已有的 `poll_telegram_commands()` + 命令处理入口承载 `/status` 命令链路，而不在 `_run_iteration()` 中内联实现状态字符串拼接。  

- **一致性与错误处理：**  
  - 日志与错误处理风格对齐 Story 7.4.1 / 7.4.2：使用 `WARNING/ERROR` 级别，避免静默失败，并保持统一前缀便于 grep。  
  - `/status` 命令必须在 Kill-Switch 激活与否、每日亏损是否触发的所有组合下返回**自洽**的状态描述，不允许产生互相矛盾字段。  
  - 本 Story 不引入新的持久化字段或 CSV 列，所有新增信息仅通过 Telegram 文案与日志暴露，避免破坏现有数据 schema。

### Project Structure Notes

- 预期主要涉及文件（以实际实现为准）：  
  - `notifications/telegram_commands.py` —— 在已有命令处理框架下增加 `/status` 分支与处理函数；  
  - `notifications/telegram.py` —— 复用发送 helper，将 `/status` 文案发送给用户；  
  - `core/risk_control.py` / `core/state.py` —— 提供风控状态与组合状态读取接口；  
  - `bot.py` —— 维持命令轮询与分发调用顺序，不直接内联 `/status` 业务逻辑；  
  - `tests/test_notifications_telegram_commands.py` —— 为 `/status` 命令新增/扩展测试用例。  
- 实现需继续遵守 `docs/architecture/06-project-structure-and-mapping.md` 与 `docs/architecture/07-implementation-patterns.md` 中关于分层、日志、测试与外部服务集成的约定。

### Learnings from Previous Story

- **前一 Story:** 根据 `sprint-status.yaml` 的顺序，上一条已完成的 Story 是 `7-4-2-实现-kill-和-resume-命令`（状态为 `done`，详见 `docs/sprint-artifacts/7-4-2-实现-kill-和-resume-命令.md`）。  
- **可复用能力与约束：**  
  - `notifications/telegram_commands.py` 中已经实现了命令分发入口（例如 `process_telegram_commands` / `handle_command` 风格 API），并为 `/kill` 与 `/resume` 提供了完整业务逻辑与错误处理；  
  - Kill-Switch 激活/解除与每日亏损相关的核心逻辑（`activate_kill_switch`、`deactivate_kill_switch`、`check_daily_loss_limit` 等）在 `core/risk_control.py` 中统一封装，`/status` 不应绕过这些接口或在命令层维护平行状态；  
  - 日志与审计事件在 7.4.2 中已经为 `/kill` 与 `/resume` 设计了字段与文本模式，应尽量沿用，避免引入第三套格式。  
- **对本 Story 的启示：**  
  - `/status` 命令应站在「观察者」角度，对现有风控状态与审计事件做可读化呈现，而不是重新计算或推导状态；  
  - 所有与风险相关的数值（每日亏损、阈值、权益）应与 PRD 和现有通知中的定义完全一致，避免出现两个版本的「亏损百分比」；  
  - 在 Dev Notes 与 Change Log 中保持对 Epic/PRD/前序 Story 的引用，方便后续 `story-context` 与 code-review 工作流追踪整个 Epic 的实现脉络。  

### References

- [Source: docs/epic-risk-control-enhancement.md#Story-7.4.3-实现-status-命令]  
- [Source: docs/prd-risk-control-enhancement.md#风控状态管理]  
- [Source: docs/prd-risk-control-enhancement.md#Telegram-命令集成]  
- [Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]  
- [Source: docs/sprint-artifacts/7-4-2-实现-kill-和-resume-命令.md]  
- [Source: docs/architecture/06-project-structure-and-mapping.md]  
- [Source: docs/architecture/07-implementation-patterns.md]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/7-4-3-实现-status-命令.context.xml`  
- (相关) `docs/epic-risk-control-enhancement.md#Story-7.4.3-实现-status-命令`  
- (相关) `docs/prd-risk-control-enhancement.md#风控状态管理`  

### Agent Model Used

- Cascade（本 Story 草稿由 SM/AI 协同创建，用于指导后续 Dev Story 实施与代码评审）

### Debug Log References

- `/status` 命令路径中的日志行为建议：  
  - 当收到 `/status` 命令并成功返回状态时：记录 INFO 日志，包含 Kill-Switch、每日亏损与权益等核心字段摘要；  
  - 当命令来自未授权 Chat 时：记录 WARNING 日志并忽略（与 7.4.1 保持一致）；  
  - 当在构建状态文案或发送 Telegram 消息时发生异常：记录 WARNING/ERROR 日志，并返回通用错误提示给用户（如有可能）。  

### Completion Notes List

- [ ] 初始 Story 草稿已由 `/create-story` 工作流创建，等待后续 Dev Story 实施与代码评审。  
- [ ] 完成实现后需更新本节，记录实际完成日期与 Definition of Done。  

### File List

- **预期将被修改/新增的文件（在后续实现 Story 中更新为实际结果）：**  
  - `notifications/telegram_commands.py` — 为 `/status` 命令新增处理逻辑。  
  - `notifications/telegram.py` — 复用发送 helper 将 `/status` 文本发送给用户（如有需要）。  
  - `core/risk_control.py` / `core/state.py` — 如需小幅扩展以提供更方便的只读访问 helper。  
  - `tests/test_notifications_telegram_commands.py` — 新增 `/status` 命令相关单元测试。  

## Change Log

- 2025-12-01: 初始 Story 草稿由 `/create-story` 工作流基于 PRD / Epic / 架构文档与前一 Story 7.4.2 生成，状态设为 `drafted`，等待后续 `story-context` 与 Dev Story 实施。
- 2025-12-01: 通过 Dev Story 完成 `/status` 命令实现与集成，新增单元测试并运行 `./scripts/run_tests.sh` 全量通过一次，状态更新为 `done`。
