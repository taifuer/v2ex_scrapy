import sqlite3


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS period_metrics;
        DROP TABLE IF EXISTS activity_period;
        DROP TABLE IF EXISTS node_period;
        DROP TABLE IF EXISTS tag_period;
        DROP TABLE IF EXISTS title_token_period;
        DROP TABLE IF EXISTS topic_group_period;
        DROP TABLE IF EXISTS topic_group_tag_period;
        DROP TABLE IF EXISTS topic_group_term_period;
        DROP TABLE IF EXISTS topic_group_topic_period;
        DROP TABLE IF EXISTS topic_group_node_period;
        DROP TABLE IF EXISTS representative_post;
        DROP TABLE IF EXISTS first_reply_period;
        DROP TABLE IF EXISTS comment_age_period;
        DROP TABLE IF EXISTS long_tail_period;
        DROP TABLE IF EXISTS discussion_structure_period;
        DROP TABLE IF EXISTS member_activity_period;
        DROP TABLE IF EXISTS engagement_period;

        CREATE TABLE period_metrics (
            period TEXT PRIMARY KEY,
            topic_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            member_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            zero_reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            favorite_sum INTEGER NOT NULL,
            thank_sum INTEGER NOT NULL
        );
        CREATE TABLE activity_period (
            period TEXT NOT NULL,
            weekday INTEGER NOT NULL,
            hour INTEGER NOT NULL,
            topic_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            PRIMARY KEY (period, weekday, hour)
        );
        CREATE TABLE node_period (
            period TEXT NOT NULL,
            node TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            PRIMARY KEY (period, node)
        );
        CREATE TABLE tag_period (
            period TEXT NOT NULL,
            tag TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            PRIMARY KEY (period, tag)
        );
        CREATE TABLE topic_group_period (
            period TEXT NOT NULL,
            group_name TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            PRIMARY KEY (period, group_name)
        );
        CREATE TABLE topic_group_topic_period (
            period TEXT NOT NULL,
            group_name TEXT NOT NULL,
            topic TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            PRIMARY KEY (period, group_name, topic)
        );
        CREATE TABLE first_reply_period (
            period TEXT NOT NULL,
            bucket TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            PRIMARY KEY (period, bucket)
        );
        CREATE TABLE comment_age_period (
            period TEXT NOT NULL,
            bucket TEXT NOT NULL,
            comment_count INTEGER NOT NULL,
            PRIMARY KEY (period, bucket)
        );
        CREATE TABLE long_tail_period (
            period TEXT PRIMARY KEY,
            comment_30d_count INTEGER NOT NULL,
            after_24h_count INTEGER NOT NULL,
            after_7d_count INTEGER NOT NULL,
            eligible_topic_count INTEGER NOT NULL
        );
        CREATE TABLE discussion_structure_period (
            period TEXT PRIMARY KEY,
            replied_topic_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            commenter_count INTEGER NOT NULL,
            author_participated_count INTEGER NOT NULL,
            mention_comment_count INTEGER NOT NULL
        );
        CREATE TABLE member_activity_period (
            period TEXT PRIMARY KEY,
            new_member_count INTEGER NOT NULL,
            author_count INTEGER NOT NULL,
            commenter_count INTEGER NOT NULL
        );
        CREATE TABLE engagement_period (
            period TEXT PRIMARY KEY,
            topic_count INTEGER NOT NULL,
            click_count INTEGER NOT NULL,
            favorite_count INTEGER NOT NULL,
            topic_thank_count INTEGER NOT NULL,
            vote_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            comment_thank_count INTEGER NOT NULL,
            thanked_comment_count INTEGER NOT NULL
        );
        """
    )
