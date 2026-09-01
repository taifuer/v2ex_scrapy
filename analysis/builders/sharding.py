import hashlib


MEMBER_PROFILE_BUCKET_COUNT = 64
MEMBER_COMMENT_BUCKET_COUNT = 64
ENTITY_PERIOD_COMMENT_BUCKET_COUNT = 2048
TAG_DETAIL_BUCKET_COUNT = 64
TAG_PERIOD_POST_BUCKET_COUNT = 256
NODE_DETAIL_BUCKET_COUNT = 64
NODE_PERIOD_POST_BUCKET_COUNT = 256


def hashed_bucket(value: str, bucket_count: int) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    width = max(1, len(format(bucket_count - 1, "x")))
    return format(int(digest[:8], 16) % bucket_count, f"0{width}x")


def bucket_names(bucket_count: int) -> list[str]:
    width = max(1, len(format(bucket_count - 1, "x")))
    return [format(index, f"0{width}x") for index in range(bucket_count)]


def tag_detail_bucket(tag: str) -> str:
    return hashed_bucket(tag, TAG_DETAIL_BUCKET_COUNT)


def tag_period_post_bucket(tag: str) -> str:
    return hashed_bucket(tag, TAG_PERIOD_POST_BUCKET_COUNT)


def node_detail_bucket(node: str) -> str:
    return hashed_bucket(node, NODE_DETAIL_BUCKET_COUNT)


def node_period_post_bucket(node: str) -> str:
    return hashed_bucket(node, NODE_PERIOD_POST_BUCKET_COUNT)


def entity_period_comment_bucket(value: str) -> str:
    return hashed_bucket(value, ENTITY_PERIOD_COMMENT_BUCKET_COUNT)


def member_profile_bucket(username: str) -> str:
    return hashed_bucket(username, MEMBER_PROFILE_BUCKET_COUNT)


def member_comment_bucket(username: str) -> str:
    digest = hashlib.sha1(username.encode("utf-8")).hexdigest()
    return format(int(digest[:2], 16) % MEMBER_COMMENT_BUCKET_COUNT, "02x")
