"""Portabla scenarier och kontroll av indata till användargränssnittet."""
from datetime import datetime, timezone
import json
import math

from stella_model import Model

FORMAT = "jagersro-stella-scenario/v1"


def export_scenario(model: Model, preset: str, overrides: dict, curves: dict) -> bytes:
    parameters = model.parameters(preset) | overrides
    data = {"format": FORMAT, "source_sha256": model.data["source"]["sha256"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "preset": preset, "parameters": parameters, "curves": curves}
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def import_scenario(model: Model, content: bytes) -> tuple[str, dict, dict]:
    if len(content) > 2_000_000:
        raise ValueError("Scenariofilen är för stor.")
    data = json.loads(content.decode("utf-8-sig"))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("Filen är inte en scenariofil från denna app.")
    if data.get("source_sha256") != model.data["source"]["sha256"]:
        raise ValueError("Scenariot bygger på en annan version av Stella-modellen.")
    preset = data.get("preset")
    if preset not in {"saved", "equations"}:
        raise ValueError("Okänt grundscenario.")
    params, curves = data.get("parameters", {}), data.get("curves", {})
    if not isinstance(params, dict) or not isinstance(curves, dict):
        raise ValueError("Parametrar och kurvor ska vara objekt.")
    editable = {v["key"] for v in model.editable()}
    baseline = model.parameters(preset)
    changes = {}
    for key, value in params.items():
        if key not in editable or isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"Ogiltig parameter: {key}")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"Ogiltigt tal för {key}")
        if value != baseline.get(key): changes[key] = value
    for key, ys in curves.items():
        i = model.index.get(key)
        if i is None or i in model.aliases or "lookup" not in model.variables[i]:
            raise ValueError(f"Okänd kurva: {key}")
        expected = model.variables[i]["lookup"]["y"]
        if not isinstance(ys, list) or len(ys) != len(expected) or any(
                isinstance(y, bool) or not isinstance(y, (float, int)) or not math.isfinite(y) for y in ys):
            raise ValueError(f"Ogiltiga kurvpunkter: {key}")
    return preset, changes, curves


def parameter_checks(model: Model, preset: str, overrides: dict) -> list[str]:
    """Konkreta konsistenskontroller, utan att ändra användarens värden."""
    p = model.parameters(preset) | overrides
    messages = []
    for module, suffix in [("Byggnader", "Flerbostadshus"), ("Kontor", "Kontor")]:
        keys = [f"{module}.Andel_{kind}_{suffix}" for kind in [
            "betonghus", "klimatförbättrad_betonghus", "stålhus", "klimatförbättrad_stålhus", "trähus"]]
        values = [p[k] for k in keys]
        if any(x < 0 or x > 1 for x in values) or not math.isclose(sum(values), 1, abs_tol=1e-7):
            messages.append(f"Stomandelarna i {module} ska vara mellan 0 och 1 och summera till 1 (nu {sum(values):.4g}).")
    keys = [k for k in p if k.startswith("Scarborough_modell.Andel_")]
    if keys and (any(p[k] < 0 or p[k] > 1 for k in keys) or
                 not math.isclose(sum(p[k] for k in keys), 1, abs_tol=1e-7)):
        messages.append("Kostandelarna i Scarborough-modellen ska anges som andelar 0–1 och summera till 1, även om originalnamnen anger %.")
    for key in ["Invånare.Bostadsyta_per_invånare_(m2_BTA/pers)",
                "ROT.Bostadsyta_per_invånare_i_befintliga_bostäder_(n)",
                "Energi.Genomsnittlig_antal_vån._i_stadsdel",
                "Mobilitet.Medelstorlek_hushåll_Flerbostadshus_(m2_Atemp)",
                "Global_klimatbudget.Global_CO2-pool_(Gton_CO2e)"]:
        if key in p and p[key] <= 0:
            messages.append(f"{model.variables[model.index[key]]['name']} behöver vara större än 0.")
    for key, value in p.items():
        v = model.variables[model.index[key]]
        text = v["name"].lower()
        if (text.startswith(("av/på", "på/av")) or key == "Energi.Solelsproduktion_1/0") and value not in {0, 1}:
            messages.append(f"{v['name']} ska vara 0 eller 1.")
    return messages
