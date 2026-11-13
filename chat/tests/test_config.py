import unittest

from config import persona_enabled


class PersonaToggleTest(unittest.TestCase):
    def test_on_by_default(self) -> None:
        self.assertTrue(persona_enabled(None))
        self.assertTrue(persona_enabled(""))
        self.assertTrue(persona_enabled("1"))
        self.assertTrue(persona_enabled("on"))

    def test_off_variants(self) -> None:
        for raw in ("0", "off", "nej", "NEJ", "false", "no", " off "):
            with self.subTest(raw=raw):
                self.assertFalse(persona_enabled(raw))


if __name__ == "__main__":
    unittest.main()
