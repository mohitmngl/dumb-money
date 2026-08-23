import py_compile
files = [
    "dumbmoney/indicators.py",
    "dumbmoney/engine.py",
    "dumbmoney/db.py",
    "dumbmoney/basket_screener.py",
    "dumbmoney/string_screener.py",
    "dumbmoney/app.py",
]
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"OK: {f}")
    except py_compile.PyCompileError as e:
        print(f"FAIL: {f}: {e}")
