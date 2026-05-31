# Fix: Integrate main_force into review output

## Problem

The review skill has main_force detection code (`main_force.py`, `main_force_output.py`) but it's NOT integrated into the final output:

1. `main_force.py` — 主力检测逻辑已实现
2. `main_force_output.py` — 格式化输出已实现
3. `review_core.py` 的 `build_review()` 流程里没有调用它
4. `ai-guide.md` 定义了 main_force 字段要求，但实际 JSON 没有这个字段

## Expected Output

main_force 字段应该包含：
- `main_force.stage` — 吸筹/拉升/派发/不明
- `main_force.confidence` — 置信度
- `main_force.cum_flow_5d_wan` — 5日净流入

## Requirements

1. 在 `review_core.py` 的 `build_review()` 流程中集成 main_force 检测
2. 确保 main_force 数据出现在最终 JSON 输出中
3. 确保渲染流程也使用 main_force 数据
4. 运行测试验证集成正确

## Files to Modify

- `01-功能包-packages/review/scripts/review_core.py` — 集成 main_force 调用
- 可能需要修改渲染文件以使用 main_force 数据

## Verification

1. 运行 review skill 测试
2. 检查输出 JSON 包含 main_force 字段
3. 验证 main_force 数据格式正确
