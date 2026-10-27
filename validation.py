"""Jämför en ny beräkning med originalresultaten ur den bifogade ISDB-filen."""
from pathlib import Path
import json
import numpy as np

from stella_model import MODEL_PATH, Model, Simulation

RTOL = 1e-9
ATOL = 1e-7


def compare_reference(model: Model, result: Simulation) -> list[dict]:
    if result.preset != "saved" or result.overrides or result.curves:
        raise ValueError("Referenskontrollen kräver det oförändrade sparade grundscenariot.")
    directory = MODEL_PATH.parent
    meta = json.loads((directory / "reference.json").read_text(encoding="utf-8"))
    if meta.get("model_sha256") and meta["model_sha256"] != model.data["source"]["sha256"]:
        raise ValueError("Referensresultaten hör till en annan modellversion.")
    spec = model.data["simulation"]
    if (spec["start"], spec["stop"], spec["dt"]) != (
            meta["run"]["starttime"], meta["run"]["stoptime"], meta["run"]["dt"]):
        raise ValueError("Referenskörningens tidsinställningar stämmer inte med modellen.")
    rows = []
    with np.load(directory / "reference.npz", allow_pickle=False) as reference:
        for series in meta["series"]:
            key = series["key"]
            expected = reference[series["array"]]
            actual = result.series(key)
            if len(expected) not in {1, len(actual)}:
                raise ValueError(f"Tidsserierna har olika längd för {key}")
            delta = np.abs(actual - expected)
            scale = max(float(np.max(np.abs(expected))), 1e-12)
            rows.append({
                "Variabel": key,
                "Godkänd": bool(np.isfinite(actual).all() and np.isfinite(expected).all() and
                                 np.allclose(actual, expected, rtol=RTOL, atol=ATOL)),
                "Stella vid slutår": float(expected[-1]),
                "Python vid slutår": float(actual[-1]),
                "Största absoluta avvikelse": float(np.max(delta)),
                "Avvikelse / seriens största belopp": float(np.max(delta))/scale,
                "Lagrade referensvärden": len(expected),
            })
    return rows


def summary(rows: list[dict]) -> dict:
    return {
        "compared_series": len(rows),
        "passed_series": sum(row["Godkänd"] for row in rows),
        "stored_reference_values": sum(row["Lagrade referensvärden"] for row in rows),
        "max_scale_normalized_error": max(row["Avvikelse / seriens största belopp"] for row in rows),
        "rtol": RTOL, "atol": ATOL,
        "scope": "Oförändrade sparade reglage, 2024–2050, Euler, DT=1/365 år",
    }
