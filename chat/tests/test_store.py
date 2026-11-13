import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from store import RESET, Store, import_legacy


class StoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "turns.jsonl"
        self.store = Store(self.path, session="test")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_turns_become_context(self) -> None:
        self.store.add_turn("user", "Hej")
        self.store.add_turn("assistant", "Hej själv")

        self.assertEqual(
            self.store.context(),
            [
                {"role": "user", "content": "Hej"},
                {"role": "assistant", "content": "Hej själv"},
            ],
        )

    def test_every_event_has_time_and_session(self) -> None:
        self.store.add_turn("user", "Hej")

        event = self.store.events()[0]
        self.assertEqual(event["type"], "turn")
        self.assertEqual(event["session"], "test")
        self.assertIn("time", event)

    def test_reset_hides_earlier_turns_but_keeps_log(self) -> None:
        self.store.add_turn("user", "Hej")
        self.store.reset()
        self.store.add_turn("user", "Ny start")

        self.assertEqual(self.store.context(), [{"role": "user", "content": "Ny start"}])
        self.assertEqual(len(self.store.events()), 3)
        self.assertEqual(self.store.events()[1]["type"], RESET)

    def test_compact_replaces_context_with_summary(self) -> None:
        self.store.add_turn("user", "Katten heter Misse Mjau och är gul")
        self.store.add_turn("assistant", "Noterat")
        self.store.compact({"fakta": ["katt: Misse Mjau, gul"]}, "SAMMANFATTNING")

        self.assertEqual(
            self.store.context(), [{"role": "assistant", "content": "SAMMANFATTNING"}]
        )
        # Inget har raderats: de gamla turerna finns kvar i loggen.
        self.assertEqual(len(self.store.events()), 3)

    def test_compact_without_rendered_is_ignored(self) -> None:
        self.store.add_turn("user", "Hej")
        self.store.compact({"fakta": []}, "")

        self.assertEqual(self.store.context(), [{"role": "user", "content": "Hej"}])

    def test_unknown_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_turn("robot", "Hej")

    def test_broken_lines_are_counted_and_skipped(self) -> None:
        self.store.add_turn("user", "Hej")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write("{inte json\n")
            fh.write("[1, 2, 3]\n")

        self.assertEqual(self.store.context(), [{"role": "user", "content": "Hej"}])
        self.assertEqual(self.store.broken_lines, 2)

    def test_missing_file_gives_empty_context(self) -> None:
        self.assertEqual(self.store.context(), [])


class LegacyImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = Store(self.root / "turns.jsonl")
        self.legacy = self.root / "history.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_imports_valid_posts_once(self) -> None:
        self.legacy.write_text(
            json.dumps(
                [
                    {"role": "user", "content": "Hej"},
                    {"role": "assistant", "content": "Hej!"},
                    {"role": "tool", "content": "ignoreras"},
                    {"role": "user", "content": 5},
                ]
            ),
            encoding="utf-8",
        )

        self.assertEqual(import_legacy(self.store, self.legacy), 2)
        self.assertEqual(len(self.store.context()), 2)
        # Andra anropet ska inte importera igen.
        self.assertEqual(import_legacy(self.store, self.legacy), 0)
        self.assertEqual(len(self.store.context()), 2)

    def test_broken_legacy_file_gives_zero(self) -> None:
        self.legacy.write_text("{trasig", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(import_legacy(self.store, self.legacy), 0)

    def test_missing_legacy_file_gives_zero(self) -> None:
        self.assertEqual(import_legacy(self.store, self.legacy), 0)


if __name__ == "__main__":
    unittest.main()
