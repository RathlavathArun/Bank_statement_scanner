import json
import sys
from pathlib import Path

# Add core path to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bank_regression import get_coverage_report


def main():
    report = get_coverage_report()
    report_path = Path(__file__).resolve().parents[1] / "coverage_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("Coverage report generated at:", report_path)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
