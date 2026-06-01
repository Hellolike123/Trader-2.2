# 新增需求：trader 加 --cost 参数

现在 trader 没有 --cost 参数，用户没法输入成本价。

## 需要改的地方：

1. **final_report.py 加 --cost 参数**（float，可选）
   ```python
   parser.add_argument("--cost", type=float, help="Your cost basis")
   ```

2. **build_report() 加 cost 参数**
   ```python
   def build_report(target: str, cost: float | None = None)
   ```

3. **cost 传给 evaluate_position_state()**
   ```python
   has_position = cost is not None
   entry_price = cost if cost is not None else 原来的逻辑
   ```

4. **cost 加入 __FACTS__ 输出**
   ```python
   "cost": args.cost
   ```

## 改完之后用户可以：
```bash
trader script --target 南网科技 --cost 60.00
```
系统就会用"已有持仓"模式分析
