# -*- coding: utf-8 -*-
import os, sys, datetime, re, json, time
from lxml import html
from pyquery import PyQuery as pq

reload(sys)
sys.setdefaultencoding("utf-8")

sys.path.append(os.path.join(os.path.split(os.path.realpath(__file__))[0], '..'))
import BaseCrawler

sys.path.append(os.path.join(os.path.split(os.path.realpath(__file__))[0], '../../../util'))
import loghelper,extract,db, util,url_helper,download, extractArticlePublishedDate

sys.path.append(os.path.join(os.path.split(os.path.realpath(__file__))[0], '../../parser/util2'))
import parser_mysql_util
import parser_mongo_util

#logger
loghelper.init_logger("crawler_yimin_news", stream=True)
logger = loghelper.get_logger("crawler_yimin_news")

NEWSSOURCE = "Yimin"
DATE = None
RETRY = 3
TYPE = 60005
SOURCE =13827
URLS = []
CURRENT_PAGE = 1
linkPattern = "news/index/detail/id/\d+.html"
Nocontents = [
]
columns = [
    {"column": None, "max": 1},
]


class ListCrawler(BaseCrawler.BaseCrawler):
    def __init__(self):
        BaseCrawler.BaseCrawler.__init__(self)

    # 实现
    def is_crawl_success(self, url, content):
        if content.find("</html>") == -1:
            return False

        d = pq(html.fromstring(content.decode("utf-8")))
        title = d('head> title').text().strip()
        logger.info("title: %s url: %s", title, url)
        if title.find("一鸣网") >= 0:
            return True
        return False


def has_news_content(content):
    d = pq(html.fromstring(content.decode("utf-8")))
    title = d('head> title').text().strip()
    temp = title.split('——')
    if len(temp) < 3:
        return False
    if temp[0].strip() == "":
        return False
    return True


def process_news(column, newsurl, content, newspost, download_crawler):
    if has_news_content(content):
        d = pq(html.fromstring(content.decode("utf-8")))

        key = newsurl.split("/")[-1].strip().replace(".html","").replace('detail_','')

        type = TYPE

        category = None

        title = d('div.left.zb-n> h1').text().strip()

        tags = []

        postraw = newspost
        # posturl = parser_mysql_util.get_logo_id(postraw, download_crawler, SOURCE, key, "news")
        (posturl, width, height) = parser_mysql_util.get_logo_id_new(postraw, download_crawler, SOURCE, key, "news")
        if posturl is not None:
            post = str(posturl)
        else:
            post = None

        # brief = d("meta[name='description']").attr("content").replace(u'一鸣网——让发生的发声|智慧共享新媒体平台|上海TMT媒体开创者、一鸣网ymtmt.com','')
        brief = d('div.left.zb-n> p.gy').text().strip()
        news_time = datetime.datetime.now()

        article = d('div.left.zb-n').html()
        contents = extract.extractContents(newsurl, article)

        logger.info("%s, %s, %s, %s -> %s, %s. %s", key, title, news_time, ":".join(tags), category, brief, post)
        # exit()
        mongo = db.connect_mongo()
        collection_news = mongo.article.news
        if collection_news.find_one({"title": title}) is not None:
            logger.info('already exists %s',title)
            mongo.close()
            return

        flag, domain = url_helper.get_domain(newsurl)
        dnews = {
            "date": news_time - datetime.timedelta(hours=8),
            "title": title,
            "link": newsurl,
            "createTime": datetime.datetime.now(),
            "source": SOURCE,
            "key": key,
            "key_int": int(key),
            "type": type,
            "original_tags": tags,
            "processStatus": 0,
            # "companyId": None,
            "companyIds": [],
            "category": category,
            "domain": domain,
            "categoryNames": []
        }
        dcontents = []
        rank = 1
        start = False
        for c in contents:
            if start is False and c["data"].find(brief)>=0 and c["data"].find(title)>=0:
                start = True
                continue
            if start is False:
                continue

            if c["data"].find("-END-") >= 0:
                break
            if c["type"] == "text":
                dc = {
                    "rank": rank,
                    "content": c["data"],
                    "image": "",
                    "image_src": "",
                }
            else:
                if download_crawler is None:
                    dc = {
                        "rank": rank,
                        "content": "",
                        "image": "",
                        "image_src": c["data"],
                    }
                else:
                    (imgurl, width, height) = parser_mysql_util.get_logo_id_new(c["data"], download_crawler, SOURCE, key, "news")
                    if imgurl is not None:
                        dc = {
                            "rank": rank,
                            "content": "",
                            "image": str(imgurl),
                            "image_src": "",
                            "height": int(height),
                            "width": int(width)
                        }
                    else:
                        continue

            logger.info(c["data"])
            dcontents.append(dc)
            rank += 1
        dnews["contents"] = dcontents
        if brief is None or brief.strip() == "":
            brief = util.get_brief_from_news(dcontents)
        if post is None or post.strip() == "":
            post = util.get_posterId_from_news(dcontents)
        if download_crawler is None:
            dnews["post"] = post
        else:
            dnews["postId"] = post
        dnews["brief"] = brief

        if news_time > datetime.datetime.now():
            logger.info("Time: %s is not correct with current time", news_time)
            dnews["date"] = datetime.datetime.now() - datetime.timedelta(hours=8)
        # collection_news.insert(dnews)
        nid = parser_mongo_util.save_mongo_news(dnews)
        logger.info("Done: %s", nid)
        mongo.close()
        # logger.info("*************DONE*************")
    else:
        logger.info( 'has no news content %s',newsurl)
    return


def run_news(column, crawler, download_crawler):
    while True:
        if len(URLS) == 0:
            return
        URL = URLS.pop(0)

        crawler_news(column, crawler, URL["link"], URL["post"], download_crawler)

def crawler_news(column, crawler, newsurl, newspost, download_crawler):
    while True:
        result = crawler.crawl(newsurl, agent=True)
        if result['get'] == 'success':
            #logger.info(result["redirect_url"])
            try:
                process_news(column, newsurl, result['content'], newspost, download_crawler)
            except Exception,ex:
                logger.exception(ex)
            break



def process(content, flag):

    d = pq(html.fromstring(content.decode("utf-8")))
    for a in d('div> div.xw-li'):
        try:
            href = d(a)('div.right> h1> a').attr("href").strip()
            # logger.info(link)
            if re.search(linkPattern, href):
                link = "http://ymtmt.com" + href
                logger.info("Link: %s is right news link", link)
                title = d(a)('div.right> h1> a').text().strip()
                post='http://ymtmt.com' + d(a)('div.photo> a> img').attr("src").strip()
                logger.info("%s-%s", title, post)
                # check mongo data if link is existed
                mongo = db.connect_mongo()
                collection_news = mongo.article.news
                item = collection_news.find_one({"link": link})
                item1 = collection_news.find_one({"title": title})
                mongo.close()

                if ((item is None and item1 is None) or flag == "all") and link not in URLS:
                    linkmap = {
                        "link": link,
                        "post": post
                    }
                    URLS.append(linkmap)
                else:
                    logger.info('already exists %s',link)
            else:
                # logger.info(link)
                pass
        except:
            logger.info("cannot get link")
    return len(URLS)

def run(flag, column, listcrawler, newscrawler, concurrent_num, download_crawler):
    global CURRENT_PAGE
    cnt = 1
    while True:
        key = CURRENT_PAGE

        if flag == "all":
            if key > column["max"]:
                return
        else:
            if cnt == 0 or key > column["max"]:
                return

        CURRENT_PAGE += 1

        url = 'http://www.ymtmt.com/'

        while True:

            result = listcrawler.crawl(url,agent=True)

            if result['get'] == 'success':
                try:
                    cnt = process(result['content'], flag)
                    if cnt > 0:
                        logger.info("%s has %s fresh news", url, cnt)
                        logger.info(URLS)
                        # threads = [gevent.spawn(run_news, column, newscrawler, download_crawler) for i in xrange(concurrent_num)]
                        # gevent.joinall(threads)
                        run_news(column, newscrawler, download_crawler)
                        # exit()

                except Exception,ex:
                    logger.exception(ex)
                    cnt = 0
                break



def start_run(concurrent_num, flag):
    global DATE
    global CURRENT_PAGE
    while True:
        listcrawler = ListCrawler()
        newscrawler = ListCrawler()
        download_crawler = download.DownloadCrawler(use_proxy=False)
        # download_crawler = None

        logger.info("%s news %s start...", NEWSSOURCE, flag)
        # #Re download news of 24 hours
        # dt = datetime.date.today()
        # if DATE != dt:
        #     logger.info("Date changed!!! Back to yesterday")
        #     today = datetime.datetime(dt.year, dt.month, dt.day)
        #     yesterday = datetime.datetime(dt.year, dt.month, dt.day) - datetime.timedelta(days=1)
        #     mongo = db.connect_mongo()
        #     collection_news = mongo.article.news
        #     for nn in list(collection_news.find({"source": SOURCE, "createTime": {"$gt":yesterday, "$lt": today}})):
        #         link = nn["link"]
        #         logger.info("Redownload %s", link)
        #         crawler_news(column={}, crawler=newscrawler, newsurl=link, newspost=None, download_crawler=download_crawler)
        #     DATE = dt

        for column in columns:
            CURRENT_PAGE = 1
            run(flag, column, listcrawler, newscrawler, concurrent_num, download_crawler)

        logger.info("%s news %s end.", NEWSSOURCE, flag)

        if flag == "incr":
            time.sleep(60*8)        #30 minutes
        else:
            return
            #gevent.sleep(86400*3)   #3 days

if __name__ == "__main__":
    if len(sys.argv) > 1:
        param = sys.argv[1]
        if param == "incr":
            start_run(1, "incr")
        elif param == "all":
            start_run(1, "all")
        else:
            link = param
            download_crawler = None
            crawler_news(column={}, crawler=ListCrawler(), newsurl=link, newspost=None, download_crawler=download_crawler)
    else:
        start_run(1, "incr")