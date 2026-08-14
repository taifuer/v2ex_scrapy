import unittest
from pathlib import Path

from scrapy.http import HtmlResponse

from v2ex_scrapy.v2ex_parser import parse_comment, parse_member, parse_topic


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_response(name: str, url: str) -> HtmlResponse:
    return HtmlResponse(
        url=url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
    )


class V2exParserTest(unittest.TestCase):
    def test_parse_topic_node_from_go_link_in_header(self):
        html = """
        <html>
          <body>
            <div class="header">
              <h1>Example topic</h1>
              <small>
                <a href="/member/alice">alice</a>
                · 100 次点击
                <span title="2026-02-24 15:18:16 +08:00"></span>
              </small>
              <a href="/go/programmer">程序员</a>
            </div>
            <div class="cell">
              <div class="topic_content">content</div>
            </div>
            <div class="box">
              <div class="cell"><span class="gray">3 条回复</span></div>
            </div>
            <a class="tag" href="/tag/Python">Python</a>
          </body>
        </html>
        """
        response = HtmlResponse(
            url="https://www.v2ex.com/t/1",
            body=html.encode(),
            encoding="utf-8",
        )

        topic = next(parse_topic(response, 1))

        self.assertEqual(topic.node, "programmer")
        self.assertEqual(topic.author, "alice")
        self.assertEqual(topic.reply_count, 3)

    def test_parse_standard_topic_interactions_and_tags(self):
        response = fixture_response(
            "topic_standard.html", "https://www.v2ex.com/t/123"
        )

        topic = next(parse_topic(response, 123))

        self.assertEqual(topic.title, "Example topic")
        self.assertEqual(topic.node, "programmer")
        self.assertEqual(topic.tag, ["Python", "AI"])
        self.assertEqual(topic.clicks, 1234)
        self.assertEqual(topic.votes, 12)
        self.assertEqual(topic.favorite_count, 8)
        self.assertEqual(topic.thank_count, 5)
        self.assertEqual(topic.reply_count, 2)

    def test_parse_comment_page(self):
        response = fixture_response(
            "topic_standard.html", "https://www.v2ex.com/t/123?p=2"
        )

        comments = list(parse_comment(response, 123))

        self.assertEqual([item.id_ for item in comments], [101, 102])
        self.assertEqual([item.commenter for item in comments], ["bob", "carol"])
        self.assertEqual([item.no for item in comments], [1, 2])
        self.assertEqual([item.thank_count for item in comments], [3, 0])

    def test_parse_member_profile(self):
        response = fixture_response(
            "member_standard.html", "https://www.v2ex.com/member/alice"
        )

        member = next(parse_member(response))

        self.assertEqual(member.username, "alice")
        self.assertEqual(member.uid, 123456)
        self.assertGreater(member.create_at, 0)
        self.assertEqual(member.social_link, [{"Website": "https://example.com"}])


if __name__ == "__main__":
    unittest.main()
