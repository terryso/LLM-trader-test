# Story 7.4.2: 实现 kill 和 resume 命令
 
Status: done
 
## Story

As a user,
I want to control Kill-Switch via Telegram commands,
so that I can quickly pause or resume trading in response to risk events.

## Acceptance Criteria

1. **AC1 – /kill 命令激活 Kill-Switch（对齐 Epic 7.2 / 7.4.2，PRD FR5, FR6, FR7）**  
   - 在已正确配置 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`，且 Bot 正常运行时：  
     - 当收到来自授权 Chat 的 `/kill` 命令：  
       - 调用 `activate_kill_switch(risk_control_state, reason=...)` 或等价封装，激活 Kill-Switch；  
       - 在下一轮迭代中，所有 `signal="entry"` 的决策被拒绝（沿用既有 Kill-Switch 信号过滤逻辑）；  
       - 现有持仓的 `signal="close"` 与 SL/TP 检查保持正常工作；  
       - 通过 Telegram 发送一条确认消息，明确告知 Kill-Switch 已激活并给出触发原因（包括“Manual trigger via Telegram”）。

2. **AC2 – /resume 与 /resume confirm 的二次确认机制（对齐 Epic 7.2 / 7.4.2，PRD FR9–FR11, FR16）**  
   - 当 Kill-Switch 处于激活状态时：  
     - 收到 `/resume` 命令但未带 `confirm` 参数：  
       - 不改变 Kill-Switch 状态；  
       - 返回一条提示消息，明确要求用户发送 `/resume confirm` 才会真正解除 Kill-Switch；  
       - 日志中记录一次尝试恢复但未确认的事件。  
     - 收到 `/resume confirm` 命令：  
       - 调用 `deactivate_kill_switch(risk_control_state, force=...)` 或等价封装；  
       - 若解除成功（包括每日亏损未触发或已通过 `/reset_daily` 处理）：  
         - Kill-Switch 状态变为未激活；  
         - 通过 Telegram 发送解除成功的确认消息；  
       - 若解除失败（例如每日亏损限制仍在生效且未强制恢复）：  
         - 保持 Kill-Switch 激活；  
         - 返回一条解释失败原因的消息（例如“每日亏损限制仍在生效”）。

3. **AC3 – 日志与审计（对齐 PRD FR19–FR21）**  
   - 每次执行 `/kill` 或 `/resume` / `/resume confirm` 命令时：  
     - 在日志中以结构化方式记录：命令名称、chat_id、执行结果（成功/失败/需确认）、风险状态变化（前后对比）、触发原因；  
     - 对成功激活/解除 Kill-Switch 的操作，在 `ai_decisions.csv` 或等价审计通道中记录一条 `action="RISK_CONTROL"` 的事件，包含 `source="telegram-command"` 与简要描述。  
   - 网络错误或 Telegram 回复失败不会影响 Kill-Switch 实际状态，但会以 WARNING/ERROR 级别记录日志。

4. **AC4 – 单元测试与回归（对齐 Epic 7.2 / 7.4，PRD 成功标准）**  
   - 新增或扩展测试（例如 `tests/test_notifications_telegram_commands.py` 或独立模块），覆盖：  
     - `/kill` 正常路径：激活 Kill-Switch 并返回确认文案；  
     - `/resume` 未带 `confirm`：保持 Kill-Switch 激活并返回提示；  
     - `/resume confirm` 成功解除 Kill-Switch 的路径；  
     - `/resume confirm` 由于每日亏损触发等原因无法解除时的处理与返回文案；  
     - 未授权 chat 下同名命令不会生效；  
     - 日志与审计调用在关键路径被正确触发（可通过 mock/spy 校验）。  
   - 运行 `./scripts/run_tests.sh` 时，所有既有测试与本 Story 新增测试均通过。

## Tasks / Subtasks

- [x] **Task 1 – 设计命令处理入口与路由（AC1, AC2, AC3）**  
  - [x] 1.1 在 `notifications/telegram_commands.py` 或等价模块中，基于现有命令解析结果，定义统一的命令分发入口（例如 `process_telegram_commands(commands)` 或 `handle_command(command, args, ...)`）。  
  - [x] 1.2 明确命令处理层与底层 `TelegramCommandHandler.poll_commands()` 的边界：前者只消费结构化命令对象，不重新处理 HTTP / offset 等细节。  
  - [x] 1.3 设计返回值约定（文本消息 / 结构化结果），供发送层复用（例如统一通过 `notifications/telegram.py` 发送回复消息）。

- [x] **Task 2 – 实现 /kill 命令（AC1, AC3）**  
  - [x] 2.1 在命令处理入口中增加对 `command == "kill"` 的分支，将调用路由到 Kill-Switch 相关逻辑。  
  - [x] 2.2 调用 `activate_kill_switch(risk_control_state, reason="Manual trigger via Telegram")` 或等价 helper，并确保使用 UTC 时间。  
  - [x] 2.3 调用通知发送函数（例如 `send_telegram_message` 或包装函数），返回包含原因与后续操作建议的确认消息。  
  - [x] 2.4 记录结构化日志与审计事件（如 `action="RISK_CONTROL"`, `detail="kill via telegram"`）。

- [x] **Task 3 – 实现 /resume 与 /resume confirm 命令（AC2, AC3）**  
  - [x] 3.1 在命令处理入口中增加对 `command == "resume"` 的分支。  
  - [x] 3.2 当未带 `confirm` 参数时，仅返回提示消息（例如"请发送 /resume confirm 以确认解除"），不修改风控状态。  
  - [x] 3.3 当 `args[0] == "confirm"` 时，调用 `deactivate_kill_switch(risk_control_state, force=...)` 或等价 helper：  
        - 根据 `daily_loss_triggered` 等字段决定是否允许解除；  
        - 返回成功或失败文案，并记录相应日志与审计事件。  
  - [x] 3.4 与 `/kill` 保持一致的 Markdown 与本地化风格（中文提示 + emoji）。

- [x] **Task 4 – 集成到主循环与测试（AC1–AC4）**  
  - [x] 4.1 在 `bot.py` 中，基于已有的 `poll_telegram_commands()` 调用，将解析出的命令列表传递给新的命令处理入口。  
  - [x] 4.2 确保命令处理失败不会中断 `_run_iteration()`：捕获异常、记录日志、继续后续风控与交易逻辑。  
  - [x] 4.3 在 `tests/test_notifications_telegram_commands.py` 或新建测试文件中，为 `/kill`、`/resume`、`/resume confirm` 的典型与异常路径补充单元测试。  
  - [x] 4.4 运行 `./scripts/run_tests.sh` 并在 Change Log 中记录一次成功运行。

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.4: Telegram 命令集成** 的第二个实现 Story，对应 `sprint-status.yaml` 中的 key：`7-4-2-实现-kill-和-resume-命令`。  
- 需求主要来源：  
  - Epic 文档 `docs/epic-risk-control-enhancement.md` 中 **Story 7.4.2: 实现 /kill 和 /resume 命令** 的拆解与示例代码：  
    - 明确 `/kill` 激活 Kill-Switch，`/resume` + `/resume confirm` 解除 Kill-Switch，并要求有确认机制；  
    - 提供了 `handle_command(command, args)` 风格的示例实现。[Source: docs/epic-risk-control-enhancement.md#Story-7.4.2-实现-kill-和-resume-命令]  
  - PRD 文档 `docs/prd-risk-control-enhancement.md` 中 **Kill-Switch 功能** 与 **Telegram 命令集成** 段落：  
    - FR5–FR11 定义了 Kill-Switch 的触发、恢复、行为约束与通知要求；  
    - FR22–FR24 定义了 Telegram 命令接收、安全校验与未知命令帮助信息行为。[Source: docs/prd-risk-control-enhancement.md#Kill-Switch-功能]  
  - `docs/epics.md` 中 **Epic 7.4: Telegram 命令集成（Post-MVP）** 的范围说明：  
    - 本 Epic 用 Telegram 命令为 Kill-Switch、每日亏损限制等能力提供远程控制手段。[Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]
- 与前序 Stories 的关系：  
  - Epic 7.1 / 7.2 / 7.3 已提供 `RiskControlState`、Kill-Switch 激活/解除与每日亏损限制的核心逻辑与通知通路（参考 `docs/sprint-artifacts/7-3-4-实现每日亏损限制通知.md` 等）；  
  - Story 7.4.1 已实现 Telegram 命令接收与解析，将结构化命令对象安全地注入主循环；  
  - 本 Story 在此基础上实现 `/kill` 与 `/resume` 命令的**业务语义**与安全确认机制。

### Architecture & Implementation Constraints

- **模块边界与职责：**  
  - `notifications/telegram_commands.py`：  
    - 负责从 Telegram API 拉取更新并解析为 `TelegramCommand`（已由 Story 7.4.1 建立）；  
    - 在本 Story 中扩展命令处理层（例如 `process_telegram_commands` 或 `handle_command`）时，应避免与 HTTP 访问/offset 管理耦合。  
  - `notifications/telegram.py`：  
    - 继续专注于发送通知与封装发送 helper，可被命令处理层复用以推送确认/错误消息；  
    - 不直接负责任何 Kill-Switch 业务决策。  
  - `core/risk_control.py`：  
    - 暴露 `activate_kill_switch`、`deactivate_kill_switch`、`check_daily_loss_limit` 等 API，作为命令处理层的唯一入口；  
    - 命令处理不应直接修改 `RiskControlState` 内部字段，而应通过这些 helper 函数完成。  
  - `bot.py`：  
    - 在 `_run_iteration()` 中装配 `TelegramCommandHandler`，调用 `poll_telegram_commands()` 后将结果交给命令处理入口；  
    - 只依赖高层接口（例如 `process_telegram_commands(commands)`），不关心具体命令细节。
- **一致性要求：**  
  - 错误处理与日志风格应与现有 Telegram 通知模块保持一致（参考 Story 7.4.1）：使用 WARNING/ERROR 级别，避免静默失败；  
  - 所有与 Kill-Switch 状态相关的变更必须使用 UTC 时间，并记录在日志中，便于后续审计与排错；  
  - 保持与 `docs/architecture/06-project-structure-and-mapping.md`、`docs/architecture/07-implementation-patterns.md` 中的分层与依赖方向一致。[Source: docs/architecture/06-project-structure-and-mapping.md]  
  - 命令字符串与参数语义（`/kill`、`/resume confirm`）需与 PRD 与前序通知文案保持完全一致，避免用户混淆。

### Project Structure Notes

- 预期主要涉及文件（以实际实现为准）：  
  - `notifications/telegram_commands.py` —— 在 Story 7.4.1 的基础上扩展命令处理逻辑（路由 `/kill`、`/resume`、`/resume confirm` 到风控 API）。  
  - `notifications/telegram.py` —— 复用现有发送 helper，用于将命令处理结果反馈给用户。  
  - `core/risk_control.py` —— 复用/细化 Kill-Switch 激活与解除函数，确保与每日亏损限制逻辑协同。  
  - `bot.py` —— 在 `_run_iteration()` 中调用命令处理入口，确保在风控检查与 LLM 决策之前处理控制类命令。  
  - `tests/test_notifications_telegram_commands.py` —— 为新命令处理逻辑补充单元测试。  
- 需要继续遵守架构文档中对外部服务适配层与主循环解耦的约定：  
  - Telegram API 访问集中在 notifications 层；  
  - 风控与交易决策集中在 core/bot 层；  
  - 通过清晰的函数接口跨层传递最小必要的信息。

### Learnings from Previous Story

- **前一 Story:** 根据 `sprint-status.yaml` 的顺序，上一条已完成的 Story 是 `7-4-1-实现-telegram-命令接收机制`（状态为 `done`，详见 `docs/sprint-artifacts/7-4-1-实现-telegram-命令接收机制.md`）。  
- **可复用能力与约束：**  
  - `TelegramCommandHandler` 已经实现了 `getUpdates` 轮询、chat 过滤、命令解析与 `last_update_id` 管理，本 Story 不应重复实现这些基础设施，而是直接复用其输出 `TelegramCommand` 对象。  
  - 主循环 `_run_iteration()` 已在早期阶段集成了 `poll_telegram_commands()`，并预留了将命令传递给后续处理入口的机制（例如 `process_telegram_commands(commands)`）；本 Story 应在这一入口上实现具体业务逻辑，而非在主循环中内联处理每条命令。  
  - 日志与错误处理模式（包括未授权 chat、网络错误、JSON 解析异常等）已在 7.4.1 中定义，本 Story 应延续相同的模式，避免引入新的“静默失败”路径。  
- **对本 Story 的启示：**  
  - 所有 `/kill` 与 `/resume` 相关的行为（包括失败场景）都应通过 Telegram 回复与日志双重暴露，保证用户可见性与后续审计能力；  
  - 恢复逻辑必须与每日亏损限制（7.3.x）配合，避免绕过 `daily_loss_triggered` 保护；若需要强制恢复，应通过显式的 `force=True` 或后续 `/reset_daily` 语义实现。  
  - 在 Dev Notes 与 Change Log 中保持对 Epic/PRD/前序 Story 的引用，方便后续 Review 与 `story-context` 工作流构建技术上下文。

### References

- [Source: docs/epic-risk-control-enhancement.md#Story-7.4.2-实现-kill-和-resume-命令]  
- [Source: docs/prd-risk-control-enhancement.md#Kill-Switch-功能]  
- [Source: docs/prd-risk-control-enhancement.md#Telegram-命令集成]  
- [Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]  
- [Source: docs/sprint-artifacts/7-4-1-实现-telegram-命令接收机制.md]  
- [Source: docs/architecture/06-project-structure-and-mapping.md]  
- [Source: docs/architecture/07-implementation-patterns.md]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/7-4-2-实现-kill-和-resume-命令.context.xml`（由后续 `story-context` 工作流生成后填充）  
- (相关) `docs/epic-risk-control-enhancement.md#Story-7.4.2-实现-kill-和-resume-命令`  
- (相关) `docs/prd-risk-control-enhancement.md#Kill-Switch-功能`

### Agent Model Used

- Cascade（本 Story 草稿由 SM/AI 协同创建，用于指导后续 Dev Story 实施与代码评审）

### Debug Log References

- 命令处理路径中的日志行为建议：  
  - 当收到 `/kill` 时：记录 INFO/NOTICE 级日志，包含 chat_id、reason、前后 Kill-Switch 状态；  
  - 当收到 `/resume` 但未确认时：记录 INFO 日志，标记为“resume-request-pending-confirm”；  
  - 当收到 `/resume confirm` 时：记录 INFO/WARNING 日志，描述解除是否成功以及失败原因；  
  - 所有异常情况（调用风控 API 失败、发送 Telegram 消息失败等）记录 WARNING/ERROR 级别日志并附带 stack/错误文本。

### Completion Notes

**Completed:** 2025-12-01
**Definition of Done:** All acceptance criteria met, code reviewed, tests passing

### File List

- **已修改文件:**  
  - `notifications/telegram_commands.py` — 添加 `CommandResult`、`handle_kill_command()`、`handle_resume_command()`、`create_kill_resume_handlers()` 等。  
  - `bot.py` — 更新 `poll_telegram_commands()` 以集成命令处理器。  
- **已扩展测试文件:**  
  - `tests/test_notifications_telegram_commands.py` — 新增 `TestHandleKillCommand`、`TestHandleResumeCommand`、`TestCreateKillResumeHandlers`、`TestKillResumeIntegration` 测试类。

## Change Log

- 2025-12-01: 初始 Story 草稿由 `/create-story` 工作流基于 PRD / Epic / 架构文档与前一 Story 7.4.1 生成，状态设为 `drafted`，等待后续 `story-context` 与 Dev Story 实施。
- 2025-12-01: 完成 Story 实现，所有任务已完成，631 个测试全部通过。状态更新为 `review`。
