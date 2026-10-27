"""Riktigt Streamlit AppTest. Kräver installation av requirements.txt."""
from pathlib import Path
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Streamlit är inte installerat i denna testmiljö")
class StreamlitAppTests(unittest.TestCase):
    def test_app_starts_with_original_result_and_changes_preset(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 4)
        self.assertEqual(app.metric[3].value, "307 192")
        self.assertFalse(app.error)
        app.selectbox(key="preset_label").select("Ekvationernas grundvärden").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertNotEqual(app.metric[3].value, "307 192")


if __name__ == "__main__": unittest.main()
