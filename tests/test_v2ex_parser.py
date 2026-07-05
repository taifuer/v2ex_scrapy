import unittest

from scrapy.http import HtmlResponse

from v2ex_scrapy.v2ex_parser import parse_topic


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


if __name__ == "__main__":
    unittest.main()
