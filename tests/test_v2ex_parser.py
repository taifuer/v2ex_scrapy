import unittest
from pathlib import Path

from lxml import etree
from scrapy.http import HtmlResponse

from v2ex_scrapy.utils import time_to_timestamp
from v2ex_scrapy.v2ex_parser import (
    has_empty_reply_section, parse_comment, parse_member, parse_topic, parse_topic_supplement,
)


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

    def test_parse_comments_inside_topic_replies_wrapper(self):
        response = fixture_response(
            "topic_standard.html", "https://v2ex.com/t/123?p=2"
        )
        expected = list(parse_comment(response, 123))
        main = response.selector.root.xpath('//*[@id="Main"]')[0]
        wrapper = etree.Element("div", id="topic-replies")
        for child in list(main):
            wrapper.append(child)
        main.append(wrapper)
        response = response.replace(body=etree.tostring(
            response.selector.root, encoding="utf-8", method="html"
        ))

        comments = list(parse_comment(response, 123))

        self.assertEqual([item.id_ for item in comments], [101, 102])
        for actual, original in zip(comments, expected):
            self.assertEqual(actual.commenter, original.commenter)
            self.assertEqual(actual.thank_count, original.thank_count)
            self.assertEqual(actual.content, original.content)
            self.assertEqual(actual.create_at, original.create_at)
            self.assertEqual(actual.no, original.no)
            self.assertEqual(actual.topic_id, 123)

    def test_non_reply_cells_are_not_comments(self):
        response = HtmlResponse(
            url="https://v2ex.com/t/123",
            body=b'<div id="Main"><div class="box">'
                 b'<div class="cell" id="topic_123"><table><tr><td>'
                 b'Topic controls</td></tr></table></div></div></div>',
            encoding="utf-8",
        )

        self.assertEqual(list(parse_comment(response, 123)), [])

    def test_empty_reply_section_keeps_the_positive_snapshot(self):
        response = fixture_response("topic_empty_replies.html", "https://v2ex.com/t/123")
        self.assertTrue(has_empty_reply_section(response, 123))
        self.assertEqual(next(parse_topic(response, 123)).reply_count, 1)
        self.assertEqual(list(parse_comment(response, 123)), [])

    def test_empty_reply_section_rejects_unconfirmed_pages(self):
        for case in ("logged_out", "missing_topic", "missing_section", "changed_row", "multi_page", "http_error"):
            with self.subTest(case=case):
                response = fixture_response("topic_empty_replies.html", "https://v2ex.com/t/123")
                root = response.selector.root
                if case in {"logged_out", "missing_topic", "missing_section"}:
                    selector = {"logged_out": 'a[href="/signout"]', "missing_topic": '.header',
                                "missing_section": '#topic-replies'}[case]
                    element = response.css(selector)[0].root
                    element.getparent().remove(element)
                elif case == "changed_row":
                    response.css('#topic-replies > .box')[0].root.append(etree.Element("article"))
                elif case == "multi_page":
                    response.css('#topic-replies .gray')[0].root.text = "101 条回复"
                response = response.replace(
                    status=500 if case == "http_error" else 200,
                    body=etree.tostring(root, encoding="utf-8", method="html"),
                )
                self.assertFalse(has_empty_reply_section(response, 123))

    def test_parse_member_profile(self):
        response = fixture_response(
            "member_standard.html", "https://www.v2ex.com/member/alice"
        )

        member = next(parse_member(response))

        self.assertEqual(member.username, "alice")
        self.assertEqual(member.uid, 123456)
        self.assertGreater(member.create_at, 0)
        self.assertEqual(member.social_link, [{"Website": "https://example.com"}])

    def test_supplements_use_their_own_exact_timestamp(self):
        response = fixture_response(
            "topic_supplements.html", "https://www.v2ex.com/t/123"
        )
        supplements = list(parse_topic_supplement(response, 123))
        self.assertEqual([item.create_at for item in supplements], [
            time_to_timestamp("2026-09-05 11:00:00 +08:00"),
            time_to_timestamp("2026-09-07 12:00:00 +08:00"),
            0,
        ])
        self.assertEqual(supplements[0].content, "First supplement")
        self.assertTrue(all(item.topic_id == 123 for item in supplements))


if __name__ == "__main__":
    unittest.main()
