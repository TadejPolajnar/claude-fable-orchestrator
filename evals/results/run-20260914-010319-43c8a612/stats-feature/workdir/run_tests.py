import importlib
import sys
from pathlib import Path


def main():
    root = Path(__file__).parent
    sys.path.insert(0, str(root))
    total = 0
    failed = 0
    for module_path in sorted(root.glob("test_*.py")):
        module = importlib.import_module(module_path.stem)
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            func = getattr(module, name)
            if not callable(func):
                continue
            total += 1
            try:
                func()
                print(f"PASS {module_path.stem}.{name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {module_path.stem}.{name}: {exc}")
    print(f"{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
