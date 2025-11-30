# Story 7.2.4: 确保 SL/TP 在 Kill-Switch 期间正常工作

Status: review

## Story

As a trading-bot operator relying on automatic risk protections,
I want stop-loss and take-profit checks to keep working even when the Kill-Switch is active,
so that existing positions can still be protected and unwound safely during emergency shutdowns.

## Acceptance Criteria

1. **AC1 – Kill-Switch 激活时 SL/TP 检查仍然执行（PRD FR7–FR8 对齐）**  
   - 在 `RISK_CONTROL_ENABLED=True` 且 `risk_control_state.kill_switch_active=True` 的情况下：  
     - 每轮 `_run_iteration()` 仍然在风控检查之后调用一次 `bot.check_stop_loss_take_profit()`；  
     - SL/TP 检查基于 `execution.routing.check_stop_loss_take_profit_for_positions(...)`，对所有持仓遍历执行，不因为 Kill-Switch 而跳过。  
   - 对于多空两侧持仓：  
     - Long：低点 `low` 低于 `stop_loss` 时触发止损；在 `low > stop_loss` 且高点 `high` 高于 `profit_target` 时触发止盈；  
     - Short：高点 `high` 高于 `stop_loss` 时触发止损；在 `high < stop_loss` 且低点 `low` 低于 `profit_target` 时触发止盈；  
     - 触发时均调用 `execute_close(...)`，行为与当前 `tests/test_stop_loss_take_profit.py` 约定保持一致。  
   - 新增或更新测试覆盖以下场景：  
     - Kill-Switch 未激活时的 SL/TP 行为（回归基线）；  
     - Kill-Switch 激活时的 SL/TP 行为，与未激活时**完全一致**（仅 entry 行为受 Kill-Switch 影响）。

2. **AC2 – Kill-Switch 仅阻止 entry，不阻止 close 与 SL/TP**  
   - 在 Kill-Switch 激活 (`kill_switch_active=True`) 且 `check_risk_limits(...)` 返回 `allow_entry=False` 的情况下：  
     - `process_ai_decisions(...)` 中：  
       - 所有 `signal="entry"` 的决策被统一阻止，并按 Story 7.2.3 的日志与 `ai_decisions.csv` 方案记录审计事件；  
       - 所有 `signal="close"` 的决策仍然按现有路径调用 `execute_close(...)`，不受 Kill-Switch 影响；  
       - `signal="hold"` 行为保持不变。  
     - `check_stop_loss_take_profit()` 触发的止损/止盈 close 同样不受 Kill-Switch 影响：  
       - 本 Story 不在 SL/TP 路径上引入任何基于 Kill-Switch 的 early-return 或 short-circuit；  
       - 至少通过 1–2 个集成测试验证：在 Kill-Switch 激活期间有持仓且价格触及 SL 或 TP 时，实际发生 close，并且 Kill-Switch 不阻断。  
   - 文档层面明确约束：**Kill-Switch 只阻止新的开仓（entry），不阻止风险收缩方向的操作（close / SL/TP）。**

3. **AC3 – Hyperliquid 实盘模式下的 SL/TP 语义与 Kill-Switch 协同**  
   - 当 `hyperliquid_trader.is_live=True` 时：  
     - `bot.check_stop_loss_take_profit()` 继续保持当前行为：直接返回，不发起任何基于本地 K 线的 SL/TP close 调用（依赖交易所原生触发单）；  
     - Kill-Switch 激活与否**不改变**上述行为，防止在实盘路径中引入双重或冲突的 SL/TP 逻辑。  
   - 在 `hyperliquid_trader.is_live=False` 的纸上/模拟路径中：  
     - Kill-Switch 激活时，SL/TP 逻辑按 AC1/AC2 正常运行；  
     - 新增或更新测试显式覆盖 `is_live=True/False` × `kill_switch_active=True/False` 的组合，验证：  
       - 实盘模式下从不调用 `fetch_market_data` / `execute_close`（沿用现有 `test_does_nothing_when_hyperliquid_live` 语义）；  
       - 纸上模式下，Kill-Switch 激活与否都不改变 SL/TP 行为。  

4. **AC4 – 日志与审计的一致性（与 7.2.1 / 7.2.3 对齐）**  
   - 当 Kill-Switch 激活期间由 SL/TP 触发 close 时：  
     - 现有的结构化日志与 `trade_history.csv` / `portfolio_state.csv` 记录中，能够区分「由 SL/TP 引发的风险收缩」与「由 LLM entry 被 Kill-Switch 阻止」两类事件；  
     - 如无需新增字段，则在 Dev Notes 中记录清晰的审计路径说明（从 RiskControlState → check_risk_limits → check_stop_loss_take_profit / execute_close → CSV/日志），并通过测试或手工检查验证链路闭环；  
     - 如确需新增字段（例如在 `trade_history.csv` 中标记 `exit_reason=stop_loss|take_profit|manual|risk_control`），则：  
       - 更新相应写入/读取逻辑与架构文档中的字段说明；  
       - 保证旧数据或缺失字段场景下仍然向后兼容。  

5. **AC5 – 测试覆盖与回归**  
   - 在以下测试文件中增加或更新用例，覆盖 Kill-Switch + SL/TP 组合场景：  
     - `tests/test_stop_loss_take_profit.py`：在 `kill_switch_active=True` 时复用/扩展现有 long/short 场景；  
     - `tests/test_risk_control_integration.py`：新增一组集成测试，从 `check_risk_limits(...)` → `_run_iteration()` → `check_stop_loss_take_profit()` → `execute_close()` 路径验证 AC1/AC2。  
   - 所有既有 Kill-Switch 相关测试（7.2.1 / 7.2.2 / 7.2.3）以及 SL/TP 测试均需继续通过；如需调整，仅允许在期望值层面做非行为性更新（例如新增日志字段）。

## Tasks / Subtasks

- [x] **Task 1 – 梳理 Kill-Switch + SL/TP 数据流与职责边界（AC1, AC2, AC3）**  
  - [x] 1.1 基于 `docs/architecture/03-data-flow.md` 与当前 `bot._run_iteration()`，绘制从 RiskControlState → `check_risk_limits(...)` → `allow_entry` → `check_stop_loss_take_profit()` → `process_ai_decisions(...)` → `TradeExecutor` 的简化数据流。  
  - [x] 1.2 在 Dev Notes 中用文字明确：Kill-Switch 只影响 entry 决策，不影响 close/SLTP；Hyperliquid 实盘模式下由交易所负责触发单。  
  - [x] 1.3 对照 `tests/test_stop_loss_take_profit.py` 总结当前 SL/TP 触发规则，作为后续测试与实现的权威基线。

- [x] **Task 2 – 设计并实现 Kill-Switch + SL/TP 集成测试（AC1, AC2, AC3, AC5）**  
  - [x] 2.1 在 `tests/test_stop_loss_take_profit.py` 中新增至少 2–3 个用例，显式设置 `risk_control_state.kill_switch_active=True`（或通过注入 / mock）验证：SL/TP 行为不因 Kill-Switch 改变。  
  - [x] 2.2 在 `tests/test_risk_control_integration.py` 中新增专门的测试类（例如 `KillSwitchAndStopLossTakeProfitIntegrationTests`），覆盖：  
       - Kill-Switch 激活 + 有持仓 + 价格触及 SL/TP → 仍发生 close；  
       - Kill-Switch 未激活时行为与基线一致；  
       - Hyperliquid `is_live=True` 时，无论 Kill-Switch 状态如何，SL/TP 逻辑保持 no-op。  
  - [x] 2.3 如需要，通过 mock `bot.check_stop_loss_take_profit` 与 `TradeExecutor.execute_close` 等，减少对真实交易所连接与 I/O 的依赖。

- [x] **Task 3 – 最小必要的实现或重构（AC1, AC2, AC3, AC4）**  
  - [x] 3.1 在不破坏现有行为的前提下，检查并必要时调整 `_run_iteration()` 中风控检查、SL/TP 检查与 LLM 决策处理的顺序与依赖（保持「先 SL/TP、后 LLM entry/close」的直觉）。  
  - [x] 3.2 如发现 Kill-Switch 与 SL/TP 路径间存在隐式耦合或重复判断，做最小重构以保持单一职责，并在 Dev Notes 中记录设计决策。  
  - [x] 3.3 仅在确有必要时扩展 CSV/日志字段，用于更好地区分「风险收缩」与「entry 被阻止」事件；所有变更都需在架构文档中补充说明。  

- [x] **Task 4 – 回归测试与文档更新（AC4, AC5）**  
  - [x] 4.1 运行完整测试套件（`./scripts/run_tests.sh`），确保所有 Kill-Switch / SLTP / 执行层相关测试通过。  
  - [x] 4.2 如对日志或 CSV schema 有变更，更新 `docs/architecture/07-implementation-patterns.md` 或相关数据文档，保持审计路径清晰。  
  - [x] 4.3 在本 Story 的 Change Log 中记录最终实现与测试情况，供后续 Story 与 Epic 回顾使用。

## Dev Notes

### Requirements & Context Summary

- 本 Story 属于 **Epic 7.2: Kill-Switch 核心功能**，对应 `sprint-status.yaml` 中的 key：`7-2-4-确保-sl-tp-在-kill-switch-期间正常工作`。  
- 需求主要来源：  
  - PRD 《风控系统增强 - 产品需求文档》（`docs/prd-risk-control-enhancement.md`）中关于 Kill-Switch 与 SL/TP 的功能条款：  
    - **FR7–FR8**：Kill-Switch 激活后拒绝所有 `signal=entry`，但保留 `signal=close` 与 SL/TP 检查继续执行；  
    - **FR19–FR20**：所有风控状态变更与事件需要在日志与 `ai_decisions.csv` 中留下可审计轨迹。  
  - Epic 文档 `docs/epics.md` 中 Epic 7.2/Story 7.2.4 的描述：  
    - 「确保 SL/TP 在 Kill-Switch 期间正常工作（迭代细化现有逻辑与日志）」，强调在已实现 Kill-Switch / 信号过滤基础上，对 SL/TP 行为做专门的验证与加固。  
  - Tech Spec `docs/sprint-artifacts/tech-spec-epic-7-1.md` 与 Epic 7.1 Retro 中对 `RiskControlState`、`check_risk_limits(...)` 和主循环集成的定义：  
    - Kill-Switch 状态集中在 `core/risk_control.py` / `core/state.py`；  
    - 主循环通过 `check_risk_limits(...)` 获取「是否允许 entry」的结果，并在迭代开始阶段执行。  
  - 既有 Story 7.2.1 / 7.2.2 / 7.2.3 已经实现：  
    - Kill-Switch 激活/解除逻辑与 env/持久化优先级；  
    - 主循环与执行层的 entry 阶段 Kill-Switch 防护；  
    - 基于 `allow_entry` 的信号过滤与被阻止 entry 的日志/CSV 审计记录。  
- 本 Story 在上述基础上，聚焦「当 Kill-Switch 激活时，SL/TP 相关行为完全保持可预期且可验证」，避免后续演进中在此边界产生回归。

### Learnings from Previous Story

**From Story 7-2-3-实现信号过滤逻辑 (Status: done)**

- **现有能力与约束**  
  - Kill-Switch 激活与其他风控条件在 `core.risk_control.check_risk_limits(...)` 中汇总为布尔标志（例如 `allow_entry: bool`），由 `_run_iteration()` 传入 `process_ai_decisions(...)`；  
  - 当 `allow_entry=False` 时，`process_ai_decisions(...)` 会：  
    - 统一阻止所有 `signal="entry"` 的决策；  
    - 记录结构化 WARNING 日志，包含 `coin`、`signal`、`allow_entry`、`kill_switch_active`、`reason` 等字段；  
    - 在 `ai_decisions.csv` 中追加一条 `signal="blocked"` 的审计记录，`reasoning` 字段以 `RISK_CONTROL_BLOCKED: ...` 开头，保持向后兼容。  
  - `TradeExecutor.execute_entry(...)` 在执行层仍保留 Kill-Switch 最终守卫（defense-in-depth），通过 `is_kill_switch_active` 回调获取状态。  

- **对本 Story 的直接启示**  
  - **Kill-Switch 语义已经在 entry 路径上充分实现并验证**：本 Story 不应在 SL/TP 路径上重复 Kill-Switch 判定，而是只需确认「Kill-Switch 不影响 SL/TP」。  
  - 现有日志与 CSV 审计路径已经能够清晰区分「entry 被阻止」事件；本 Story 更关注「在 Kill-Switch 期间，由 SL/TP 引发的 close 是否如预期执行」，必要时只需补充少量标记字段或文档说明。  
  - 任何为了满足本 Story 而对 SL/TP 逻辑的修改，都必须与 7-2-3 已建立的 entry 过滤逻辑与测试保持一致，不引入新的分叉路径或双重判断。  

### Architecture & Implementation Constraints

- **模块边界**  
  - 风控状态与 Kill-Switch 逻辑：`core/risk_control.py` / `core/state.py`；  
  - 主循环与决策处理：`bot.py` / `core/trading_loop.py`；  
  - SL/TP 执行逻辑：`execution/routing.py::check_stop_loss_take_profit_for_positions` + `bot.check_stop_loss_take_profit()`；  
  - 执行层与最终守卫：`execution/executor.py::TradeExecutor.execute_entry/execute_close`；  
  - 日志与通知：`notifications/logging.py`、`notifications/telegram.py`。  

- **必须遵守的约束**  
  - 禁止在 SL/TP 路径中直接读取或修改 `RiskControlState`，以免破坏「风控决策集中在 core/ 层」的设计；如确需使用 Kill-Switch 状态，应通过显式参数传入，并在 Dev Notes 中记录理由。  
  - 不得在 `strategy/`、`llm/`、`display/` 等层新增任何与 Kill-Switch 或 SL/TP 相关的分支逻辑。  
  - 不得改变 Hyperliquid 实盘路径 `hyperliquid_trader.is_live=True` 时的「本地 SL/TP 不执行」语义，只能通过文档与测试进一步明确其行为。  

### Project Structure Notes

- 预计主要涉及文件：  
  - `bot.py` —— 核查并必要时调整 `_run_iteration()` 中风控检查与 `check_stop_loss_take_profit()` 调用顺序；  
  - `execution/routing.py` —— 复查 `check_stop_loss_take_profit_for_positions(...)` 行为，确保在 Kill-Switch 场景下不引入额外耦合；  
  - `core/trading_loop.py` —— 如有与 SL/TP 记录相关的辅助函数（例如 `log_ai_decision` 或 trade logging），在需要时补充审计标记；  
  - `tests/test_stop_loss_take_profit.py` —— 扩展单元测试覆盖 Kill-Switch 相关场景；  
  - `tests/test_risk_control_integration.py` —— 新增从 RiskControlState 到 SL/TP 执行路径的集成测试。  

### References

- [Source: docs/prd-risk-control-enhancement.md#Kill-Switch（紧急停止）]  
- [Source: docs/prd-risk-control-enhancement.md#功能需求]  
- [Source: docs/epics.md#Epic-7.2-Kill-Switch-核心功能]  
- [Source: docs/sprint-artifacts/tech-spec-epic-7-1.md]  
- [Source: docs/sprint-artifacts/7-2-1-实现-kill-switch-激活逻辑.md]  
- [Source: docs/sprint-artifacts/7-2-2-实现-kill-switch-解除逻辑.md]  
- [Source: docs/sprint-artifacts/7-2-3-实现信号过滤逻辑.md]  
- [Source: docs/architecture/03-data-flow.md]  
- [Source: docs/architecture/07-implementation-patterns.md]  
- [Source: tests/test_stop_loss_take_profit.py]  
- [Source: tests/test_risk_control_integration.py]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/7-2-4-确保-sl-tp-在-kill-switch-期间正常工作.context.xml

### Agent Model Used

- Cascade

### Debug Log References

- 本 Story 通过以下测试覆盖 Kill-Switch + SL/TP 关键路径，可通过 `pytest -k "stop_loss_take_profit or KillSwitchAndStopLossTakeProfitIntegrationTests"` 进行快速回归：
  - `tests/test_stop_loss_take_profit.py::CheckStopLossTakeProfitTests::test_kill_switch_active_does_not_block_sl_tp_in_paper_mode`  
  - `tests/test_stop_loss_take_profit.py::CheckStopLossTakeProfitTests::test_kill_switch_active_does_not_change_hyperliquid_live_noop`  
  - `tests/test_risk_control_integration.py::KillSwitchAndStopLossTakeProfitIntegrationTests::test_run_iteration_triggers_sl_tp_close_when_kill_switch_active`  

  典型 grep 策略：
  - `grep -n "Stop loss hit" -r .` 观察由 SL 触发的平仓日志；
  - `grep -n "Kill-Switch active (executor guard)" -r .` 与 `grep -n "entry blocked" -r .` 区分 entry 被 Kill-Switch 拦截的路径；
  - 结合 `trade_history.csv` 中 CLOSE 记录的 `reason` 字段，确认由 SL/TP 引发的风险收缩事件。

### Completion Notes List

- [Done] 在不修改核心业务逻辑的前提下，通过新增/扩展测试验证：Kill-Switch 激活期间，纸上模式下的 SL/TP 行为与基线完全一致，仅 entry 被阻止；Hyperliquid 实盘模式在 Kill-Switch 激活时依旧保持 SL/TP no-op 语义。  
- [Done] 在 `tests/test_risk_control_integration.py` 中补充 `_run_iteration()` 级联集成测试，证明主循环在 Kill-Switch 激活时仍然执行 `check_stop_loss_take_profit()` 并触发平仓；运行 `./scripts/run_tests.sh` 全量测试全部通过。

### File List

- 修改的测试文件：
  - `tests/test_stop_loss_take_profit.py`  
  - `tests/test_risk_control_integration.py`

## Change Log

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 0.1 | 2025-11-30 | Nick (SM) | 初始 Story 草稿（通过 create-story 工作流生成，定义 Kill-Switch 期间 SL/TP 行为与测试要求） |
| 0.2 | 2025-11-30 | Cascade (Dev Agent) | 按 AC1–AC5 增加 Kill-Switch + SL/TP 组合场景测试，并验证在 Kill-Switch 激活时 SL/TP 行为与基线一致，仅 entry 被阻止；更新 Story 状态为 review。 |
| 0.3 | 2025-11-30 | Nick (SM) | Senior Developer Review (AI)：验证 AC 与任务均已实现，无需进一步代码改动，建议后续如增加 exit_reason 字段可单独立 Story 跟进。 |

## Senior Developer Review (AI)

### Reviewer & Date

- Reviewer: Nick (via Cascade AI assistant)
- Date: 2025-11-30

### Outcome

- **Outcome:** Approve （无代码层面的修改请求）  
- **理由概述：**
  - 所有 Acceptance Criteria（AC1–AC5）均可在现有代码与测试中找到明确证据；
  - 所有标记为完成的 Tasks/Subtasks 在代码或文档中都有对应实现或验证工作，无「打勾未实现」情况；
  - 新增测试遵循现有测试风格，无明显架构或安全风险。

### Acceptance Criteria Coverage

| AC # | 描述（摘要） | 状态 | 实现与证据（文件:位置 / 测试） |
|------|--------------|------|--------------------------------|
| AC1 | Kill-Switch 激活时仍执行 SL/TP 检查 | **IMPLEMENTED** | 主循环 `_run_iteration()` 始终在 `check_risk_limits(...)` 之后调用 `bot.check_stop_loss_take_profit()`（`bot.py` 623–662 行）；`check_stop_loss_take_profit()` 仅基于 `hyperliquid_trader.is_live` 决定是否调用 `execution.routing.check_stop_loss_take_profit_for_positions(...)`，未引入 Kill-Switch 分支（`bot.py` 451–456，`execution/routing.py` 475–531）；基线 SL/TP 行为由 `tests/test_stop_loss_take_profit.py::CheckStopLossTakeProfitTests` 中 long/short 场景验证，新增加 `test_kill_switch_active_does_not_block_sl_tp_in_paper_mode` 证明 Kill-Switch 激活时行为保持一致。 |
| AC2 | Kill-Switch 仅阻止 entry，不阻止 close/SLTP | **IMPLEMENTED** | entry 路径通过 `core.risk_control.check_risk_limits(...)` 返回 `allow_entry`，在 `bot.process_ai_decisions(...)` 中统一过滤 `signal="entry"`，对 close/hold 不做阻断（`bot.py` 377–449）；`SignalFilteringIntegrationTests`（`tests/test_risk_control_integration.py`）中的 `test_process_ai_decisions_blocks_entry_when_allow_entry_false`、`allows_close_when_allow_entry_false`、`allows_hold_when_allow_entry_false` 分别验证 entry 被阻止而 close/hold 继续执行；本 Story 新增 `_run_iteration` 级别测试 `KillSwitchAndStopLossTakeProfitIntegrationTests::test_run_iteration_triggers_sl_tp_close_when_kill_switch_active`，证明 Kill-Switch 激活时，SL/TP 路径仍会触发 `execute_close(...)`。 |
| AC3 | Hyperliquid 实盘模式下 SL/TP 与 Kill-Switch 协同 | **IMPLEMENTED** | `execution.routing.check_stop_loss_take_profit_for_positions(...)` 在 `hyperliquid_is_live=True` 时直接 `return`，保证本地 SL/TP 在实盘路径中为 no-op（`execution/routing.py` 488–489）；`tests/test_stop_loss_take_profit.py::test_does_nothing_when_hyperliquid_live` 验证 Hyperliquid 实盘模式下不调用 `fetch_market_data` / `execute_close`；新增 `test_kill_switch_active_does_not_change_hyperliquid_live_noop` 验证在 Kill-Switch 激活时该 no-op 语义保持不变（不额外引入 Kill-Switch 耦合）。 |
| AC4 | 日志与审计的一致性 | **IMPLEMENTED（保持现有设计）** | entry 被 Kill-Switch 阻止的日志与 `ai_decisions.csv` 记录已在 Story 7.2.3 中实现：`bot.process_ai_decisions(...)` 对 `allow_entry=False` 情况记录结构化 WARNING 日志（包含 `coin`、`signal`、`allow_entry`、`kill_switch_active`、`reason` 等），并追加 `signal="blocked"` 的审计记录，`reasoning` 字段以 `RISK_CONTROL_BLOCKED: ...` 开头（`bot.py` 420–444）；`SignalFilteringIntegrationTests::test_blocked_entry_log_contains_required_fields` 与 `test_blocked_entry_csv_record_contains_risk_control_marker` 在 `tests/test_risk_control_integration.py` 中验证该行为。由此可区分「entry 被 Kill-Switch 阻止」与正常 SL/TP close；本 Story 未对 trade_history.csv 结构做变更，仅在 Dev Notes 中记录了审计链路。 |
| AC5 | 测试覆盖与回归 | **IMPLEMENTED** | 针对 Kill-Switch + SL/TP 的新测试：`tests/test_stop_loss_take_profit.py` 中新增 2 个组合场景；`tests/test_risk_control_integration.py` 新增 `KillSwitchAndStopLossTakeProfitIntegrationTests` 覆盖从 `check_risk_limits(...)` → `_run_iteration()` → `check_stop_loss_take_profit()` → `execute_close()` 的路径；全量测试通过（`./scripts/run_tests.sh` 输出 476 passed）。 |

**AC 总结：** 5/5 个 Acceptance Criteria 均已实现并有对应代码与测试证据。

### Tasks / Subtasks Completion Validation

| Task | Marked As | Verified As | 证据与说明 |
|------|-----------|-------------|------------|
| Task 1 – 梳理 Kill-Switch + SL/TP 数据流与职责边界 | Completed | VERIFIED COMPLETE | Story Dev Notes 中对模块边界与数据流进行了详细总结（`Dev Notes` 中 *Requirements & Context Summary*、*Architecture & Implementation Constraints*、*Project Structure Notes*），并引用 `bot._run_iteration`、`core/risk_control.check_risk_limits`、`bot.check_stop_loss_take_profit` 与 `execution.routing.check_stop_loss_take_profit_for_positions` 的具体职责；与 Story Context 中的 `codeArtifact` 列表保持一致。 |
| Task 2 – 设计并实现 Kill-Switch + SL/TP 集成测试 | Completed | VERIFIED COMPLETE | 新增/扩展测试位于 `tests/test_stop_loss_take_profit.py` 与 `tests/test_risk_control_integration.py`；测试名称和行为与 Task 描述逐条对应（包括 Kill-Switch 激活/未激活、Hyperliquid 实盘/纸上模式组合场景），并在 Story Dev Notes 的 Debug Log References 中列出。 |
| Task 3 – 最小必要的实现或重构 | Completed | VERIFIED COMPLETE | 通过审查现有实现确认无需对 `_run_iteration()` 和 SL/TP 路径做代码级修改即可满足本 Story AC：Kill-Switch 已通过 `check_risk_limits(...)` + `allow_entry` 在 entry 路径实现，SL/TP 路径未引入 Kill-Switch 分支；Dev Notes 中明确记录了这一决策以及对架构约束的遵守情况（不在 SL/TP 路径读取 `RiskControlState`，不更改 Hyperliquid 实盘语义）。 |
| Task 4 – 回归测试与文档更新 | Completed | VERIFIED COMPLETE | `./scripts/run_tests.sh` 全量测试通过（476 passed）；Story Dev Notes 的 Debug Log References 与 Change Log 0.2/0.3 行记录了测试与评审完成情况；未对架构文档或 CSV schema 做变更，符合「最小必要修改」原则。 |

**Task 总结：** 4/4 个标记完成的 Task/Subtask 均有对应实现或验证证据，未发现「打勾未实现」或可疑项。

### Test Coverage and Gaps

- **覆盖点：**
  - 单元测试：`CheckStopLossTakeProfitTests` 覆盖 long/short 各类 K 线 high/low 场景，包括 Kill-Switch 激活/未激活、Hyperliquid 实盘/纸上模式组合；
  - 集成测试：`KillSwitchBlocksEntryIntegrationTests` + `SignalFilteringIntegrationTests` + `KillSwitchAndStopLossTakeProfitIntegrationTests` 联合验证：
    - Kill-Switch 激活时 entry 被统一阻止；
    - close/hold 与 SL/TP 路径在 Kill-Switch 激活时保持正常工作；
    - `_run_iteration()` 在 Kill-Switch 激活时仍会执行 SL/TP 检查并触发 `execute_close(...)`。
  - 回归：`./scripts/run_tests.sh` 覆盖全部 476 个测试用例。
- **潜在空白（可选后续 Story）：**
  - 如未来引入更结构化的 `exit_reason` 字段到 `trade_history.csv` 或状态 JSON，可补充针对「由 SL/TP 引发的 close 事件」的 CSV 级断言（当前通过 `reason` 文本前缀和日志已可区分）。

### Architectural Alignment

- **层次与职责：**
  - SL/TP 逻辑仍集中在 `bot.check_stop_loss_take_profit` 与 `execution.routing.check_stop_loss_take_profit_for_positions`；
  - 风控与 Kill-Switch 状态管理集中在 `core/risk_control.py` / `core/state.py`，未在 SL/TP 路径直接读取或修改 `RiskControlState`；
  - Hyperliquid 实盘路径在 SL/TP 上保持 no-op，符合架构与 PRD 的语义约束。
- **一致性：**
  - 新增测试遵循现有测试结构与命名模式；
  - 未引入新的跨层依赖或耦合点，依旧通过既有 API（如 `check_risk_limits`、`process_ai_decisions`、`TradeExecutor`）进行验证。

### Security Notes

- 本 Story 仅增加测试与文档，不涉及新外部依赖、鉴权逻辑或敏感配置处理；
- 现有 Kill-Switch 与风控逻辑已通过其他 Story（7.2.1–7.2.3）和测试验证，不增加新的安全面。

### Action Items

**Code Changes Required:**

- 无。（本次评审不提出必须修改的代码项。）

**Advisory Notes:**

- Note: 若未来在 `trade_history.csv` / 状态文件中新增结构化字段（例如 `exit_reason=stop_loss|take_profit|manual|risk_control`），建议在对应 Story 中：
  - 扩展写入/读取逻辑，并在 `docs/architecture/07-implementation-patterns.md` 中补充分字段描述；
  - 增加针对该字段的测试用例，以区分「由 SL/TP 触发的风险收缩」与「entry 被 Kill-Switch 阻止」事件。 
