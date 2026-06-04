import re

with open("01-功能包-packages/trader/scripts/run_analysis.py", "r") as f:
    code = f.read()

with open("01-功能包-packages/trader/scripts/new_render.py", "r") as f:
    new_render = f.read()

# Replace everything from def render_markdown(r: dict[str, Any]) -> str: to just before def _pool_count() -> int:
pattern = re.compile(r"def render_markdown\(r: dict\[str, Any\]\) -> str:.*?(?=def _pool_count)", re.DOTALL)

if pattern.search(code):
    new_code = pattern.sub(lambda m: new_render + "\n\n", code)
    with open("01-功能包-packages/trader/scripts/run_analysis.py", "w") as f:
        f.write(new_code)
    print("Patched successfully.")
else:
    print("Could not find pattern.")
