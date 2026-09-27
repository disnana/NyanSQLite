"""Print a small GitHub summary for pytest-benchmark artifact directories."""

import json
import sys
from pathlib import Path


def main() -> None:
    root = Path(sys.argv[1])
    results = list(root.rglob("*.json"))
    if not results:
        raise SystemExit(f"No benchmark results in {root}")
    print("| Runner | Benchmark | Median (ms) |")
    print("| --- | --- | ---: |")
    for path in sorted(results):
        for entry in json.loads(path.read_text(encoding="utf-8"))["benchmarks"]:
            print(f"| {path.parent.name} | {entry['name']} | {entry['stats']['median'] * 1000:.3f} |")


if __name__ == "__main__":
    main()
