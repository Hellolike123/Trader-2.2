# Wyckoff Agent 快路径

目标：1 条命令 → 原样贴出威科夫结构卡或池链排序 → 停。禁止先批量读 references。  
硬规则详见同目录 `agent-rules.md`。

## 默认命令（cwd = 本 skill 根目录）

```bash
python3 scripts/final_wyckoff.py --target <NAME>
```

池内吸筹链排序（读 `~/.trader/pool.json` 缓存）：

```bash
python3 scripts/final_wyckoff.py rank
```

仓库根：

```bash
python3 01-功能包-packages/wyckoff/scripts/final_wyckoff.py --target <NAME>
python3 01-功能包-packages/wyckoff/scripts/final_wyckoff.py rank
```

成功 → stdout 原样输出 → 停。  
禁止手写面板；禁止把链进度写成「可执行/宜买」。

## 硬门控（markdown 成功时）

1. 未跑脚本 → 不报威科夫结论
2. 产品定位：人读结构卡，不是自动下单指令
3. 遵守 `agent-rules.md` 微信红线
4. 本 Skill 的 rank ≠ trader 分道

## 按需文档（勿预读）

| 何时 | 读什么 |
|------|--------|
| 格式校验 | `output-template.md` |
| 命令全集 | 本文件即可 |

## Exit

输出完成后即停止。
