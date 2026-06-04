import re

with open("01-功能包-packages/trader/scripts/run_analysis.py", "r") as f:
    code = f.read()

with open("01-功能包-packages/trader/scripts/new_render.py", "r") as f:
    new_render = f.read()

if "def _load_historical_win_rate" in code:
    pattern = re.compile(r"def _load_historical_win_rate\(.*?(?=def _pool_count)", re.DOTALL)
else:
    pattern = re.compile(r"def render_markdown\(r: dict(?:\[str,\s*Any\])?\) -> str:.*?(?=def _pool_count)", re.DOTALL)

if pattern.search(code):
    new_code = pattern.sub(lambda m: new_render.strip() + "\n\n", code)
    with open("01-功能包-packages/trader/scripts/run_analysis.py", "w") as f:
        f.write(new_code)
    print("Patched successfully.")
else:
    print("Could not find pattern.")
