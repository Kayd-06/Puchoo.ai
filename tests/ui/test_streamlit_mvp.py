"""Rendered-behavior checks for the Streamlit MVP.

These checks automatically skip in a Python environment without the optional
UI dependencies. They run as part of the normal test command after installing
``requirements.txt``.
"""

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


@unittest.skipIf(AppTest is None, "Streamlit is not installed")
class StreamlitMVPTests(unittest.TestCase):
    def test_all_pages_render_without_exceptions(self) -> None:
        pages = [
            HOME_PAGE,
            ASK_PAGE,
            ROOT / "apps" / "ui" / "pages" / "2_Query_History.py",
            ROOT / "apps" / "ui" / "pages" / "3_Guardrail_Settings.py",
        ]

        for page in pages:
            with self.subTest(page=page.name):
                app = AppTest.from_file(str(page))
                app.run()
                self.assertEqual([], list(app.exception))

    def test_home_accepts_a_user_question_without_fabricating_a_result(self) -> None:
        app = AppTest.from_file(str(HOME_PAGE))
        app.run()
        app.text_area[0].input("What is the latest revenue?")
        app.button[0].click()
        app.run()

        self.assertEqual([], list(app.exception))
        self.assertEqual("What is the latest revenue?", app.session_state["submitted_question"])
        self.assertIn("Clear question", [button.label for button in app.button])
        self.assertEqual(0, len(app.dataframe))
        self.assertEqual(0, len(app.code))

    def test_home_requires_a_question_before_submission(self) -> None:
        app = AppTest.from_file(str(HOME_PAGE))
        app.run()
        app.button[0].click()
        app.run()

        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(app.error))
        self.assertNotIn("submitted_question", app.session_state)

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

    def test_query_is_reviewed_before_it_can_run(self) -> None:
        app = AppTest.from_file(str(ASK_PAGE))
        app.run()
        app.text_area[0].input("How has monthly revenue changed over the last six months?")
        app.button[3].click()
        app.run()

        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(app.code))
        self.assertIn("Run approved query", [button.label for button in app.button])

        next(button for button in app.button if button.label == "Run approved query").click()
        app.run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(app.dataframe))

    def test_write_request_is_blocked_in_the_ui(self) -> None:
        app = AppTest.from_file(str(ASK_PAGE))
        app.run()
        app.text_area[0].input("Delete cancelled orders")
        app.button[3].click()
        app.run()

        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(app.error))
        self.assertNotIn("Run approved query", [button.label for button in app.button])

    def test_editing_a_question_invalidates_its_previous_proposal(self) -> None:
        app = AppTest.from_file(str(ASK_PAGE))
        app.run()
        app.text_area[0].input("How has monthly revenue changed over the last six months?")
        app.button[3].click()
        app.run()
        self.assertIn("Run approved query", [button.label for button in app.button])

        app.text_area[0].input("Which customer segments have the highest lifetime value?")
        app.run()
        self.assertEqual([], list(app.exception))
        self.assertNotIn("Run approved query", [button.label for button in app.button])
