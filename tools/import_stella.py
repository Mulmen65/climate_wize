"""Uppdatera beräkningsunderlaget från en ny STMX-fil, med valfri ISDB-referens.

python tools/import_stella.py "modell.stmx" --isdb "modell.isdb"
Granska och testa alltid en ny modellversion före publicering.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from stella_model import import_stmx, Model, name


def extract_reference(isdb: Path, model: Model, destination: Path):
    con = sqlite3.connect(isdb.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        run = con.execute("SELECT * FROM runs WHERE complete=1 ORDER BY id DESC LIMIT 1").fetchone()
        if run is None: raise ValueError("ISDB-filen saknar en komplett körning.")
        s = model.data["simulation"]
        if (s["start"], s["stop"], s["dt"]) != (run["starttime"], run["stoptime"], run["dt"]):
            raise ValueError("Tidsinställningarna skiljer sig mellan STMX och ISDB.")
        arrays = {}
        meta = {"run": {k: run[k] for k in ["name", "starttime", "stoptime", "dt", "saveint", "method", "modified"]},
                "source_file": isdb.name, "source_sha256": hashlib.sha256(isdb.read_bytes()).hexdigest(),
                "model_sha256": model.data["source"]["sha256"], "series": []}
        sql = ("SELECT v.name,m.name AS module,d.numvals,d.data FROM run_data d "
               "JOIN variables v ON v.id=d.variable JOIN models m ON m.id=v.model "
               "WHERE run=? ORDER BY v.id")
        for row in con.execute(sql, (run["id"],)):
            key = model.resolve(name(row["module"]) + "." + name(row["name"]))
            code = f"v{len(arrays):04}"
            values = np.frombuffer(row["data"], dtype="<f8").copy()
            if len(values) != row["numvals"]: raise ValueError(f"Skadat datalager för {key}")
            arrays[code] = values
            meta["series"].append({"key": key, "array": code, "length": len(values)})
        np.savez_compressed(destination / "reference.npz", **arrays)
        (destination / "reference.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stmx", type=Path)
    parser.add_argument("--isdb", type=Path)
    args = parser.parse_args()
    data = import_stmx(args.stmx)
    model = Model(data)
    if model.issues:
        raise ValueError(f"Konverteringen innehåller ekvationer som inte stöds: {model.issues}")
    dest = ROOT / "model"
    dest.mkdir(exist_ok=True)
    (dest / "model.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.isdb:
        extract_reference(args.isdb, model, dest)
        for p in [ROOT / "docs" / "validation_summary.json", ROOT / "docs" / "kontroll_mot_stella.csv"]:
            p.unlink(missing_ok=True)
    else:
        # Gamla kontrollresultat får inte framstå som validering av en ny källa.
        for p in [dest / "reference.npz", dest / "reference.json",
                  ROOT / "docs" / "validation_summary.json", ROOT / "docs" / "kontroll_mot_stella.csv"]:
            p.unlink(missing_ok=True)
    print(f"Konverterat {len(model.keys)} variabler. Kör tester och validate_model.py innan publicering.")


if __name__ == "__main__": main()
