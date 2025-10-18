import logging
import re
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import bs4
import icalendar as ical
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEARCH_URL = "https://search.yahoo.co.jp/realtime/search?ei=UTF-8&md=t&p=id%3Anico_utahiro+室料半額DAY"


@dataclass
class Tweet:
    text: str
    url: str
    post_at: datetime

    @staticmethod
    def get_timestamp(tweet_id: int) -> datetime:
        timestamp = (tweet_id >> 22) + 1288834974657
        return datetime.fromtimestamp(timestamp / 1000)

    @classmethod
    def from_tag(cls, tag: bs4.Tag) -> "Tweet":
        body = tag.select_one("[class^=Tweet_body__]")
        text = body.get_text().strip() if body else ""
        link = tag.select_one("[class^=Tweet_time__] a")
        if not link:
            raise ValueError("No link found in tweet tag")
        url = link.get("href")
        if not isinstance(url, str):
            raise ValueError("Invalid URL in tweet tag")
        m = re.search(r"/status/(\d+)", url)
        if not m:
            raise ValueError(f"No tweet ID found in URL: {url}")
        id_ = int(m.group(1))
        post_at = cls.get_timestamp(id_)
        return cls(text=text, url=url, post_at=post_at)


def fetch_tweets() -> Generator[Tweet]:
    resp = requests.get(SEARCH_URL).text
    soup = bs4.BeautifulSoup(resp, "lxml")
    tags = soup.select("[class^=Tweet_TweetContainer__]")
    for tag in tags:
        try:
            yield Tweet.from_tag(tag)
        except ValueError as e:
            logger.warning(f"Failed to parse tweet: {e}", exc_info=True)
            continue


def get_event_date(tweet: Tweet) -> date:
    m = re.search(r"(\d{1,2})月(\d{1,2})日.*室料半額DAY", tweet.text)
    if not m:
        raise ValueError("Date not found in tweet text")
    month = int(m.group(1))
    day = int(m.group(2))
    year = tweet.post_at.year
    if month < tweet.post_at.month:
        year += 1
    return date(year, month, day)


def get_event_key(event: ical.Event) -> tuple[str, date | datetime]:
    return str(event.get("SUMMARY")), event.start


def main():
    with open("docs/utahiro.ics", encoding="utf-8") as f:
        cal: ical.Calendar = ical.Calendar.from_ical(f.read())

    event_set = set(map(get_event_key, cal.events))

    for tweet in fetch_tweets():
        try:
            event_date = get_event_date(tweet)
        except ValueError as e:
            logger.warning(f"Failed to get event date: {e}", exc_info=True)
            continue

        event = ical.Event()
        event.add("SUMMARY", "ウタヒロ室料半額DAY")
        event.add("DTSTART", event_date)
        event.add("DTEND", event_date + timedelta(days=1))
        event.add("DTSTAMP", datetime.now())
        event.add("UID", uuid.uuid4())
        event.add("DESCRIPTION", tweet.text)
        event.add("LOCATION", tweet.url)

        key = get_event_key(event)
        if key not in event_set:
            cal.add_component(event)
            event_set.add(key)

    with open("docs/utahiro.ics", "wb") as f:
        f.write(cal.to_ical())


if __name__ == "__main__":
    main()
