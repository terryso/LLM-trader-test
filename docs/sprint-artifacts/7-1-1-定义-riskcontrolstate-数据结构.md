# Story 7.1.1: 定义 RiskControlState 数据结构

Status: done

## Story

As a **developer**,
I want **a well-defined data structure for risk control state**,
so that **all risk control features have a consistent state model**.

## Acceptance Criteria

1. **AC1**: `core/risk_control.py` 模块存在且可导入
2. **AC2**: `RiskControlState` dataclass 包含以下字段：
   - `kill_switch_active: bool` (默认 `False`)
   - `kill_switch_reason: Optional[str]` (默认 `None`)
   - `kill_switch_triggered_at: Optional[str]` (默认 `None`)
   - `daily_start_equity: Optional[float]` (默认 `None`)
   - `daily_start_date: Optional[str]` (默认 `None`)
   - `daily_loss_pct: float` (默认 `0.0`)
   - `daily_loss_triggered: bool` (默认 `False`)
3. **AC3**: `to_dict()` 方法返回可 JSON 序列化的字典
4. **AC4**: `from_dict()` 类方法可从字典正确恢复状态
5. **AC5**: 缺失字段时使用合理默认值（不抛出异常）
6. **AC6**: 添加单元测试覆盖所有公共方法

## Tasks / Subtasks

- [x] **Task 1**: 创建 `core/risk_control.py` 模块 (AC: 1)
  - [x] 1.1 创建文件 `core/risk_control.py`
  - [x] 1.2 添加模块文档字符串
  - [x] 1.3 更新 `core/__init__.py` 导出新模块

- [x] **Task 2**: 实现 `RiskControlState` dataclass (AC: 2)
  - [x] 2.1 导入必要依赖 (`dataclasses`, `typing`)
  - [x] 2.2 定义 dataclass 及所有字段
  - [x] 2.3 添加字段文档字符串

- [x] **Task 3**: 实现序列化方法 `to_dict()` (AC: 3)
  - [x] 3.1 使用 `dataclasses.asdict()` 实现
  - [x] 3.2 确保返回值可被 `json.dumps()` 处理

- [x] **Task 4**: 实现反序列化方法 `from_dict()` (AC: 4, 5)
  - [x] 4.1 实现 `@classmethod from_dict()`
  - [x] 4.2 使用 `.get()` 方法处理缺失字段
  - [x] 4.3 为每个字段提供合理默认值

- [x] **Task 5**: 添加单元测试 (AC: 6)
  - [x] 5.1 创建 `tests/test_risk_control.py`
  - [x] 5.2 测试默认值初始化
  - [x] 5.3 测试 `to_dict()` 序列化
  - [x] 5.4 测试 `from_dict()` 反序列化
  - [x] 5.5 测试缺失字段处理
  - [x] 5.6 运行测试确保通过

## Dev Notes

### 架构约束

- **模块位置**: `core/risk_control.py`，遵循现有 `core/` 层组件模式
- **依赖**: 仅使用 Python 标准库 (`dataclasses`, `typing`)，无新增外部依赖
- **命名规范**: 遵循 PEP 8，使用 `snake_case` 函数名和 `PascalCase` 类名

### 实现参考

技术规格中定义的 dataclass 结构：

```python
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class RiskControlState:
    """风控系统状态数据结构。
    
    Attributes:
        kill_switch_active: Kill-Switch 是否激活
        kill_switch_reason: Kill-Switch 触发原因
        kill_switch_triggered_at: Kill-Switch 触发时间 (ISO 8601 字符串)
        daily_start_equity: 当日起始权益
        daily_start_date: 当日起始日期 (YYYY-MM-DD)
        daily_loss_pct: 当日亏损百分比 (负数表示亏损)
        daily_loss_triggered: 是否由每日亏损触发了 Kill-Switch
    """
    kill_switch_active: bool = False
    kill_switch_reason: Optional[str] = None
    kill_switch_triggered_at: Optional[str] = None
    daily_start_equity: Optional[float] = None
    daily_start_date: Optional[str] = None
    daily_loss_pct: float = 0.0
    daily_loss_triggered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典，用于 JSON 持久化。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskControlState":
        """从字典反序列化，处理缺失字段。"""
        return cls(
            kill_switch_active=data.get("kill_switch_active", False),
            kill_switch_reason=data.get("kill_switch_reason"),
            kill_switch_triggered_at=data.get("kill_switch_triggered_at"),
            daily_start_equity=data.get("daily_start_equity"),
            daily_start_date=data.get("daily_start_date"),
            daily_loss_pct=data.get("daily_loss_pct", 0.0),
            daily_loss_triggered=data.get("daily_loss_triggered", False),
        )
```

### 测试策略

- 使用 pytest 框架
- 测试文件: `tests/test_risk_control.py`
- 运行命令: `./scripts/run_tests.sh` 或 `pytest tests/test_risk_control.py -v`

### Project Structure Notes

- 新增文件: `core/risk_control.py`
- 新增测试: `tests/test_risk_control.py`
- 修改文件: `core/__init__.py` (添加导出)

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-7-1.md#Data-Models-and-Contracts]
- [Source: docs/epic-risk-control-enhancement.md#Story-7.1.1]
- [Source: docs/prd-risk-control-enhancement.md#技术设计要点]
- [Source: docs/architecture/07-implementation-patterns.md#7.2-目录与代码结构]

## Dev Agent Record

### Context Reference

- [7-1-1-定义-riskcontrolstate-数据结构.context.xml](./7-1-1-定义-riskcontrolstate-数据结构.context.xml)

### Agent Model Used

Claude 3.5 Sonnet (Cascade)

### Debug Log References

- 实现计划：创建 RiskControlState dataclass，包含 7 个字段，实现 to_dict/from_dict 方法
- 测试策略：14 个测试用例覆盖默认值、序列化、反序列化、缺失字段处理、往返测试

### Completion Notes List

- ✅ 创建 `core/risk_control.py` 模块，定义 `RiskControlState` dataclass
- ✅ 实现 `to_dict()` 方法使用 `dataclasses.asdict()`
- ✅ 实现 `from_dict()` 类方法，使用 `.get()` 处理缺失字段
- ✅ 更新 `core/__init__.py` 导出 `RiskControlState`
- ✅ 创建 `tests/test_risk_control.py`，包含 14 个测试用例
- ✅ 所有 393 个测试通过，无回归问题

### Completion Notes
**Completed:** 2025-11-30
**Definition of Done:** All acceptance criteria met, code reviewed, tests passing

### File List

**NEW:**
- `core/risk_control.py` - RiskControlState dataclass 定义
- `tests/test_risk_control.py` - 单元测试（14 个测试用例）

**MODIFIED:**
- `core/__init__.py` - 添加 RiskControlState 导出

---

## Change Log

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-11-30 | Bob (SM) | 初始草稿 |
| 1.1 | 2025-11-30 | Amelia (Dev) | 实现完成，所有测试通过 |
