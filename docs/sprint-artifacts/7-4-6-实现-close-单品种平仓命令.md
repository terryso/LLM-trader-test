# Story 7.4.6: 实现 /close 单品种平仓命令

Status: ready-for-dev

## Story

As a user,
I want to partially or fully close a specific position via the Telegram `/close` command,
so that I can quickly reduce risk on a single symbol without logging into the exchange.

## Acceptance Criteria

1. **AC1 – 支持 /close 命令基本格式（对齐 PRD FR26、Epic 7.4.6）**  
   - 支持以下命令形式：`/close SYMBOL`、`/close SYMBOL all` 与 `/close SYMBOL AMOUNT`；  
   - `SYMBOL` 使用与当前持仓结构一致的标识（例如 `BTCUSDT`、`ETHUSDT` 等），并与 `/positions` 输出保持一致；  
   - 当未提供 `AMOUNT` 或显式使用 `all` 时，表示对该品种当前持仓执行全平；  
   - `AMOUNT` 表示当前名义仓位的百分比（0–100），用于部分平仓，例如 `25` 表示平掉当前仓位的 25%。

2. **AC2 – 部分平仓行为与百分比换算**  
   - 当用户输入 `/close SYMBOL AMOUNT` 且 `0 < AMOUNT < 100` 时：  
     - 基于当前名义仓位计算目标平仓名义金额：`target_notional = 当前名义仓位 * AMOUNT / 100`；  
     - 根据当前持仓方向、多空标记与合约/币的最小下单单位，计算需要下单的数量（合约张数或币数量）；  
     - 数量计算遵循统一规则：按交易所最小单位向下取整，避免提交低于最小下单量的订单；  
     - 使用 reduce-only 市价单（或等价实现）执行部分平仓，保证不会反向开新仓；  
     - Telegram 返回文案中需包含：本次实际平仓名义金额（约值）、估算成交数量、平仓后剩余持仓的方向与名义金额。

3. **AC3 – 请求百分比大于等于 100% 时退化为全平**  
   - 当用户输入 `/close SYMBOL AMOUNT` 且 `AMOUNT >= 100` 时：  
     - 不再尝试精确部分平仓，而是退化为全平行为；  
     - 下发 reduce-only 市价单执行全平；  
     - 返回文案需明确提示“请求百分比 >= 100%，已执行全平”，并给出平仓前后名义金额与方向信息。

4. **AC4 – 无持仓场景的安全处理**  
   - 当该 `SYMBOL` 当前无持仓时：  
     - 不下发任何实盘或纸上平仓订单；  
     - 返回清晰提示（例如“当前无 BTCUSDT 持仓，未执行平仓操作”）；  
     - 记录一条信息级日志，标明收到 `/close` 请求但无对应持仓。

5. **AC5 – 错误处理与日志记录（对齐 PRD 非功能与日志要求）**  
   - 命令执行过程中的错误（如交易所拒单、最小下单量不足、网络异常、参数解析失败）必须：  
     - 在日志中记录结构化信息（包含 symbol、请求金额、计算出的下单数量、错误原因摘要）；  
     - 在 Telegram 中返回简明错误信息，避免泄露敏感实现细节，但足以指导用户下一步操作（如“请求金额过小，低于最小下单单位”）；  
     - 错误不会导致 Bot 主循环退出或中断当前迭代。

6. **AC6 – 与风控联动：Kill-Switch / 每日亏损限制激活时仍允许平仓**  
   - 当 Kill-Switch 或每日亏损限制已激活时：  
     - `/close` 命令仍然允许执行，因为只会减少风险敞口或全平持仓；  
     - 不受 entry 信号过滤逻辑影响，不会被错误地视为新开仓；  
     - 日志或文案中如有需要，可在成功平仓后附带当前 Kill-Switch / 日亏状态摘要（可选）。

7. **AC7 – 单元测试与回归**  
   - 在 `tests/` 目录中新增针对 `/close` 命令的测试用例，至少覆盖：  
     - 全平场景：`/close SYMBOL` 与 `/close SYMBOL all` 在有持仓与无持仓两种情况下的行为；  
     - 部分平仓场景：`/close SYMBOL AMOUNT` 且 `0 < AMOUNT < 100` 时的行为；  
     - 请求百分比大于等于 100% 时退化为全平的行为；  
     - 参数非法（缺少 SYMBOL、AMOUNT 非数字、AMOUNT 不在合理范围等）时的错误提示与日志；  
     - 在 Kill-Switch / 日亏限制激活时，`/close` 仍能正常执行并只减仓。  
   - 运行 `./scripts/run_tests.sh` 时，所有既有测试与本 Story 新增测试均通过。

## Tasks / Subtasks

- [ ] **Task 1 – 定义 /close 命令接口与参数解析（AC1）**  
  - [ ] 1.1 在 `notifications/telegram_commands.py` 中为 `/close` 预留命令入口（如在命令注册表或 handler 工厂中登记 `"close"`），复用现有命令分发模式。  
  - [ ] 1.2 设计并实现参数解析逻辑：解析 `SYMBOL`、`all` 与 `AMOUNT`，对非法输入返回明确错误。  
  - [ ] 1.3 与 `/positions` 或持仓结构保持一致的 symbol 命名约定，避免由于大小写或后缀差异导致的匹配失败。

- [ ] **Task 2 – 设计并实现部分/全平执行路径（AC2–AC3）**  
  - [ ] 2.1 在现有平仓执行路径（执行层/交易所层）上设计一个“单 symbol 平仓”接口，输入为 symbol、方向、名义金额或“all”，输出为本次实际成交的名义金额与剩余仓位信息。  
  - [ ] 2.2 实现名义金额 → 数量的换算逻辑，考虑：当前价格来源、合约/币最小单位、精度与向下取整规则。  
  - [ ] 2.3 使用 reduce-only 市价单或等价方式触达交易所，保证不会因为数量误差导致反向开仓。  
  - [ ] 2.4 根据执行结果构建 Telegram 返回文案，清晰呈现本次平仓的核心信息（方向、数量、名义金额、剩余持仓）。

- [ ] **Task 3 – 无持仓与错误场景的防御式处理（AC4–AC5）**  
  - [ ] 3.1 在尝试下单前，统一查询当前持仓快照：若无对应 symbol，则直接返回“无持仓”提示，不执行任何交易。  
  - [ ] 3.2 为交易所拒单、最小下单量不足、网络异常等场景设计统一的错误捕获与日志模式，保持与其它 Telegram 命令一致。  
  - [ ] 3.3 在错误场景下构造简明的 Telegram 提示，并确保不会修改现有持仓状态或触发新的风险敞口。

- [ ] **Task 4 – 与风控状态集成与回归测试（AC6–AC7）**  
  - [ ] 4.1 在执行 `/close` 前后，复用或扩展现有风控检查逻辑，确保该命令在 Kill-Switch / 日亏限制激活时依然允许执行。  
  - [ ] 4.2 新增/扩展单元测试，覆盖在 Kill-Switch / 日亏限制激活状态下执行 `/close` 时的行为，验证不会被 entry 过滤逻辑阻挡。  
  - [ ] 4.3 运行 `./scripts/run_tests.sh`，确保新增逻辑不会破坏现有测试。

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.4: Telegram 命令集成（Post-MVP）** 的第六个实现 Story，对应 `sprint-status.yaml` 中的 key：`7-4-6-实现-close-单品种平仓命令`。  
- 需求主要来源：  
  - Epic 文档 `docs/epic-risk-control-enhancement.md` 中 **Story 7.4.6: 实现 /close 单品种平仓命令**：  
    - 明确 `/close SYMBOL [AMOUNT|all]` 的语义：当省略 `AMOUNT` 或使用 `all` 时表示全平，`AMOUNT` 为当前名义仓位的百分比（0–100），当 `AMOUNT >= 100` 时退化为全平并在文案中说明；  
    - 要求在无持仓、请求百分比过小、交易所拒单等场景下给出清晰的用户反馈与日志。[Source: docs/epic-risk-control-enhancement.md#Story-7.4.6-实现-close-单品种平仓命令]  
  - 风控 PRD 文档 `docs/prd-risk-control-enhancement.md` 中的 **FR26**：  
    - 定义用户可以通过 `/close SYMBOL [AMOUNT|all]` 对单个品种执行部分或全部平仓，其中不带 `AMOUNT` 或使用 `all` 表示全平；  
    - 强调 `AMOUNT` 表示当前名义仓位的百分比（0–100），`AMOUNT < 100` 为部分平仓，`AMOUNT >= 100` 退化为全平。[Source: docs/prd-risk-control-enhancement.md#Telegram-命令集成]  
  - `docs/epics.md` 中 **Epic 7: 风控系统增强（Emergency Controls）** 与 **Epic 7.4: Telegram 命令集成** 的范围说明：  
    - Telegram 命令集成是风控系统的操控界面；  
    - `/close` 与 `/close_all`、`/sl`/`/tp`/`/tpsl` 一起构成远程仓位管理能力。[Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]

### Architecture & Implementation Constraints

- **模块边界与职责（参考 `docs/architecture/06-project-structure-and-mapping.md` 与现有 7.4.x 实现）：**  
  - `notifications/telegram.py`：负责底层 Telegram Bot API 调用与消息发送；  
  - `notifications/telegram_commands.py`：集中实现命令解析、命令 handler 与命令分发，是 `/close` 命令的主要入口与文案构建位置；  
  - `core/` + `execution/` + `exchange/`：负责实际的持仓查询与平仓执行逻辑（包括名义金额到数量的换算、最小下单量处理、reduce-only 市价单等），Telegram 层不直接触达交易所 SDK，而是通过统一抽象调用。  
  - `core/risk_control.py` 与相关调用方：提供 Kill-Switch / 每日亏损限制的状态与检查逻辑，`/close` 需要与其集成但不被其阻挡。

- **实现模式与错误处理（参考 `docs/architecture/07-implementation-patterns.md`）：**  
  - 统一使用 Python `snake_case` 命名函数与变量，常量使用 `UPPER_SNAKE_CASE`；  
  - 错误处理遵循“记录日志但不终止主循环”的原则：网络错误、交易所拒单等场景都应被捕获并写入结构化日志，而不是抛出到交易主循环；  
  - 用户可见文案中金额与百分比采用统一格式（如 `$1234.56`、`-5.00%`），并尽量保持简洁、可读。

### Project Structure Notes

- 预计主要涉及文件（以实际实现为准）：  
  - `notifications/telegram_commands.py` —— 新增 `/close` 命令 handler、参数解析与结果文案构造；  
  - `notifications/telegram.py` —— 如需扩展发送辅助函数或统一 MarkdownV2 转义，可在此补充；  
  - `core/state.py` / `core/persistence.py` —— 若需要读取或更新本地持仓与权益视图；  
  - `execution/` 与 `exchange/` 下的执行与交易所适配模块 —— 提供实际的平仓执行接口（纸上/实盘路径复用同一抽象）；  
  - `tests/` 目录下与平仓、Telegram 命令相关的测试文件（例如 `tests/test_notifications_telegram_commands.py`）。

- 实现应继续遵守现有关于「运行时数据目录」「配置通过 .env 注入」「测试全部集中在 tests/ 目录」的约定，避免为 `/close` 命令引入新的数据根目录或配置入口；任何新增配置项需要同步更新 `.env.example` 与相关文档（如有）。

### Learnings from Previous Stories

- **前置 Story：7-4-1 ～ 7-4-5**  
  - Story 7.4.1 已建立 Telegram 命令接收机制与 `TelegramCommandHandler`；  
  - Story 7.4.2 实现了 `/kill` 与 `/resume` 命令，并定义了与 Kill-Switch 风控的集成模式；  
  - Story 7.4.3 与 7.4.4 分别提供了 `/status` 与 `/reset_daily`，在 Telegram 层已经建立起了“读取组合状态 + 修改风控状态”的基础能力；  
  - Story 7.4.5 为所有命令（包括 `/help`）建立了统一的安全校验与未知命令 fallback 模式（基于 `TELEGRAM_CHAT_ID` 与命令注册表/分发逻辑）。

- **对本 Story 的启示：**  
  - `/close` 的 handler 应当完全复用现有命令接收与安全校验通路，而不是单独再实现一套 Telegram API 调用或 Chat ID 校验；  
  - 为避免文案与实现脱节，推荐从统一的持仓结构与 symbol 列表生成 `/close` 相关提示（例如当无持仓时给出 `/positions` 提示链接）；  
  - 日志与审计建议继续沿用 7.4.x 既有模式，例如在平仓成功/失败时记录统一的 `action` 标识，便于后续回放与监控。

### References

- [Source: docs/epic-risk-control-enhancement.md#Story-7.4.6-实现-close-单品种平仓命令]  
- [Source: docs/prd-risk-control-enhancement.md#Telegram-命令集成]  
- [Source: docs/epics.md#Epic-7-风控系统增强-Emergency-Controls]  
- [Source: docs/epics.md#Epic-7.4-Telegram-命令集成-Post-MVP]  
- [Source: docs/sprint-artifacts/7-4-5-实现-help-命令和安全校验.md]  
- [Source: docs/architecture/06-project-structure-and-mapping.md]  
- [Source: docs/architecture/07-implementation-patterns.md]

## Dev Agent Record

### Context Reference

- 相关 PRD 与 Epic：  
  - `docs/epic-risk-control-enhancement.md#Story-7.4.6-实现-close-单品种平仓命令`  
  - `docs/prd-risk-control-enhancement.md#Telegram-命令集成`  
- 相关实现 Story：  
  - `docs/sprint-artifacts/7-4-1-实现-telegram-命令接收机制.md`  
  - `docs/sprint-artifacts/7-4-2-实现-kill-和-resume-命令.md`  
  - `docs/sprint-artifacts/7-4-3-实现-status-命令.md`  
  - `docs/sprint-artifacts/7-4-4-实现-reset-daily-命令.md`  
  - `docs/sprint-artifacts/7-4-5-实现-help-命令和安全校验.md`

### Agent Model Used

- Cascade（本 Story 草稿由 SM/AI 协同创建，用于指导后续 Dev Story 实施与代码评审）

### Debug Log References

- 建议在 `/close` 命令实现中遵循以下日志模式：  
  - 收到授权 Chat 的 `/close` 命令时记录 `INFO` 日志，包含 `symbol`、`args`、`chat_id` 与解析结果；  
  - 在无持仓、参数非法或请求金额过小等场景下记录 `WARNING` 日志，并在文案中给出清晰提示；  
  - 在执行平仓（部分/全平）时记录 `INFO` 或 `WARNING` 日志，包含 symbol、方向、平仓名义金额、剩余名义金额与错误原因（如有）；  
  - 对异常路径（网络错误、交易所拒单等）记录 `ERROR` 日志，并确保异常不会中断主循环。

### Completion Notes List

- [ ] 初始 Story 草稿由 `/create-story` 工作流创建，状态设为 `ready-for-dev`，等待后续 Dev Story 实施与代码评审。

### File List

- **NEW** `docs/sprint-artifacts/7-4-6-实现-close-单品种平仓命令.md` — 当前 Story 草稿文件（本文件）。
