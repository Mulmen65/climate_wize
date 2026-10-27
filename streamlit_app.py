"""Streamlit-gränssnitt till Jägersros konverterade Stella-modell."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from scenario import export_scenario, import_scenario, parameter_checks
from stella_model import Model, MODEL_PATH
from validation import compare_reference, summary

ROOT = Path(__file__).resolve().parent
PRESETS = {"Sparade reglage i Stella": "saved", "Ekvationernas grundvärden": "equations"}
PRESET_LABELS = {v: k for k, v in PRESETS.items()}
KEYS = {
    "personligt": "TOTAL.MODUL_1",
    "byggd_miljo": "TOTAL.MODUL_2",
    "balansering": "TOTAL.MODUL_3",
    "budget": "TOTAL.Klimatbudget_(CO2e)",
    "offentligt": "TOTAL.Ack._offentliga_klimatutsläpp_(ton_CO2)",
    "saldo": "TOTAL.TOTAL_inkl._offentliga_utsläpp_(ton_CO2e)",
}


@st.cache_resource
def get_model():
    return Model()


@st.cache_data(max_entries=3, show_spinner=False)
def simulate(preset: str, overrides_json: str, curves_json: str):
    return get_model().run(json.loads(overrides_json), preset, json.loads(curves_json))


@st.cache_data(max_entries=1, show_spinner=False)
def reference_check():
    model = get_model()
    return compare_reference(model, simulate("saved", "{}", "{}"))


def fmt(value: float) -> str:
    if not np.isfinite(value): return "Saknar värde"
    return f"{value:,.0f}".replace(",", " ")


def sv_csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, sep=";", decimal=",", float_format="%.12g").encode("utf-8-sig")


def line_chart(frame: pd.DataFrame, unit: str = "ton CO₂e", height: int = 350, x_title: str = "År"):
    long = frame.melt(id_vars="År", var_name="Serie", value_name="Värde")
    spec = {
        "mark": {"type": "line", "strokeWidth": 2.5}, "height": height,
        "encoding": {
            "x": {"field": "År", "type": "quantitative", "axis": {"title": x_title},
                  "scale": {"zero": False}},
            "y": {"field": "Värde", "type": "quantitative", "title": unit, "scale": {"zero": False}},
            "color": {"field": "Serie", "type": "nominal", "title": None,
                      "scale": {"range": ["#176b52", "#b88835", "#447eac", "#9a4559", "#748b57", "#665994"]},
                      "legend": {"orient": "bottom", "labelLimit": 500}},
            "tooltip": [{"field": "År", "type": "quantitative", "format": ".3f"},
                        {"field": "Serie", "type": "nominal"},
                        {"field": "Värde", "type": "quantitative", "format": ",.3f"}],
        }, "config": {"view": {"stroke": None}, "axis": {"gridColor": "#e6ede8"}},
    }
    st.vega_lite_chart(long, spec, use_container_width=True)


def variable_label(model: Model, key: str) -> str:
    v = model.variables[model.index[key]]
    return v["module"].replace("_", " ") + " · " + v["name"]


def reset_scenario():
    st.session_state.overrides = {}
    st.session_state.curves = {}
    st.session_state.epoch = st.session_state.get("epoch", 0) + 1


def apply_import(model: Model):
    try:
        content = st.session_state.scenario_file.getvalue()
        preset, params, curves = import_scenario(model, content)
        errors = parameter_checks(model, preset, params)
        if errors: raise ValueError(" ".join(errors))
        reset_scenario()
        st.session_state.preset_label = PRESET_LABELS[preset]
        st.session_state.overrides = params
        st.session_state.curves = curves
        st.session_state.import_message = "Scenariot är inläst."
    except (ValueError, TypeError, KeyError, UnicodeDecodeError) as e:
        st.session_state.import_error = str(e)


def common_keys(model: Model) -> list[str]:
    wanted = [
        "Byggnader.Nyproduktion_Flerbostadshus_(m2_BTA)",
        "Kontor.Nyproduktion_Kontor_(m2_BTA)",
        "Invånare.Bostadsyta_per_invånare_(m2_BTA/pers)",
        "ROT.Befintligt_fastighetsyta_i_stadsdel_(m2_BTA)",
        "Byggnader.Andel_betonghus_Flerbostadshus",
        "Byggnader.Andel_klimatförbättrad_betonghus_Flerbostadshus",
        "Byggnader.Andel_stålhus_Flerbostadshus",
        "Byggnader.Andel_klimatförbättrad_stålhus_Flerbostadshus",
        "Byggnader.Andel_trähus_Flerbostadshus",
        "Energi.Andel_FJV_av_nyproduktionen_(0-1)",
        "Energi.Nordisk_eller_svensk_emissionsfaktor",
        "Energi.Genomsnittlig_antal_vån._i_stadsdel",
        "Energi.Andel_takyta_med_solceller",
        "Energi.Solelsproduktion_1/0",
        "Mobilitet.Bilinnehav_Flerbostadshus_(bil/hushåll)",
        "Mobilitet.Körda_km_per_bil_(km/år)",
        "Mobilitet.Mobilitetsåtgärder_(0-6)",
        "Mobilitet.Av/På_M1",
        "Konsumtion.Minskad_konsumtion_(%)",
        "Urbana_träd.Antal_träd_planterade_(n)",
        "Urbana_träd.Antal_befintliga_stadsträd_(n)",
        "Återbetalning.Mängd_använd_biokol_(ton/år)",
        "Återbetalning.Kolhalt_biokol_(0-1)",
        "Återbetalning.Andel_CCF_certifierad_konstruktionsvirkesvolym_(0-2)",
        "Global_klimatbudget.Global_CO2-pool_(Gton_CO2e)",
    ]
    editable = {v["key"] for v in model.editable()}
    wanted += [v["key"] for v in model.editable() if v["key"].startswith("Scarborough_modell.Andel_")]
    return [k for k in wanted if k in editable]


def input_view(model: Model, preset: str):
    st.subheader("Ändra antaganden")
    st.write("Ändra siffrorna i kolumnen **Värde** och välj **Beräkna med dessa värden**. "
             "Ändringar från andra delmodeller följer med.")
    st.caption("Andelar anges normalt mellan 0 och 1. Av/På anges med 0 eller 1. "
               "Nyproduktion anges per år, enligt originalets flöden.")
    mode = st.radio("Visa", ["Vanliga reglage", "Alla parametrar", "Tidskurvor"], horizontal=True, key="input_mode")
    epoch = st.session_state.epoch
    defaults = model.parameters(preset)
    current = defaults | st.session_state.overrides
    if mode == "Tidskurvor":
        available = [v["key"] for i, v in enumerate(model.variables)
                     if "lookup" in v and i not in model.aliases]
        key = st.selectbox("Välj kurva", available, format_func=lambda k: variable_label(model, k), key="curve_choice")
        v = model.variables[model.index[key]]
        table = v["lookup"]
        ys = st.session_state.curves.get(key, table["y"])
        st.caption(f"Insignal: {v['equation']}. Interpolation: {table['type']}. "
                   "X-värdena bevaras; Y-värdena kan ändras.")
        with st.form(f"curve_form_{epoch}_{key}"):
            edited = st.data_editor(pd.DataFrame({"X": table["x"], "Y": ys}),
                                    disabled=["X"], hide_index=True, use_container_width=True,
                                    column_config={"Y": st.column_config.NumberColumn("Y", required=True)},
                                    key=f"curve_editor_{epoch}_{key}")
            submitted = st.form_submit_button("Beräkna med denna kurva", type="primary")
        if submitted:
            new_y = edited["Y"].astype(float).tolist()
            if not all(np.isfinite(new_y)):
                st.error("Alla kurvpunkter behöver vara ändliga tal.")
            else:
                if new_y == table["y"]: st.session_state.curves.pop(key, None)
                else: st.session_state.curves[key] = new_y
                st.session_state.epoch += 1
                st.rerun()
        line_chart(pd.DataFrame({"År": table["x"], "Original": table["y"], "Ditt scenario": ys}),
                   unit=v.get("units") or "Y-värde", height=260, x_title="Insignal (X)")
        return
    if mode == "Alla parametrar":
        modules = list(dict.fromkeys(v["module"] for v in model.editable()))
        chosen = st.selectbox("Delmodell", modules, format_func=lambda x: x.replace("_", " "), key="input_module")
        keys = [v["key"] for v in model.editable() if v["module"] == chosen]
    else:
        keys = common_keys(model)
    rows = []
    for k in keys:
        v = model.variables[model.index[k]]
        rows.append({"Delmodell": v["module"].replace("_", " "), "Parameter": v["name"],
                     "Värde": current[k], "Grundvärde": defaults[k]})
    with st.form(f"parameters_{epoch}_{mode}_{keys[0]}"):
        edited = st.data_editor(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                                height=min(710, 38+35*len(rows)),
                                disabled=["Delmodell", "Parameter", "Grundvärde"],
                                column_config={"Värde": st.column_config.NumberColumn("Värde", required=True),
                                               "Parameter": st.column_config.TextColumn(width="large")},
                                key=f"parameter_editor_{epoch}_{mode}_{keys[0]}")
        submitted = st.form_submit_button("Beräkna med dessa värden", type="primary")
    if submitted:
        candidate = dict(st.session_state.overrides)
        for k, value in zip(keys, edited["Värde"]):
            if pd.isna(value) or not np.isfinite(float(value)):
                st.error("Fyll i ett ändligt tal för varje parameter.")
                return
            if float(value) == defaults[k]: candidate.pop(k, None)
            else: candidate[k] = float(value)
        errors = parameter_checks(model, preset, candidate)
        if errors:
            for message in errors: st.error(message)
        else:
            st.session_state.overrides = candidate
            st.session_state.epoch += 1
            st.rerun()
    if st.session_state.overrides or st.session_state.curves:
        with st.expander("Visa dina ändringar"):
            changes = [{"Parameter": variable_label(model, k), "Grundvärde": defaults[k], "Ditt värde": v}
                       for k, v in st.session_state.overrides.items()]
            if changes: st.dataframe(pd.DataFrame(changes), hide_index=True, use_container_width=True)
            for k in st.session_state.curves: st.write("Ändrad kurva: " + variable_label(model, k))


def result_view(model: Model, result, year: int):
    idx = int(np.argmin(np.abs(result.time-year)))
    values = {k: result.series(v) for k, v in KEYS.items()}
    gross = values["personligt"] + values["byggd_miljo"] + values["offentligt"]
    st.subheader(f"Samlat resultat till {year}")
    columns = st.columns(4)
    metrics = [("Modul 1 + 2 + offentligt", gross[idx]),
               ("Modul 3 enligt Stella", values["balansering"][idx]),
               ("Tilldelad klimatbudget", values["budget"][idx]),
               ("Saldo enligt Stella", values["saldo"][idx])]
    for column, (title, value) in zip(columns, metrics):
        column.metric(title, fmt(value))
    st.caption("Enhet: ton CO₂e, enligt originalets benämningar. "
               "Saldo = modul 1 + modul 2 + offentliga utsläpp − modul 3 − tilldelad klimatbudget. "
               "Ett positivt saldo betyder att den tilldelade budgeten överskrids i modellen.")
    sample = np.arange(0, len(result.time), 30)
    sample = np.unique(np.append(sample, len(result.time)-1))
    frame = pd.DataFrame({"År": result.time[sample], "Modul 1 + 2 + offentligt": gross[sample],
                          "Modul 3": values["balansering"][sample], "Klimatbudget": values["budget"][sample],
                          "Saldo enligt Stella": values["saldo"][sample]})
    st.markdown("**Utveckling 2024–2050**")
    line_chart(frame)
    st.caption("Diagrammet visar ungefär månatliga ögonblick ur en simulering med dagliga beräkningssteg.")
    left, right = st.columns([1.15, 1])
    with left:
        st.markdown(f"**Bidrag till saldot {year}**")
        labels = ["1 · Personligt", "2 · Byggd miljö", "Offentligt", "3 · Avdrag", "Budget · Avdrag", "Saldo"]
        amounts = [values["personligt"][idx], values["byggd_miljo"][idx], values["offentligt"][idx],
                   -values["balansering"][idx], -values["budget"][idx]]
        walk, rows = 0.0, []
        for text, amount in zip(labels, amounts):
            rows.append({"Post": text, "Från": min(walk, walk+amount), "Till": max(walk, walk+amount),
                         "Bidrag": amount, "Typ": "Tillkommer" if amount >= 0 else "Dras av"})
            walk += amount
        rows.append({"Post": "Saldo", "Från": min(0, walk), "Till": max(0, walk), "Bidrag": walk, "Typ": "Saldo"})
        st.vega_lite_chart(pd.DataFrame(rows), {"height": 300, "mark": {"type": "bar", "cornerRadiusTopLeft": 3},
            "encoding": {"x": {"field": "Post", "type": "ordinal", "sort": labels, "axis": {"labelAngle": -30}, "title": None},
                         "y": {"field": "Till", "type": "quantitative", "title": "ton CO₂e"},
                         "y2": {"field": "Från"},
                         "color": {"field": "Typ", "type": "nominal", "scale": {"domain": ["Tillkommer", "Dras av", "Saldo"],
                                   "range": ["#447eac", "#b88835", "#176b52"]}, "legend": None},
                         "tooltip": [{"field": "Post"}, {"field": "Bidrag", "format": ",.1f", "type": "quantitative"}]},
            "config": {"view": {"stroke": None}}}, use_container_width=True)
    with right:
        st.markdown("**Vad ingår i modulerna?**")
        st.write("**Modul 1:** mobilitet, mat, övrig konsumtion och hushållsel.")
        st.write("**Modul 2:** byggnader, infrastruktur, parkering, energi, installationer och ROT enligt originalets summering.")
        st.write("**Modul 3:** träd, konstruktionsvirke, biokol och solelens utsläppsreduktion enligt originalets summering.")
        st.caption("Modul 3 innehåller både kolinlagring och undvikna utsläpp. Budgettilldelning redovisas separat. "
                   "Summeringarna återger Stella-filens logik.")
    st.markdown("**Årsresultat**")
    years, annual = result.annual()
    annual_frame = pd.DataFrame({"År": years.astype(int)})
    for k, title in [("personligt", "Modul 1"), ("byggd_miljo", "Modul 2"), ("offentligt", "Offentligt"),
                     ("balansering", "Modul 3"), ("budget", "Klimatbudget"), ("saldo", "Saldo")]:
        annual_frame[title] = annual[:, model.index[KEYS[k]]]
    st.dataframe(annual_frame.round(1), hide_index=True, use_container_width=True)
    st.download_button("Ladda ned årsresultat (CSV för Excel)", sv_csv(annual_frame), "arsresultat.csv", "text/csv", key="annual_csv")


def detail_view(model: Model, result):
    st.subheader("Utforska delmodellerna")
    modules = list(dict.fromkeys(v["module"] for v in model.variables))
    chosen = st.selectbox("Välj delmodell", modules, index=modules.index("Byggnader"),
                          format_func=lambda x: "Översikt" if x == ":" else x.replace("_", " "), key="detail_module")
    available = [v["key"] for v in model.variables if v["module"] == chosen]
    defaults = [k for k in available if model.variables[model.index[k]]["kind"] == "stock"][:2] or available[:1]
    chosen_keys = st.multiselect("Välj upp till 8 variabler", available, default=defaults,
                                format_func=lambda k: model.variables[model.index[k]]["name"],
                                max_selections=8, key=f"detail_variables_{chosen}")
    if chosen_keys:
        frequency = st.radio("Upplösning", ["År", "Dagligt beräkningssteg"], horizontal=True, key="detail_frequency")
        if frequency == "År": years, data = result.annual()
        else: years, data = result.time, result.values
        frame = pd.DataFrame({"År": years})
        for k in chosen_keys: frame[model.variables[model.index[k]]["name"]] = data[:, model.index[k]]
        st.caption("Kontrollera enheten i variabelnamnet när flera serier visas i samma diagram.")
        line_chart(frame, unit="Enligt valda variabler")
        st.dataframe(frame, hide_index=True, use_container_width=True)
        st.download_button("Ladda ned valda tidsserier (CSV)", sv_csv(frame), "valda_tidsserier.csv", "text/csv", key="selected_csv")
    st.divider()
    key = st.selectbox("Visa ekvation och dokumentation", available,
                       format_func=lambda k: model.variables[model.index[k]]["name"], key=f"equation_{chosen}")
    v = model.variables[model.index[key]]
    if key in model.alias_keys:
        st.write("Hämtas från: " + variable_label(model, model.alias_keys[key]))
        v = model.variables[model.index[model.alias_keys[key]]]
    st.code(v["equation"], language="text")
    if v["documentation"]:
        st.text(v["documentation"])
    if "lookup" in v:
        st.dataframe(pd.DataFrame({"X": v["lookup"]["x"], "Y, original": v["lookup"]["y"]}), hide_index=True)
    st.caption("Originalets benämningar, formler och dokumentation är bevarade. "
               "En siffra i en parametercell ersätter formelns konstanta värde i ditt scenario.")


def control_view(model: Model):
    st.subheader("Kontroll mot Stella")
    report_path = ROOT / "docs" / "validation_summary.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        st.success(f"Grundscenariot: {report['passed_series']} av {report['compared_series']} sparade variabler/tidsserier stämmer med Stella inom angiven tolerans.")
        st.caption(f"Kontrollen omfattar {report['stored_reference_values']:,} lagrade referensvärden. "
                   f"Relativ tolerans {report['rtol']:g}, absolut tolerans {report['atol']:g}. "
                   "Den gäller sparade reglage och originalets tidsinställningar.")
    reference_available = (MODEL_PATH.parent / "reference.npz").exists() and (MODEL_PATH.parent / "reference.json").exists()
    if not reference_available:
        st.info("Denna modellversion saknar sparade referensresultat från Stella.")
    if st.button("Kör referenskontrollen på nytt", disabled=not reference_available):
        with st.spinner("Jämför alla sparade serier och dagliga beräkningssteg…"):
            rows = reference_check()
        report = summary(rows)
        if report["passed_series"] == report["compared_series"]: st.success("Alla jämförda serier stämmer.")
        else: st.error("Minst en serie avviker. Se kontrolltabellen.")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.download_button("Ladda ned kontrolltabell", sv_csv(pd.DataFrame(rows)), "kontroll_mot_stella.csv", "text/csv")
    st.markdown("**Beräkningen**")
    st.write("Modellen använder Euler-metoden med tidssteg 1/365 år från 2024 till 2050. "
             "Kopplingar mellan delmodeller, ackumulerande lager, fördröjningen DELAY, INIT, "
             "PERCENT och grafiska funktioner har översatts till Python.")
    st.caption(f"{len(model.keys)} unika variabeldefinitioner, {len(model.aliases)} externa kopplingar, "
               f"{len(model.stock_indices)} oberoende lager och {len(model.editable())} redigerbara talparametrar.")
    with st.expander("Tolkning och iakttagelser i originalet"):
        st.write("Kontrollen visar att Python återger den bifogade modellen. Den utgör ingen separat vetenskaplig granskning av klimatantaganden, systemgränser eller budgetmetod.")
        st.write("CO₂ och CO₂e förekommer blandat i originalets variabelnamn. Andelarna för kost i Scarborough-modellen lagras som tal 0–1 trots att namnen anger procent.")
        st.write("Modul 3 blandar kolinlagring och solelens utsläppsreduktion. Originalets olika totalsummeringar använder dessutom olika tecken för modul 3. Översikten använder TOTAL inkl. offentliga utsläpp och visar budgetavdraget separat.")
        st.write("Garage och installationer kan ingå både i byggnadssumman och som separata poster i modul 2. Det bör kontrolleras vid en metodrevidering, eftersom summeringen kan ge dubbelräkning.")
        st.write("Två hjälpekvationer för parklind i delmodellen Återbetalning ger orimligt stora omkrets- och diametervärden genom att använda kalenderåret i exponenten. De har bevarats i konverteringen; se metodbeskrivningen innan de resultaten används.")
    with st.expander("Modellfil och källor"):
        st.text(model.data["source"]["filename"])
        st.code(model.data["source"]["sha256"], language="text")
        st.write("Antaganden och ursprungliga hänvisningar kan läsas per variabel under Delmodeller. Inga emissionsfaktorer eller litteraturkällor har uppdaterats i konverteringen.")


def main():
    st.set_page_config(page_title="Jägersro · Klimatmodell", page_icon="🌿", layout="wide")
    st.markdown("""<style>
        .block-container {max-width:1440px; padding-top:2rem;}
        [data-testid="stMetric"] {background:#f1f6f2; border:1px solid #dce8df; padding:1rem; border-radius:10px;}
        [data-testid="stMetricLabel"] {color:#3d5948;}
        h1,h2,h3 {color:#173d30;}
        </style>""", unsafe_allow_html=True)
    model = get_model()
    if "overrides" not in st.session_state: reset_scenario()
    if "preset_label" not in st.session_state: st.session_state.preset_label = "Sparade reglage i Stella"
    with st.sidebar:
        st.markdown("### Jägersro")
        st.caption("Klimatmodell · från Stella Architect")
        chosen_preset = st.selectbox("Grundscenario", list(PRESETS), key="preset_label", on_change=reset_scenario)
        preset = PRESETS[chosen_preset]
        st.caption("Sparade reglage återger filens senast sparade inställningar. Grundvärden använder ekvationernas värden.")
        year = st.slider("Visa samlat resultat till år", 2024, 2050, 2050, key="display_year")
        st.button("Återställ ditt scenario", on_click=reset_scenario, use_container_width=True)
        st.divider()
        st.download_button("Spara scenario (JSON)", export_scenario(model, preset, st.session_state.overrides, st.session_state.curves),
                           "jagersro_scenario.json", "application/json", use_container_width=True)
        uploaded = st.file_uploader("Läs in sparat scenario", type=["json"], key="scenario_file")
        if uploaded is not None:
            st.button("Använd scenariofil", on_click=apply_import, args=(model,), use_container_width=True)
        if "import_error" in st.session_state: st.error(st.session_state.pop("import_error"))
        if "import_message" in st.session_state: st.success(st.session_state.pop("import_message"))
        st.caption(f"{len(st.session_state.overrides)} ändrade talparametrar · {len(st.session_state.curves)} ändrade kurvor")
    st.title("Klimatmodell för Jägersro")
    st.write("Utforska klimatutsläpp, kolinlagring och klimatbudget för stadsdelen 2024–2050.")
    st.caption("Konverterad från Klimatmodell CO2e-budget, Avatar-MFF · version 1.0")
    try:
        with st.spinner("Beräknar med dagliga tidssteg…"):
            result = simulate(preset, json.dumps(st.session_state.overrides, sort_keys=True),
                              json.dumps(st.session_state.curves, sort_keys=True))
    except (ValueError, ArithmeticError, KeyError) as e:
        st.error(f"Scenariot gick inte att beräkna: {e}")
        st.info("Återställ scenariot i vänsterspalten eller läs in en tidigare scenariofil.")
        return
    if result.issues:
        st.warning(f"{len(result.issues)} variabler saknar ändliga resultat för dessa indata. Kontrollera antagandena.")
        with st.expander("Visa berörda variabler"):
            st.dataframe(pd.DataFrame([{"Variabel": k, "Orsak": v} for k, v in result.issues.items()]), hide_index=True)
    tabs = st.tabs(["Resultat", "Ändra antaganden", "Delmodeller", "Modell & kontroll", "Exportera"])
    with tabs[0]: result_view(model, result, year)
    with tabs[1]: input_view(model, preset)
    with tabs[2]: detail_view(model, result)
    with tabs[3]: control_view(model)
    with tabs[4]:
        st.subheader("Exportera resultat och antaganden")
        st.write("CSV-filerna använder semikolon och decimalkomma för svensk Excel. "
                 "Årsresultaten är värden vid respektive årsskifte, beräknade med dagliga steg.")
        years, data = result.annual()
        frame = pd.DataFrame(data, columns=model.keys)
        frame.insert(0, "År", years.astype(int))
        st.download_button("Alla variabler, årsvis (CSV)", sv_csv(frame), "alla_variabler_arsvis.csv", "text/csv")
        params = model.parameters(preset) | st.session_state.overrides
        parameter_frame = pd.DataFrame([{"Variabel": k, "Benämning": variable_label(model, k), "Värde": v,
                                         "Ändrad i scenariot": k in st.session_state.overrides} for k, v in params.items()])
        st.download_button("Alla inparametrar (CSV)", sv_csv(parameter_frame), "inparametrar.csv", "text/csv")
        st.download_button("Scenario med parametrar och kurvor (JSON)",
                           export_scenario(model, preset, st.session_state.overrides, st.session_state.curves),
                           "jagersro_scenario.json", "application/json", key="scenario_export")
        st.caption("För dagliga värden: välj variabler och upplösning under Delmodeller. "
                   "Scenariofilen kan återimporteras och delas med andra användare av samma modellversion.")
    st.divider()
    st.caption("Jägersro · Stella → Python/Streamlit · Originalets beräkningslogik och antaganden bevaras.")


if __name__ == "__main__":
    main()
