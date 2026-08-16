from v2ex_scrapy.config import (
    get_bool_env,
    get_cookie_string,
    get_env,
    get_float_env,
    get_int_env,
    get_proxies,
)

PROXIES = get_proxies()
COOKIES = get_cookie_string()

# Scrapy settings for v2ex_scrapy project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "v2ex_scrapy"

SPIDER_MODULES = ["v2ex_scrapy.spiders"]
NEWSPIDER_MODULE = "v2ex_scrapy.spiders"

if get_bool_env("V2EX_SCRAPY_LOG_TO_FILE"):
    LOG_FILE = "v2ex_scrapy.log"
LOG_FILE_APPEND = False

_JOBDIR = get_env("V2EX_JOBDIR")
if _JOBDIR != "":
    JOBDIR = _JOBDIR

# Identify the crawler and keep an override for authenticated environments that
# require a browser-compatible user agent.
USER_AGENT = get_env(
    "V2EX_USER_AGENT",
    "V2EXDashboardBot/1.0 (+https://github.com/taifuer/v2ex_scrapy; taifu@taifua.com)",
)

# Obey robots.txt rules
ROBOTSTXT_OBEY = get_bool_env("V2EX_ROBOTSTXT_OBEY", True)

# Configure maximum concurrent requests performed by Scrapy (default: 16)
CONCURRENT_REQUESTS = get_int_env("V2EX_CONCURRENT_REQUESTS", 1)
CONCURRENT_REQUESTS_PER_DOMAIN = get_int_env(
    "V2EX_CONCURRENT_REQUESTS_PER_DOMAIN", 1
)

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
DOWNLOAD_DELAY = max(0.0, get_float_env("V2EX_DOWNLOAD_DELAY", 1.0))
RANDOMIZE_DOWNLOAD_DELAY = True
# The download delay setting will honor only one of:
# CONCURRENT_REQUESTS_PER_DOMAIN = 16
# CONCURRENT_REQUESTS_PER_IP = 16

# Disable cookies (enabled by default)
# COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
TELNETCONSOLE_ENABLED = False

# Override the default request headers:
# DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
# }

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
# SPIDER_MIDDLEWARES = {
#    "tutorial_scrapy.middlewares.TutorialScrapySpiderMiddleware": 543,
# }

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
DOWNLOADER_MIDDLEWARES = {
    "v2ex_scrapy.middlewares.ProxyAndCookieDownloaderMiddleware": 543,
    # "v2ex_scrapy.middlewares.RandomUserAgentMiddleware": 544,
    "v2ex_scrapy.middlewares.RateLimitDownloaderMiddleware": 610,
    "v2ex_scrapy.middlewares.SaveHttpStatusToDBMiddleware": 620,
}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
# EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
# }

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
    "v2ex_scrapy.pipelines.TutorialScrapyPipeline": 300,
}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
AUTOTHROTTLE_ENABLED = get_bool_env("V2EX_AUTOTHROTTLE_ENABLED", True)
# The initial download delay
AUTOTHROTTLE_START_DELAY = max(
    DOWNLOAD_DELAY, get_float_env("V2EX_AUTOTHROTTLE_START_DELAY", 2.0)
)
# The maximum download delay to be set in case of high latencies
AUTOTHROTTLE_MAX_DELAY = max(
    AUTOTHROTTLE_START_DELAY,
    get_float_env("V2EX_AUTOTHROTTLE_MAX_DELAY", 60.0),
)
# The average number of requests Scrapy should be sending in parallel to
# each remote server
AUTOTHROTTLE_TARGET_CONCURRENCY = max(
    0.1, get_float_env("V2EX_AUTOTHROTTLE_TARGET_CONCURRENCY", 0.5)
)
V2EX_RATE_LIMIT_RETRIES = get_int_env("V2EX_RATE_LIMIT_RETRIES", 2)
V2EX_RATE_LIMIT_BASE_DELAY = get_float_env("V2EX_RATE_LIMIT_BASE_DELAY", 5.0)
V2EX_RATE_LIMIT_MAX_DELAY = get_float_env("V2EX_RATE_LIMIT_MAX_DELAY", 300.0)
V2EX_RATE_LIMIT_ABORT_AFTER = get_int_env("V2EX_RATE_LIMIT_ABORT_AFTER", 6)
# Enable showing throttling stats for every response received:
# AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
# HTTPCACHE_ENABLED = True
# HTTPCACHE_EXPIRATION_SECS = 0
# HTTPCACHE_DIR = "httpcache"
# HTTPCACHE_IGNORE_HTTP_CODES = []
# HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
