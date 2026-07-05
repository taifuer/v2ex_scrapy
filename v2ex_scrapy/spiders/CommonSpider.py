import math

import scrapy
import scrapy.http.response.html
from scrapy.spidermiddlewares.httperror import HttpError

from v2ex_scrapy import v2ex_parser
from v2ex_scrapy.DB import DB
from v2ex_scrapy.items import CommentItem, MemberItem, TopicItem


class CommonSpider:
    def __init__(self, logger, update_member=False, update_comment=False):
        self.db = DB()
        self.logger = logger
        self.UPDATE_MEMBER = update_member
        self.UPDATE_COMMENT = update_comment

    def parse_topic_err(self, failure):
        if failure.check(HttpError):
            topic_id = failure.request.cb_kwargs["topic_id"]
            self.logger.warning(f"Crawl Topic Err {topic_id}")
            yield TopicItem.err_topic(topic_id=topic_id)

    def parse_topic(
        self, response: scrapy.http.response.html.HtmlResponse, topic_id: int
    ):
        self.logger.info(f"Crawl Topic {topic_id}")

        if response.status == 302:
            # need login or account too young
            yield TopicItem.err_topic(topic_id=topic_id)
        else:
            for i in v2ex_parser.parse_topic_supplement(response, topic_id):
                yield i
            for topic in v2ex_parser.parse_topic(response, topic_id):
                yield topic
                for i in self.crawl_member(topic.author, response):
                    yield i
                for i in self.parse_comment(response, topic_id):
                    yield i
                # crawl sub page comments using the count parsed with the topic
                topic_reply_count = topic.reply_count
                # use actual stored comment count to decide which pages to fetch
                c = self.db.get_comment_count_by_topic(topic_id)
                if (
                    # 爬了一部分 并且设置更新评论
                    (0 < c < topic_reply_count)
                    and self.UPDATE_COMMENT
                ) or (
                    # 没有爬 并且有评论
                    topic_reply_count > 0
                    and c == 0
                ):
                    total_page = math.ceil(topic_reply_count / 100)
                    # Revisit a partially stored page; parse_comment skips duplicates.
                    start_page = max(2, c // 100 + 1)
                    for i in range(start_page, total_page + 1):
                        for j in self.crawl_comment(topic_id, i, response):
                            yield j

    def crawl_comment(self, topic_id, page, response):
        yield response.follow(
            f"/t/{topic_id}?p={page}",
            callback=self.parse_comment,
            cb_kwargs={"topic_id": topic_id},
        )

    def parse_comment(self, response: scrapy.http.response.html.HtmlResponse, topic_id):
        for comment_item in v2ex_parser.parse_comment(response, topic_id):
            # skip if comment already exists in DB to avoid duplicate processing
            try:
                exists = self.db.exist(CommentItem, comment_item.id_)
            except Exception:
                exists = False

            if exists:
                self.logger.debug(f"skip existing comment {comment_item.id_}")
                continue

            yield comment_item
            for i in self.crawl_member(comment_item.commenter, response):
                yield i

    def crawl_member(self, username, response: scrapy.http.response.html.HtmlResponse):
        if username != "" and (
            self.UPDATE_MEMBER or not self.db.exist(MemberItem, username)
        ):
            yield response.follow(
                f"/member/{username}",
                callback=self.parse_member,
                errback=self.member_err,
                cb_kwargs={"username": username},
            )

    def member_err(self, failure):
        if failure.check(HttpError):
            username = failure.request.cb_kwargs["username"]
            self.logger.warning(f"Crawl Member Err {username}")
            yield MemberItem(
                username=username,
                avatar_url="",
                create_at=0,
                social_link=[],
                uid=-1,
            )

    def parse_member(
        self, response: scrapy.http.response.html.HtmlResponse, username: str
    ):
        self.logger.info(f"Crawl Member {username}")
        for i in v2ex_parser.parse_member(response=response):
            yield i
