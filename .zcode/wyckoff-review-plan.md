# Wyckoff 经典信号改动 — 三 Agent 审查计划

## 范围

commit `bb54b30` 的 8 个改动文件：

```
01-功能包-packages/trader/specs/spec-wyckoff-classic-signals.md    ← 需求 spec（审计员专属）
02-共享模块-shared/trader_shared/config.py                          ← 配置常量
02-共享模块-shared/trader_shared/wyckoff_core.py                    ← 检测函数 + score
02-共享模块-shared/trader_shared/fusion_core.py                     ← _wyckoff_to_signal
02-共享模块-shared/tests/test_fusion_core.py
02-共享模块-shared/tests/test_wyckoff_core.py
01-功能包-packages/trader/scripts/final_pool.py
01-功能包-packages/review/scripts/review_core.py
```

---

## Agent 角色与分工

### Agent A — 代码审查员 (Code Inspector)

**职责**: 逐文件审查实现代码，产出原始发现列表。
**不判断**严重度，**不判断**是否被 spec 要求，只报告「我看到了什么」。

**审查清单**:
1. **变量/字段一致性**: spec 里的字段名 vs 代码里的字段名是否一致？
2. **边界条件**: 空输入、数据不足、NaN、None 是否处理？
3. **逻辑错误**: if/else 分支是否覆盖所有情况？优先级是否有冲突？
4. **数据流断裂**: 上游写了但下游没读？下游读了但上游没写？
5. **测试覆盖**: 测试是否只覆盖 happy path？是否有遗漏的 edge case？
6. **硬编码/魔法数字**: 是否有不该硬编码的值被写死？
7. **字符串拼接**: reason 字符串的拼接是否可能产生空值或重复前缀？

**输出格式**（每个发现一条）:
```
[A-N] path:line | 描述 | 上游/下游上下文
```

### Agent B — Bug 判断员 (Bug Judge)

**职责**: 接收 Agent A 的原始发现，逐个判断：
- 是不是真正的 bug？（排除误报）
- 严重度：S / M / L
- 是否需要修复，还是已知约束？

**判断规则**:
- S = 阻塞级：会导致错误信号、错误输出、系统崩溃
- M = 逻辑级：功能部分生效/不生效，但不会崩溃
- L = 风格/防御级：不影响功能，但影响可维护性
- 标记「误报」的发现直接丢弃，不进入最终报告

**输出格式**:
```
[B-N] [A-N] | 结论: 真bug/误报 | 严重度: S/M/L | 原因
```

### Agent C — 需求审计员 (Requirement Auditor)

**职责**: 对照 spec，检查需求是否完全落实。
**不审查实现细节**，只关心「spec 说要了但没有」。

**审计清单**:
1. spec 中列出的 8 个信号全部有检测代码吗？
2. spec 中的优先级表 vs `_wyckoff_to_signal` 的 if 链顺序一致吗？
3. spec 中的置信度表 vs 代码中硬编码的置信度一致吗？
4. spec 中的 `calculate_wyckoff_score` 权重表，代码里全部实现了吗？
5. spec 中提到的下游消费方（final_pool / review_core），都更新了吗？
6. spec 中的测试表格，实际测试用例是否全覆盖？
7. 有没有 spec 说了但代码里完全缺失的部分？

**输出格式**:
```
[C-N] 文件: 路径:行 | 需求: spec 描述 | 现状: 代码实际行为 | 结论: 已落实/部分落实/缺失
```

---

## 执行顺序

1. **Agent A 和 Agent C 并行开始**（各自独立审查）
2. Agent A 完成后输出原始发现列表
3. Agent B 收到 Agent A 的输出后开始逐条判断
4. Agent C 完成后输出需求差距列表
5. 最终由 Agent B 汇总：
   - 有效 bug 列表（去重 + 按严重度排序）
   - 需求差距列表（来自 Agent C）

---

## 协作协议

- Agent A 和 Agent C **互不通信**，各自独立输出
- Agent B **只读** Agent A 的输出，不自己发现问题
- Agent B 判断为「误报」的发现需附上判断理由
- Agent C 发现「部分落实」需指出差距在哪
- 所有 Agent 使用 `read` 工具读取文件，**不要直接写文件**
- 如果 Agent A 发现某个文件路径不存在或无法读取，记录为 `[A] 文件不可达: path`

---

## 启动方式

> 提示：如果你是一次性启动三个 agent，给每个 agent 的 prompt 应该包含它的角色定义 + 审查清单 + 输出格式。三个 agent 共享同一个 commit 范围作为审查对象。
