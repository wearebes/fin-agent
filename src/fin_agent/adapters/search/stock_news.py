"""Public A-share news with dates, source links and bounded article excerpts."""

import re
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from fin_agent.domain.types import SearchResponse, SearchResultItem


def stock_news(ticker: str) -> SearchResponse:
    match = re.fullmatch(r"(?:(sh|sz|bj))?(\d{6})(?:\.(SS|SZ|BJ))?", ticker, re.I)
    if not match:
        return SearchResponse(query=ticker)
    prefix, code, suffix = match.groups()
    market = (
        prefix
        or ({"SS": "sh", "SZ": "sz", "BJ": "bj"}.get((suffix or "").upper()))
        or ("sh" if code.startswith("6") else "sz")
    ).lower()
    url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{market}{code}.phtml"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    response.encoding = "gb18030"
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    for link in soup.select(".datelist a"):
        href = link.get("href", "")
        parsed = urlsplit(href)
        host = parsed.hostname or ""
        if (
            parsed.scheme not in ("http", "https")
            or parsed.username
            or parsed.password
            or not host.endswith((".sina.com.cn", ".sina.cn"))
            or "/aiassist/" in href
        ):
            continue
        title = link.get_text(strip=True)
        date = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", str(link.previous_sibling))
        items.append(
            SearchResultItem(
                title=title,
                url=href,
                text=f"{date.group() if date else 'Date unspecified'} | {title} | "
                "News headline only; article body not retrieved.",
            )
        )
        if len(items) == 8:
            break
    # Read a bounded set of original articles; keep headlines if a publisher is unavailable.
    for item in items[:3]:
        try:
            article_response = requests.get(item.url, timeout=15, allow_redirects=False)
            article_response.raise_for_status()
            if article_response.status_code != 200:
                continue
            article_response.encoding = article_response.apparent_encoding
            article_soup = BeautifulSoup(article_response.text, "html.parser")
            article = article_soup.select_one("#artibody") or article_soup.select_one(".article")
            if article:
                for hidden in article.select("script, style"):
                    hidden.decompose()
                body = article.get_text(" ", strip=True)
                if body:
                    item.text = item.text.replace(
                        "News headline only; article body not retrieved.",
                        f"Article excerpt (may be truncated): {body[:4500]}",
                    )
        except requests.RequestException:
            continue
    return SearchResponse(query=ticker, results=items)
