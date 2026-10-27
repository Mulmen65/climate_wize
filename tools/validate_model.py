"""Kör den fullständiga kontrollen: python tools/validate_model.py."""
from pathlib import Path
import csv
import json
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from stella_model import Model
from validation import compare_reference, summary


def main():
    model = Model()
    result = model.run()
    rows = compare_reference(model, result)
    report = summary(rows)
    report.update({"python_version": platform.python_version(), "numpy_version": np.__version__,
                   "model_sha256": model.data["source"]["sha256"], "unresolved_variables": result.issues,
                   "unique_variable_definitions": len(model.keys), "alias_connections": len(model.aliases),
                   "independent_variables": len(model.keys)-len(model.aliases),
                   "stocks": len(model.stock_indices), "editable_parameters": len(model.editable()),
                   "saved_controls": len(model.controls), "timesteps": len(result.time),
                   "seconds": round(result.elapsed, 3),
                   "key_results_2050": {k: float(result.series(k)[-1]) for k in model.keys if k.startswith("TOTAL.")}})
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "validation_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (ROOT / "docs" / "kontroll_mot_stella.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["passed_series"] != report["compared_series"] or result.issues:
        raise SystemExit(1)


if __name__ == "__main__": main()
