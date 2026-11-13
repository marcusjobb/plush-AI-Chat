import unittest
from types import SimpleNamespace

from config import Settings
from llm import (
    COMPACT_PREFIX,
    Reply,
    SUMMARY_FIELDS,
    LLM,
    parse_summary,
    render_summary,
    summary_counts,
)


class FakeCompletions:
    """Fångar parametrarna och svarar utan nätverk."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.params: dict | None = None

    def create(self, **params):
        self.params = params
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content),
                    finish_reason="stop",
                )
            ],
            usage=None,
            model="fake-model",
        )


def make_llm(content: str = "Hej.", persona: bool = True):
    settings = Settings(
        api_key="test",
        model="gpt-unknown",
        compact_model="compact-unknown",
        base_url="http://example.invalid",
        auto_compact_at=50,
        persona=persona,
    )
    llm = LLM(settings)
    completions = FakeCompletions(content)
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return llm, completions


class PersonaTest(unittest.TestCase):
    def test_system_prompt_is_sent_with_every_message(self) -> None:
        llm, completions = make_llm()

        reply = llm.complete([{"role": "user", "content": "Hej"}], stream=False)

        self.assertEqual(reply.text, "Hej.")
        messages = completions.params["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Margareta", messages[0]["content"])
        self.assertEqual(messages[1], {"role": "user", "content": "Hej"})

    def test_persona_can_be_skipped_for_one_call(self) -> None:
        llm, completions = make_llm()

        llm.complete(
            [{"role": "user", "content": "Hej"}], stream=False, use_persona=False
        )

        self.assertEqual(
            completions.params["messages"], [{"role": "user", "content": "Hej"}]
        )

    def test_persona_off_in_settings_sends_no_system_prompt(self) -> None:
        llm, completions = make_llm(persona=False)

        self.assertEqual(llm.system, [])
        llm.complete([{"role": "user", "content": "Hej"}], stream=False)

        roles = [m["role"] for m in completions.params["messages"]]
        self.assertEqual(roles, ["user"])

    def test_compact_runs_without_persona(self) -> None:
        llm, completions = make_llm(
            content='{"fakta": ["katt: Misse Mjau, gul"], "preferenser": [], '
            '"beslut": [], "oppna_uppgifter": []}'
        )

        summary, rendered, _ = llm.compact([{"role": "user", "content": "Hej"}])

        messages = completions.params["messages"]
        self.assertNotIn("system", [m["role"] for m in messages])
        self.assertEqual(messages[0], {"role": "user", "content": "Hej"})
        self.assertEqual(messages[-1]["role"], "user")
        self.assertIn("Sammanfatta samtalet", messages[-1]["content"])
        self.assertEqual(summary["fakta"], ["katt: Misse Mjau, gul"])
        self.assertEqual(rendered.splitlines()[0], COMPACT_PREFIX)
        self.assertEqual(completions.params["model"], "compact-unknown")


class ParseSummaryTest(unittest.TestCase):
    def test_valid_json(self) -> None:
        summary = parse_summary(
            '{"fakta": ["katt: Misse Mjau, gul"], "preferenser": ["korta svar"],'
            ' "beslut": ["Bottle"], "oppna_uppgifter": []}'
        )

        self.assertEqual(summary["fakta"], ["katt: Misse Mjau, gul"])
        self.assertEqual(summary["preferenser"], ["korta svar"])
        self.assertEqual(summary["beslut"], ["Bottle"])
        self.assertEqual(summary["oppna_uppgifter"], [])

    def test_fenced_json(self) -> None:
        raw = '```json\n{"fakta": ["namn: Marcus"], "preferenser": [], ' \
              '"beslut": [], "oppna_uppgifter": []}\n```'
        self.assertEqual(parse_summary(raw)["fakta"], ["namn: Marcus"])

    def test_missing_fields_become_empty_lists(self) -> None:
        summary = parse_summary('{"fakta": ["namn: Marcus"]}')

        self.assertEqual(summary["fakta"], ["namn: Marcus"])
        for field in SUMMARY_FIELDS[1:]:
            self.assertEqual(summary[field], [])

    def test_a_string_field_is_wrapped(self) -> None:
        summary = parse_summary('{"fakta": "namn: Marcus", "preferenser": [],'
                                ' "beslut": [], "oppna_uppgifter": []}')
        self.assertEqual(summary["fakta"], ["namn: Marcus"])

    def test_json_inside_prose_is_found(self) -> None:
        summary = parse_summary(
            'Här är anteckningen: {"fakta": ["färg: gul"], "preferenser": [],'
            ' "beslut": [], "oppna_uppgifter": []} Klart.'
        )
        self.assertEqual(summary["fakta"], ["färg: gul"])

    def test_plain_text_falls_back_to_fakta(self) -> None:
        summary = parse_summary("- namn: Marcus\n- katt: Misse Mjau, gul")

        self.assertEqual(summary["fakta"], ["namn: Marcus", "katt: Misse Mjau, gul"])
        self.assertEqual(summary["beslut"], [])

    def test_garbage_does_not_raise(self) -> None:
        summary = parse_summary("")
        self.assertEqual(summary["fakta"], [])
        self.assertEqual(summary["preferenser"], [])

    def test_all_empty_json_gives_empty_summary(self) -> None:
        summary = parse_summary(
            '{"fakta": [], "preferenser": [], "beslut": [], "oppna_uppgifter": []}'
        )
        self.assertEqual(summary["fakta"], [])
        self.assertEqual(summary["beslut"], [])


class RenderSummaryTest(unittest.TestCase):
    def test_prefix_and_fields(self) -> None:
        rendered = render_summary(
            {
                "fakta": ["katt: Misse Mjau, gul", "namn: Marcus"],
                "preferenser": ["korta svar."],
                "beslut": [],
                "oppna_uppgifter": ["deploy"],
            }
        )

        lines = rendered.splitlines()
        self.assertEqual(lines[0], COMPACT_PREFIX)
        self.assertEqual(lines[1], "fakta: katt: Misse Mjau, gul; namn: Marcus")
        # Avslutande punkt stryks, tomma fält hoppas över.
        self.assertEqual(lines[2], "preferenser: korta svar")
        self.assertEqual(lines[3], "oppna_uppgifter: deploy")
        self.assertEqual(len(lines), 4)

    def test_empty_summary_still_renders(self) -> None:
        rendered = render_summary({})
        self.assertEqual(rendered, f"{COMPACT_PREFIX}\nfakta: -")

    def test_counts(self) -> None:
        text = summary_counts({"fakta": ["a", "b"], "preferenser": ["c"]})
        self.assertEqual(
            text, "fakta: 2, preferenser: 1, beslut: 0, öppna uppgifter: 0"
        )


class ReplyTest(unittest.TestCase):
    def test_truncated_only_for_length(self) -> None:
        self.assertTrue(Reply(text="x", finish_reason="length").truncated)
        self.assertFalse(Reply(text="x", finish_reason="stop").truncated)
        self.assertFalse(Reply(text="x").truncated)

    def test_usage_line(self) -> None:
        reply = Reply(text="x", usage={"prompt": 10, "completion": 5, "total": 15})
        self.assertEqual(reply.usage_line, "tokens: 10 in, 5 ut (15 totalt)")

    def test_missing_usage_gives_empty_line(self) -> None:
        self.assertEqual(Reply(text="x").usage_line, "")


if __name__ == "__main__":
    unittest.main()
