import math

import scrapy
import scrapy.http.response.html
from scrapy.spidermiddlewares.httperror import HttpError

from v2ex_scrapy import v2ex_parser
from v2ex_scrapy.DB import DB
from v2ex_scrapy.items import CommentItem, MemberItem, TopicItem


def comment_start_page(actual_count: int, refresh_existing: bool) -> int:
    return 2 if refresh_existing else max(2, actual_count // 100 + 1)


def should_crawl_comment_pages(
    actual_count: int,
    expected_count: int,
    update_comments: bool,
    refresh_existing: bool,
) -> bool:
    if expected_count <= 0:
        return False
    if actual_count == 0:
        return True
    return update_comments and (
        refresh_existing or actual_count < expected_count
    )


class CommonSpider:
    def __init__(
        self,
        logger,
        update_member=False,
        update_comment=False,
        crawl_members=True,
        refresh_existing_comments=False,
        parse_comment_callback=None,
        parse_member_callback=None,
        member_errback=None,
    ):
        self.db = DB()
        self.logger = logger
        self.UPDATE_MEMBER = update_member
        self.UPDATE_COMMENT = update_comment
        self.CRAWL_MEMBERS = crawl_members
        self.REFRESH_EXISTING_COMMENTS = refresh_existing_comments
        self.parse_comment_callback = parse_comment_callback or self.parse_comment
        self.parse_member_callback = parse_member_callback or self.parse_member
        self.member_errback = member_errback or self.member_err

    def parse_topic_err(self, failure):
        if failure.check(HttpError):
            topic_id = failure.request.cb_kwargs["topic_id"]
            self.logger.warning(f"Crawl Topic Err {topic_id}")
            yield TopicItem.err_topic(topic_id=topic_id)

    def parse_topic(
        self, response: scrapy.http.response.html.HtmlResponse, topic_id: int
    ):
        self.logger.info(f"Crawl Topic {topic_id}")

        if response.status in {301, 302}:
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
                if should_crawl_comment_pages(
                    c,
                    topic_reply_count,
                    self.UPDATE_COMMENT,
                    self.REFRESH_EXISTING_COMMENTS,
                ):
                    total_page = math.ceil(topic_reply_count / 100)
                    # A forced refresh is also used to repair missing middle pages.
                    # Existing comment IDs are updated in place, so revisiting every
                    # page is both safe and more reliable than inferring continuity
                    # from the stored row count.
                    start_page = comment_start_page(c, self.REFRESH_EXISTING_COMMENTS)
                    for i in range(start_page, total_page + 1):
                        for j in self.crawl_comment(topic_id, i, response):
                            yield j

    def crawl_comment(self, topic_id, page, response):
        yield response.follow(
            f"/t/{topic_id}?p={page}",
            callback=self.parse_comment_callback,
            cb_kwargs={"topic_id": topic_id},
        )

    def parse_comment(self, response: scrapy.http.response.html.HtmlResponse, topic_id):
        for comment_item in v2ex_parser.parse_comment(response, topic_id):
            # skip if comment already exists in DB to avoid duplicate processing
            try:
                exists = self.db.exist(CommentItem, comment_item.id_)
            except Exception:
                exists = False

            if exists and not self.REFRESH_EXISTING_COMMENTS:
                self.logger.debug(f"skip existing comment {comment_item.id_}")
                continue

            yield comment_item
            for i in self.crawl_member(comment_item.commenter, response):
                yield i

    def crawl_member(self, username, response: scrapy.http.response.html.HtmlResponse):
        if self.CRAWL_MEMBERS and username != "" and (
            self.UPDATE_MEMBER or not self.db.exist(MemberItem, username)
        ):
            yield response.follow(
                f"/member/{username}",
                callback=self.parse_member_callback,
                errback=self.member_errback,
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
