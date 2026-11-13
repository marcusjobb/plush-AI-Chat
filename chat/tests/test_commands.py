import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from chat import (
    auto_compact_due,
    auto_compact_if_due,
    help_text,
    parse_command,
)
from config import MAX_CHARS, MAX_MESSAGES, WARN_AT, budget_state
from llm import LLMError, Reply
from store import Store


class ParseCommandTest(unittest.TestCase):
    def test_slash_commands(self) -> None:
        self.assertEqual(parse_command("/compact"), ("command", "compact"))
        self.assertEqual(parse_command("/exit"), ("command", "exit"))
        self.assertEqual(parse_command("/help"), ("command", "help"))
        self.assertEqual(parse_command("/reset"), ("command", "reset"))

    def test_bare_aliases(self) -> None:
        self.assertEqual(parse_command("exit"), ("command", "exit"))
        self.assertEqual(parse_command("AVSLUTA"), ("command", "exit"))
        self.assertEqual(parse_command("nollställ"), ("command", "reset"))
        self.assertEqual(parse_command("? "), ("command", "help"))

    def test_unknown_slash_command_is_not_a_message(self) -> None:
        self.assertEqual(parse_command("/finns-inte"), ("unknown", "finns-inte"))

    def test_ordinary_text_is_a_message(self) -> None:
        self.assertEqual(parse_command("Hej!"), ("message", "Hej!"))
        self.assertEqual(parse_command("  Hej  "), ("message", "Hej"))
        # Ett snedstreck mitt i texten är inget kommando.
        self.assertEqual(parse_command("3/4 är klart"), ("message", "3/4 är klart"))

    def test_empty_line_is_none(self) -> None:
        self.assertIsNone(parse_command(""))
        self.assertIsNone(parse_command("   "))


class BudgetTest(unittest.TestCase):
    def messages(self, count: int, chars: int = 1) -> list[dict[str, str]]:
        return [{"role": "user", "content": "x" * chars} for _ in range(count)]

    def test_small_history_is_fine(self) -> None:
        self.assertIsNone(budget_state(self.messages(2, 100)))

    def test_warning_before_the_ceiling(self) -> None:
        state = budget_state(self.messages(int(MAX_MESSAGES * WARN_AT)))
        self.assertIsNotNone(state)
        self.assertEqual(state[0], "warn")

    def test_hard_stop_at_the_ceiling(self) -> None:
        state = budget_state(self.messages(MAX_MESSAGES))
        self.assertIsNotNone(state)
        self.assertEqual(state[0], "stop")

    def test_many_characters_trigger_too(self) -> None:
        state = budget_state(self.messages(1, MAX_CHARS))
        self.assertEqual(state[0], "stop")


class FakeLLM:
    """Fejkklients som svarar med en sammanfattning utan nätverk."""

    def __init__(self, limit: int = 50, fail: bool = False) -> None:
        self.settings = SimpleNamespace(
            auto_compact_at=limit, compact_model="fake-model"
        )
        self.fail = fail
        self.calls = 0

    def compact(self, messages):
        self.calls += 1
        if self.fail:
            raise LLMError("fejkfel")
        return (
            {"fakta": ["katt: Misse Mjau, gul"]},
            "SAMMANFATTNING",
            Reply(text=""),
        )


class AutoCompactTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self._tmp.name) / "turns.jsonl")
        # 50 meddelanden är den kontext som ska trigga komprimering.
        self.messages = [{"role": "user", "content": "x"} for _ in range(50)]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_due_at_limit(self) -> None:
        self.assertFalse(auto_compact_due(self.messages[:49], 50))
        self.assertTrue(auto_compact_due(self.messages, 50))

    def test_disabled_with_zero(self) -> None:
        self.assertFalse(auto_compact_due(self.messages, 0))

    def test_retry_floor_blocks_until_history_grows(self) -> None:
        self.assertFalse(auto_compact_due(self.messages, 50, retry_floor=60))
        self.assertTrue(auto_compact_due(self.messages + [{}] * 10, 50, 60))

    def test_compact_runs_and_replaces_history(self) -> None:
        llm = FakeLLM()
        with contextlib.redirect_stdout(io.StringIO()):
            messages, floor = auto_compact_if_due(llm, self.store, self.messages)

        self.assertEqual(llm.calls, 1)
        self.assertEqual(floor, 0)
        self.assertEqual(
            messages, [{"role": "assistant", "content": "SAMMANFATTNING"}]
        )
        self.assertEqual(self.store.events()[0]["type"], "compact")

    def test_failed_compact_sets_retry_floor(self) -> None:
        llm = FakeLLM(fail=True)
        with contextlib.redirect_stdout(io.StringIO()):
            messages, floor = auto_compact_if_due(llm, self.store, self.messages)

        self.assertEqual(llm.calls, 1)
        self.assertEqual(len(messages), 50)
        self.assertEqual(floor, 60)

        # Samma historik igen: inget nytt försök förrän den vuxit.
        with contextlib.redirect_stdout(io.StringIO()):
            _, floor = auto_compact_if_due(llm, self.store, self.messages, floor)
        self.assertEqual(llm.calls, 1)

    def test_below_limit_does_nothing(self) -> None:
        llm = FakeLLM()
        messages, floor = auto_compact_if_due(llm, self.store, self.messages[:10])

        self.assertEqual(llm.calls, 0)
        self.assertEqual(floor, 0)
        self.assertEqual(len(messages), 10)
        self.assertEqual(self.store.events(), [])

    def test_help_mentions_the_limit(self) -> None:
        self.assertIn("50 meddelanden", help_text(50))
        self.assertIn("avstängd", help_text(0))
        self.assertIn("Margareta", help_text(50))
        self.assertIn("avstängd", help_text(50, persona=False))


if __name__ == "__main__":
    unittest.main()
