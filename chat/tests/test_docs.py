import re
import unittest
from pathlib import Path

CHAT = Path(__file__).resolve().parent.parent
REFERRER = "referrer_id=9b12faba-f8a3-49ea-bd25-d8343f1fd965"

# Alla webbadresser till 1min.ai, även docs.1min.ai. api.1min.ai är endpointen
# och matchar inte, eftersom den inte ska ha några parametrar.
LINK = re.compile(r"https://(?!api\.)(?:[\w-]+\.)?1min\.ai[^\s)\]>`]*")


def one_min_links() -> list[tuple[str, str]]:
    found = []
    for name in ("README.md", ".env.example", "prompt.md"):
        text = (CHAT / name).read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            found.append((name, match.group(0)))
    return found


class ReferralLinkTest(unittest.TestCase):
    def test_every_website_link_carries_the_referrer(self) -> None:
        links = one_min_links()
        self.assertTrue(links, "inga 1min.ai-länkar hittades")
        for name, url in links:
            with self.subTest(file=name, url=url):
                self.assertIn(REFERRER, url)

    def test_api_endpoint_is_not_treated_as_a_referral_link(self) -> None:
        text = (CHAT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://api.1min.ai/openai/v1", text)
        self.assertFalse(any("api.1min.ai" in url for _, url in one_min_links()))


if __name__ == "__main__":
    unittest.main()
