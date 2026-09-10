"""Smoke tests for the workspace-scoped Streamlit UI."""

from __future__ import annotations

from pathlib import Path
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ModuleNotFoundError:  # pragma: no cover - dependency-free test environments
    AppTest = None


ROOT = Path(__file__).resolve().parents[2]
HOME_PAGE = ROOT / "apps" / "ui" / "Home.py"
ASK_PAGE = ROOT / "apps" / "ui" / "pages" / "1_Ask_a_Question.py"
MY_DATA_PAGE = ROOT / "apps" / "ui" / "pages" / "4_My_Data.py"


@unittest.skipIf(AppTest is None, "Streamlit is not installed")
class StreamlitMVPTests(unittest.TestCase):
    def test_all_pages_render_without_exceptions(self) -> None:
        pages = [
            HOME_PAGE,
            ASK_PAGE,
            ROOT / "apps" / "ui" / "pages" / "2_Query_History.py",
            ROOT / "apps" / "ui" / "pages" / "3_Guardrail_Settings.py",
            MY_DATA_PAGE,
        ]

        for page in pages:
            with self.subTest(page=page.name):
                app = AppTest.from_file(str(page))
                app.run()
                self.assertEqual([], list(app.exception))

    def test_home_requires_a_workspace_and_does_not_show_demo_results(self) -> None:
        app = AppTest.from_file(str(HOME_PAGE))
        app.run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(0, len(app.dataframe))
        self.assertEqual(0, len(app.code))

    def test_home_contains_no_example_result_data(self) -> None:
        source = HOME_PAGE.read_text(encoding="utf-8")
        for fabricated_value in (
            "Rahul Menon",
            "Priya Sharma",
            "Rohan Das",
            "term_records",
            "student_name",
            "attendance_pct",
        ):
            with self.subTest(fabricated_value=fabricated_value):
                self.assertNotIn(fabricated_value, source)

    def test_ask_page_requires_a_workspace_before_executing(self) -> None:
        app = AppTest.from_file(str(ASK_PAGE))
        app.run()
        self.assertEqual([], list(app.exception))

    def test_ask_page_has_compact_question_controls(self) -> None:
        app = AppTest.from_file(str(ASK_PAGE))
        app.run()
        self.assertEqual(["Your question"], [element.label for element in app.text_area])
        self.assertIn("Generate answer", [element.label for element in app.button])

    def test_connection_page_exposes_all_supported_source_paths(self) -> None:
        app = AppTest.from_file(str(MY_DATA_PAGE))
        app.run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(
            ["Upload CSV or Excel", "Connect database server", "SQLite file"],
            [element.label for element in app.tabs],
        )
        self.assertEqual(
            ["Choose a CSV or Excel file", "Upload a SQLite database"],
            [element.label for element in app.file_uploader],
        )
