import json
import math
from pathlib import Path
import unittest

import numpy as np

from scenario import export_scenario, import_scenario, parameter_checks
from stella_model import Model, Node, Parser, EquationError, lookup_value
from validation import compare_reference


class OriginalModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = Model()
        cls.result = cls.model.run()

    def test_every_saved_stella_series(self):
        """681 serier inklusive 2 344 711 faktiskt lagrade referensvärden."""
        self.assertFalse(self.result.issues)
        rows = compare_reference(self.model, self.result)
        self.assertEqual(len(rows), 681)
        self.assertEqual(sum(r["Lagrade referensvärden"] for r in rows), 2344711)
        for row in rows:
            with self.subTest(variable=row["Variabel"]):
                self.assertTrue(row["Godkänd"], row)

    def test_all_808_variables_are_finite(self):
        self.assertEqual(self.result.values.shape, (9491, 808))
        self.assertTrue(np.isfinite(self.result.values).all())
        self.assertEqual(len(self.model.aliases), 127)

    def test_formula_defaults_also_run(self):
        result = self.model.run(preset="equations")
        self.assertFalse(result.issues)
        self.assertTrue(np.isfinite(result.values).all())
        self.assertFalse(np.allclose(result.values, self.result.values))

    def test_removing_biochar_changes_net_by_its_exact_contribution(self):
        result = self.model.run({"Återbetalning.Mängd_använd_biokol_(ton/år)": 0})
        net = "TOTAL.TOTAL_inkl._offentliga_utsläpp_(ton_CO2e)"
        biochar = "Återbetalning.Negativt_utsläpp_biokol_(ton_CO2e)"
        self.assertFalse(result.issues)
        np.testing.assert_allclose(result.series(biochar), 0, atol=1e-10)
        np.testing.assert_allclose(result.series(net)-self.result.series(net),
                                   self.result.series(biochar), rtol=1e-9, atol=1e-7)
        # Ändringar får inte påverka originalets sparade reglage.
        self.assertEqual(self.model.parameters()["Återbetalning.Mängd_använd_biokol_(ton/år)"], 363)

    def test_a_changed_lookup_changes_values_and_is_isolated(self):
        key = "Energi.Emissionsfaktor_Nordisk_elmix_(gCO2e/kWh)"
        table = self.model.variables[self.model.index[key]]["lookup"]
        result = self.model.run(curves={key: [0.0]*len(table["y"])})
        self.assertFalse(result.issues)
        np.testing.assert_allclose(result.series(key), 0)
        self.assertGreater(self.result.series(key)[0], 0)
        self.assertEqual(self.model.variables[self.model.index[key]]["lookup"]["y"][0], 82)

    def test_scenario_export_import_preserves_changes(self):
        changes = {"Mobilitet.Körda_km_per_bil_(km/år)": 9000.0}
        content = export_scenario(self.model, "saved", changes, {})
        preset, restored, curves = import_scenario(self.model, content)
        self.assertEqual(preset, "saved")
        self.assertEqual(restored, changes)
        self.assertFalse(curves)
        self.assertFalse(parameter_checks(self.model, preset, restored))

    def test_invalid_scenario_and_inconsistent_shares_rejected(self):
        data = json.loads(export_scenario(self.model, "saved", {}, {}))
        data["source_sha256"] = "wrong"
        with self.assertRaises(ValueError):
            import_scenario(self.model, json.dumps(data).encode())
        self.assertTrue(parameter_checks(self.model, "saved", {"Byggnader.Andel_trähus_Flerbostadshus": 0.4}))
        with self.assertRaises(ValueError):
            self.model.run({"Mobilitet.Körda_km_per_bil_(km/år)": math.inf})


class NumericalSemanticsTests(unittest.TestCase):
    def ev(self, expression):
        node = Parser(expression).parse()
        return Model._eval(node, lambda i: 0, 2024, lambda n: 2024, lambda n: 0)

    def test_lazy_stella_if_and_percent(self):
        self.assertEqual(self.ev("4+IF(1)=1THEN(PERCENT(.09))ELSE(1/0)"), 13)
        self.assertEqual(self.ev("IF(0)=1 THEN 1/0 ELSE 7"), 7)
        self.assertAlmostEqual(self.ev("2^3^2"), 512)

    def test_continuous_and_discrete_endpoints(self):
        table = {"x": [2024, 2025, 2026], "y": [10, 20, 40], "type": "continuous"}
        self.assertEqual(lookup_value(2024.5, table), 15)
        self.assertEqual(lookup_value(2020, table), 10)
        table["type"] = "discrete"
        self.assertEqual(lookup_value(2024.9, table), 10)
        self.assertEqual(lookup_value(2025, table), 20)
        self.assertEqual(lookup_value(2050, table), 40)

    def test_no_python_calls_or_attribute_access(self):
        with self.assertRaises(EquationError):
            Parser('__import__("os")').parse()
        with self.assertRaises(EquationError):
            Parser("1; open('secret')").parse()

    def test_euler_delay_and_init_on_known_small_system(self):
        def var(key, kind, equation, inflows=None):
            return {"key": key, "module": "Test", "name": key, "kind": kind,
                    "equation": equation, "non_negative": False, "inflows": inflows or [], "outflows": []}
        data = {"simulation": {"start": 2024, "stop": 2028, "dt": 1}, "connections": {}, "controls": {},
                "variables": [var("Test.Lager", "stock", "0", ["Test.Flöde"]),
                              var("Test.Flöde", "flow", "2"),
                              var("Test.Lag", "aux", "DELAY(TIME,2)"),
                              var("Test.Förfluten_tid", "aux", "TIME-INIT(TIME)")]}
        result = Model(data).run()
        np.testing.assert_allclose(result.series("Test.Lager"), [0, 2, 4, 6, 8])
        np.testing.assert_allclose(result.series("Test.Lag"), [2024, 2024, 2024, 2025, 2026])
        np.testing.assert_allclose(result.series("Test.Förfluten_tid"), [0, 1, 2, 3, 4])


if __name__ == "__main__": unittest.main()
