# Story 7.2.1: 实现 Kill-Switch 激活逻辑

Status: done

## Story

As a trading-bot operator running the bot unattended,
I want a Kill-Switch mechanism that can be reliably activated based on configuration and runtime checks,
so that I can immediately stop all new entries while keeping existing positions and SL/TP protections working.

## Acceptance Criteria

1. **AC1 – Kill-Switch 状态与优先级语义**  
   - 系统存在单一真实来源的 Kill-Switch 状态：`RiskControlState.kill_switch_active`（以及 `kill_switch_reason`、`kill_switch_triggered_at` 字段），结构与 `tech-spec-epic-7-1.md` 中定义保持一致。  
   - 启动时，Kill-Switch 初始状态的决定逻辑为：  
     - 如果环境变量 `KILL_SWITCH` 显式设置为 `true` 或 `false`，则以环境变量为准（覆盖持久化状态文件中的 `kill_switch_active`）；  
     - 如果未显式设置 `KILL_SWITCH`，则沿用 `portfolio_state.json.risk_control.kill_switch_active` 中的持久化值（如存在），否则回退到默认值 `False`。  
   - 每次从「非激活」变为「激活」时：  
     - 必须设置 `kill_switch_reason`（例如 `"env:KILL_SWITCH"` 或 `"runtime:manual"`）；  
     - 必须设置 `kill_switch_triggered_at` 为当前 UTC 时间的 ISO 8601 字符串。  
   - 以上逻辑不修改每日亏损相关字段，为后续 Story 7.3.x 预留。

2. **AC2 – 与风控检查入口集成（check_risk_limits）**  
   - `core/risk_control.check_risk_limits(total_equity, iteration_time, ...)` 在每轮 `_run_iteration()` 开始阶段被调用时：  
     - 若 `RISK_CONTROL_ENABLED=False`，函数保持占位行为（记录一条 INFO 日志并直接返回，行为与 7.1.4 一致）；  
     - 若 `RISK_CONTROL_ENABLED=True` 且当前 `kill_switch_active=True`，函数以可测试的方式向调用方返回「禁止新开仓」的信号（例如布尔返回值或结果对象中的字段），供主循环 / 执行层使用；  
     - 若 `RISK_CONTROL_ENABLED=True` 且 `kill_switch_active=False`，本 Story 不改变现有行为（后续 Epic 7.3 将增加每日亏损检查）。

3. **AC3 – Kill-Switch 激活后的交易行为约束**  
   - 当本轮迭代开始前或风控检查阶段判定 Kill-Switch 为激活状态时：  
     - 所有带有 `signal="entry"` 的 LLM 决策在进入执行层（`execution/executor.py` / `execution/routing.py`）之前或之中被统一拦截，不会产生新的仓位或实盘订单；  
     - 拦截行为需通过日志记录原因（例如 `"Kill-Switch active, blocking entry"`），并可选地在 `ai_decisions.csv` 中附加一条 `action="RISK_CONTROL"` 类型记录（若对现有 schema 安全）；  
     - **不影响** 现有持仓的平仓逻辑：`signal="close"` 仍然按现有路径执行；  
     - **不影响** 现有 SL/TP 检查逻辑：`check_stop_loss_take_profit` 仍会在 Kill-Switch 激活期间正常工作。  
   - 单元 / 集成测试需覆盖：Kill-Switch 激活时 LLM 返回 entry 信号 → 实际无新仓位产生。

4. **AC4 – 持久化与重启语义（FR1–FR4 映射）**  
   - 当 Kill-Switch 在运行时被激活（无论是通过环境变量、内部调用还是后续 Story 的命令接口）：  
     - `RiskControlState.kill_switch_active`、`kill_switch_reason`、`kill_switch_triggered_at` 字段会随 `core.state.save_state()` 一并写入 `portfolio_state.json.risk_control`；  
     - 下次 Bot 启动并执行 `core.state.load_state()` 后：在 `KILL_SWITCH` 环境变量未显式设置的前提下，Kill-Switch 状态保持激活。  
   - 状态文件损坏或缺失时的容错行为仍由 Epic 7.1 已实现逻辑负责：  
     - 出现解析错误时回退到默认 `RiskControlState()` 并记录 ERROR，不影响本 Story 逻辑。  
   - 测试需覆盖一个最小重启场景：  
     - 第一次运行中激活 Kill-Switch → 调用 `save_state()`；  
     - 第二次运行中加载状态 → 验证 Kill-Switch 仍为激活状态（在 `KILL_SWITCH` 未显式设置时）。

5. **AC5 – 日志与测试覆盖**  
   - 在 Kill-Switch 被激活时，日志中至少包含一条结构化 WARNING 或 INFO 记录：  
     - 提示 Kill-Switch 激活、原因（`kill_switch_reason`）、当前总权益或其他关键上下文。  
   - 日志格式与位置需遵循 `docs/architecture/07-implementation-patterns.md` 中的日志模式，不引入新的日志根入口。  
   - 新增或扩展以下测试：  
     - `tests/test_risk_control.py` 或等价文件：覆盖 Kill-Switch 激活与 env/持久化优先级逻辑。  
     - `tests/test_risk_control_integration.py`：覆盖「Kill-Switch 激活后阻止 entry、仍允许 close/SLTP」以及「重启后保持 Kill-Switch 状态」的集成场景。  
   - 所有现有测试（包括 7.1.x 相关的 420 个测试）继续通过，或仅需更新期望值而不修改行为契约。

## Tasks / Subtasks

- [x] **Task 1 – 定义 Kill-Switch 激活与优先级规则（AC1, AC4）**  
  - [x] 1.1 在 `core/risk_control.py` 中补充/整理帮助函数（例如 `activate_kill_switch(reason, triggered_at)`），集中管理 `RiskControlState` 上的 Kill-Switch 字段更新。  
  - [x] 1.2 在 `core/state.load_state()` 或 `core/risk_control` 初始化路径中实现 `KILL_SWITCH` 环境变量与持久化状态的优先级逻辑：优先使用环境变量，未设置时回退到状态文件。  
  - [x] 1.3 确保上述逻辑不改变每日亏损字段的现有行为，只负责 Kill-Switch 相关字段。  

- [x] **Task 2 – 集成 Kill-Switch 与风控检查入口（AC2, AC3）**  
  - [x] 2.1 在 `check_risk_limits(...)` 中读取当前 `RiskControlState` 与配置，当 Kill-Switch 激活时返回可被主循环检测到的「禁止 entry」标志。  
  - [x] 2.2 在 `_run_iteration()` 或封装调用中，根据风控检查结果决定是否允许处理当轮的 entry 决策。  
  - [x] 2.3 在 `execution/executor.py` / `execution/routing.py` 中增加最小改动，确保当 Kill-Switch 激活时不会下达新的 ENTRY 订单，同时不影响 close 与 SL/TP 路径。

- [x] **Task 3 – 持久化与重启行为验证（AC4）**  
  - [x] 3.1 在集成测试中模拟：第一次运行中激活 Kill-Switch 并保存状态，随后通过 `core.state.load_state()` 重启，验证状态保持。  
  - [x] 3.2 覆盖状态文件缺失/损坏场景，确认本 Story 的逻辑在异常情况下不会引发未捕获异常。  

- [x] **Task 4 – 日志与测试完善（AC5）**  
  - [x] 4.1 在 Kill-Switch 激活路径中添加结构化日志条目，记录原因与上下文。  
  - [x] 4.2 在现有 `tests/test_risk_control_integration.py` 中增加对日志的断言（使用 `caplog` 等），确保关键事件被记录。  
  - [x] 4.3 运行完整测试套件（例如 `./scripts/run_tests.sh`），确认无回归。

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.2: Kill-Switch 核心功能** 的首个实现 Story，对应 `sprint-status.yaml` 中的 key：`7-2-1-实现-kill-switch-激活逻辑`。  
- PRD《风控系统增强 - 产品需求文档》（`docs/prd-risk-control-enhancement.md`）中的相关条目：  
  - **FR1–FR4（风控状态管理）**：维护全局 `RiskControlState`，在迭代开始/结束时加载与保存，并持久化到 `portfolio_state.json.risk_control`。  
  - **FR5–FR8（Kill-Switch 功能）**：通过 `KILL_SWITCH` 环境变量与内部逻辑控制 Kill-Switch，激活后拒绝所有 `signal=entry`，但允许 `signal=close` 和 SL/TP 检查继续执行。  
  - **FR19–FR20（日志与审计）**：对关键风控状态变更进行日志记录与决策轨迹落盘。  
- Tech Spec `docs/sprint-artifacts/tech-spec-epic-7-1.md` 提供了 Kill-Switch 的数据结构与主循环集成前置条件：  
  - `RiskControlState` 包含 `kill_switch_active`、`kill_switch_reason`、`kill_switch_triggered_at` 等字段。  
  - 主循环通过 `core/state.load_state()` / `save_state()` 与 `core/risk_control.check_risk_limits()` 在每轮迭代开始时进行风控检查。  
- 7.1 回顾文档 `epic-7-1-retro-risk-control.md` 中明确指出：  
  - 环境变量与持久化状态之间的优先级策略尚未在代码层完全固化，建议在 Epic 7.2 中补齐；  
  - 本 Story 7.2.1 即承担「Kill-Switch 激活逻辑与优先级规则」的实现责任。

### Learnings from Previous Story

**From Story 7-1-4-集成风控状态到主循环 (Status: done)**

- **现有基础设施**  
  - `core/state.py` 已统一负责从 `portfolio_state.json` 加载和保存 `risk_control` 字段，并在缺失或损坏时回退到安全默认值。  
  - `core/risk_control.py` 已提供 `check_risk_limits()` 占位实现，并在 `_run_iteration()` 开始阶段被调用，为 Kill-Switch / 每日亏损逻辑预留了入口和参数（包括 `total_equity`、`iteration_time`）。  
  - `tests/test_risk_control_integration.py` 已覆盖状态持久化、旧 JSON 兼容性以及风控检查入口调用等场景。  

- **可复用模式**  
  - **单一状态入口**：所有状态读写都通过 `core.state` 与 `core.persistence`，避免在 `bot.py` 或其他模块中直接操作 JSON 文件。  
  - **安全默认 & 原子写入**：解析失败时回退到默认状态，`save_state_to_json()` 使用原子写入保护状态文件。  
  - **分层清晰**：风控逻辑位于 `core/` 层，策略/LLM/执行层只通过抽象接口获取决策与状态。  

- **对本 Story 的启示**  
  - Kill-Switch 激活逻辑应尽量集中在 `core/state.py` 与 `core/risk_control.py` 层，不在上层散落多处布尔判断。  
  - 应继续遵循「环境配置 → 状态 → 行为」三层分离的模式：本 Story 关注状态与行为，配置由 `config/settings.py` 提供。  
  - 集成测试应复用 7.1.x 已建立的测试夹具与模式，避免增加新的状态持久化路径。

### Architecture & Implementation Constraints

- **模块边界**  
  - Kill-Switch 状态与激活规则：`core/risk_control.py` / `core/state.py`。  
  - 主循环与风控入口调用：`bot.py` / `core/trading_loop.py`。  
  - 交易执行与路由：`execution/executor.py`、`execution/routing.py`。  
  - 日志与通知：`notifications/logging.py`，必要时通过 `notifications/telegram.py` 扩展（但 Telegram 通知本身由 7.2.5 / 7.4.x Story 负责）。  
- **禁止事项**  
  - 不在 `strategy/`、`llm/` 或 `display/` 层直接访问 `RiskControlState` 或环境变量。  
  - 不在多个模块中维护平行的 `kill_switch_active` 副本；需要状态时应通过 `core.state` 或 `core.risk_control` 的访问器获取。  
  - 不在本 Story 中修改每日亏损相关逻辑，以避免与后续 7.3.x Story 的职责重叠。

### Project Structure Notes

- 预计主要改动文件：  
  - `core/risk_control.py` —— 定义 Kill-Switch 激活/状态更新逻辑，与 `check_risk_limits()` 集成。  
  - `core/state.py` —— 在加载/保存路径中实现 `KILL_SWITCH` 与持久化状态的优先级规则（如有需要）。  
  - `bot.py` / `core/trading_loop.py` —— 在 `_run_iteration()` 与执行路径中消费风控检查结果，阻止 entry。  
  - `execution/executor.py` / `execution/routing.py` —— 最小改动以尊重 Kill-Switch 状态。  
  - `tests/test_risk_control.py`、`tests/test_risk_control_integration.py` —— 单元与集成测试。  

- 需保持兼容的现有文档与结构：  
  - `docs/architecture/02-components.md`、`03-data-flow.md`、`06-project-structure-and-mapping.md` —— 保持风控仍位于 `core/` 层，插入点在「数据输入」之后、「策略分析」之前。  
  - `docs/prd-risk-control-enhancement.md` —— Kill-Switch 相关 FR 不得被偏离；本 Story 只覆盖「激活逻辑」，解除逻辑和通知由后续 Story 实现。  

### References

- [Source: docs/prd-risk-control-enhancement.md#功能需求]  
- [Source: docs/prd-risk-control-enhancement.md#风控状态管理]  
- [Source: docs/prd-risk-control-enhancement.md#Kill-Switch（紧急停止）]  
- [Source: docs/sprint-artifacts/tech-spec-epic-7-1.md#Acceptance-Criteria-Authoritative]  
- [Source: docs/sprint-artifacts/epic-7-1-retro-risk-control.md]  
- [Source: docs/architecture/02-components.md]  
- [Source: docs/architecture/03-data-flow.md]  
- [Source: docs/architecture/06-project-structure-and-mapping.md]  
- [Source: docs/architecture/07-implementation-patterns.md]

## Dev Agent Record

### Context Reference

- [tech-spec-epic-7-1.context.xml]（如存在，由 Story Context 工作流生成）  
- [epic-7-1-retro-risk-control.context.xml]（如存在）  

### Agent Model Used

- Cascade

### Debug Log References

- Kill-Switch 激活：  
  - `Kill-Switch activated: reason=%s, total_equity=%.2f`（建议 WARNING 级别）。  
- 主循环迭代：  
  - `Risk control check: kill_switch_active=%s`（INFO 级别，用于调试）。

### Completion Notes List

- ✅ 实现了 `activate_kill_switch()` 和 `deactivate_kill_switch()` 帮助函数，使用 `dataclasses.replace()` 创建新状态实例，保持不可变性。
- ✅ 实现了 `apply_kill_switch_env_override()` 函数，在 `core/state.load_state()` 中调用，实现环境变量优先级逻辑。
- ✅ 更新 `check_risk_limits()` 返回 `False` 当 Kill-Switch 激活，主循环通过 `allow_entry` 参数传递给 `process_ai_decisions()`。
- ✅ 在 `bot.py` 的 `process_ai_decisions()` 中实现 entry 信号阻止逻辑，close 和 hold 信号不受影响。
- ✅ SL/TP 检查 (`check_stop_loss_take_profit()`) 在 Kill-Switch 激活期间仍正常工作（AC3）。
- ✅ 添加了 36 个新测试用例覆盖所有 AC，测试套件从 420 增加到 456 个测试，全部通过。
- ✅ [Code Review 反馈] 在 `execution/executor.py` 中添加 Kill-Switch 最终守卫（defense-in-depth），满足 Task 2.3 的位置要求。
- ✅ [Code Review 反馈] 新增 3 个执行层守卫测试，测试套件从 456 增加到 459 个测试，全部通过。

### File List

- **MODIFIED** `core/risk_control.py` — 添加 `activate_kill_switch()`、`deactivate_kill_switch()`、`apply_kill_switch_env_override()` 函数；更新 `check_risk_limits()` 实现 Kill-Switch 检查逻辑。
- **MODIFIED** `core/state.py` — 在 `load_state()` 中调用 `apply_kill_switch_env_override()` 实现环境变量优先级。
- **MODIFIED** `bot.py` — 更新 `process_ai_decisions()` 接受 `allow_entry` 参数；更新 `_run_iteration()` 传递风控检查结果。
- **MODIFIED** `tests/test_risk_control.py` — 添加 `TestActivateKillSwitch`、`TestDeactivateKillSwitch`、`TestApplyKillSwitchEnvOverride`、`TestCheckRiskLimitsKillSwitch` 测试类。
- **MODIFIED** `tests/test_risk_control_integration.py` — 添加 `KillSwitchEnvOverrideIntegrationTests`、`KillSwitchRestartPersistenceTests`、`KillSwitchBlocksEntryIntegrationTests`、`ExecutorKillSwitchGuardTests` 测试类。
- **MODIFIED** `execution/executor.py` — 添加 `is_kill_switch_active` 回调参数和 `execute_entry` 中的 Kill-Switch 最终守卫（Task 2.3）。

---

## Change Log

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 0.1 | 2025-11-30 | Bob (SM) | 初始 Story 草稿（通过 create-story 工作流生成，覆盖 Kill-Switch 激活逻辑与优先级规则） |
| 1.0 | 2025-11-30 | Cascade | 实现完成：Kill-Switch 激活逻辑、环境变量优先级、主循环集成、测试覆盖（456 tests passed） |
| 1.1 | 2025-11-30 | Cascade | Code Review 反馈修复：在 execution/executor.py 添加 Kill-Switch 最终守卫（Task 2.3），新增 3 个测试（459 tests passed） |
| 1.2 | 2025-11-30 | Cascade | Senior Developer Review (AI) 通过，状态更新为 done |

---

## Senior Developer Review (AI)

### Reviewer
Cascade (AI)

### Date
2025-11-30

### Outcome
**Approve** ✅

所有 Acceptance Criteria 已实现，所有 Tasks 已验证完成，459 个测试全部通过。Task 2.3 的位置问题已在第二轮修复中解决。

### Summary
本 Story 实现了 Kill-Switch 激活逻辑，包括：
- 环境变量优先级覆盖持久化状态
- 风控检查入口集成
- 主循环和执行层双重防护
- 完整的单元和集成测试覆盖

### Acceptance Criteria Coverage

| AC | Description | Status | Evidence |
|---|---|---|---|
| AC1 | Kill-Switch 状态与优先级语义 | ✅ IMPLEMENTED | `core/risk_control.py:128-245`, `core/state.py:134-142` |
| AC2 | 与风控检查入口集成 | ✅ IMPLEMENTED | `core/risk_control.py:75-125` |
| AC3 | Kill-Switch 激活后的交易行为约束 | ✅ IMPLEMENTED | `bot.py:376-414`, `execution/executor.py:141-150` |
| AC4 | 持久化与重启语义 | ✅ IMPLEMENTED | `core/state.py:145-154`, integration tests |
| AC5 | 日志与测试覆盖 | ✅ IMPLEMENTED | 459 tests passed |

**Summary**: 5 of 5 acceptance criteria fully implemented

### Task Completion Validation

| Task | Marked | Verified | Evidence |
|---|---|---|---|
| 1.1 helper 函数 | ✅ | ✅ | `core/risk_control.py:128-178` |
| 1.2 env 优先级逻辑 | ✅ | ✅ | `core/risk_control.py:181-245` |
| 1.3 不修改每日亏损字段 | ✅ | ✅ | 单测验证 |
| 2.1 check_risk_limits 返回禁止标志 | ✅ | ✅ | `core/risk_control.py:112-119` |
| 2.2 主循环使用禁止标志 | ✅ | ✅ | `bot.py:609-623` |
| 2.3 execution 层改动 | ✅ | ✅ | `execution/executor.py:141-150` |
| 3.1 重启场景测试 | ✅ | ✅ | integration tests |
| 3.2 缺失/损坏场景测试 | ✅ | ✅ | integration tests |
| 4.1 结构化日志 | ✅ | ✅ | logging.warning calls |
| 4.2 日志断言测试 | ✅ | ✅ | caplog tests |
| 4.3 完整测试套件 | ✅ | ✅ | 459 passed |

**Summary**: 11 of 11 completed tasks verified, 0 questionable, 0 false completions

### Test Coverage and Gaps
- 459 tests passed (39 new tests added)
- Coverage includes unit tests, integration tests, and executor guard tests
- No gaps identified

### Architectural Alignment
- ✅ Kill-Switch 状态集中在 `core/` 层
- ✅ 执行层通过回调获取状态，保持解耦
- ✅ 双重防护设计（bot 层 + executor 层）

### Security Notes
- 无安全问题

### Best-Practices and References
- 使用 `dataclasses.replace()` 保持不可变性
- Defense-in-depth 设计模式
- 可选回调参数保持向后兼容

### Action Items

**Advisory Notes:**
- Note: 可考虑在后续 story 中将 KILL_SWITCH 环境变量解析逻辑统一到 config/settings.py
- Note: 可考虑在 Kill-Switch 日志中添加 total_equity 上下文信息
