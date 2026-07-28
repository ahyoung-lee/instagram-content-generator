import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re


class ArticleFetchError(Exception):
    """Raised when the article behind a URL could not be read.

    This is deliberately loud. Silently substituting placeholder text used to
    make the AI invent an article out of thin air, producing confident-looking
    cards that had nothing to do with the submitted link.
    """


# Containers that hold the article body on common Korean/global news sites.
# Checked in order; the first one with real text wins.
ARTICLE_SELECTORS = [
    "article",
    "#dic_area",                    # Naver News
    "#articleBodyContents",         # Naver News (legacy)
    "#newsct_article",              # Naver News (current)
    "#article-view-content-div",    # many Korean CMS installs
    ".article-body", ".article_body", ".articleBody",
    ".news-article-body", ".art_text", ".story-news",
    "[itemprop='articleBody']",
    "#articleBody", "#article_body", "#newsEndContents",
    ".entry-content", ".post-content",   # blogs
    "main",
]

# Text that betrays an error/placeholder page rather than an article.
ERROR_PAGE_MARKERS = [
    "페이지가 존재하지 않", "페이지를 찾을 수 없", "사용할 수 없는 페이지",
    "잘못된 접근", "삭제된 기사", "존재하지 않는 기사",
    "page not found", "404 not found", "access denied", "forbidden",
]


def _clean_title(raw: str) -> str:
    """Strips the trailing site name that news sites append to <title>."""
    title = re.sub(r"\s+", " ", (raw or "")).strip()
    # "기사 제목 | 연합뉴스", "기사 제목 - 한겨레", "기사 제목 :: 사이트"
    for sep in ("|", " - ", "::", " — "):
        if sep in title:
            head = title.split(sep)[0].strip()
            # Only accept the split if it left something article-length behind.
            if len(head) >= 8:
                title = head
                break
    return title.strip(" |-:—")


def _extract_title(soup: BeautifulSoup) -> str:
    """Prefers the real headline (og:title / h1) over the browser tab title."""
    og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "title"})
    if og and og.get("content", "").strip():
        return _clean_title(og["content"])

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return _clean_title(h1.get_text(strip=True))

    if soup.title and soup.title.string:
        return _clean_title(soup.title.string)
    return ""


def _text_from(container) -> str:
    """Joins the paragraph text inside one container.

    Only <p> (plus <br>-separated blocks) are read — never <div> — because the
    old code collected nested <div>s and their child <p>s, duplicating the body
    many times over and burying it under navigation text.
    """
    parts = []
    paragraphs = container.find_all("p")
    if paragraphs:
        for p in paragraphs:
            text = p.get_text(" ", strip=True)
            if len(text) >= 20:
                parts.append(text)
    if not parts:
        # Some CMSs dump the body as bare text with <br> separators.
        raw = container.get_text("\n", strip=True)
        parts = [ln.strip() for ln in raw.split("\n") if len(ln.strip()) >= 20]
    return "\n".join(parts)


def _extract_body(soup: BeautifulSoup) -> str:
    """Finds the article body, preferring known containers, else densest block."""
    for selector in ARTICLE_SELECTORS:
        for container in soup.select(selector):
            text = _text_from(container)
            if len(text) >= 200:
                return text

    # Fallback: whichever element holds the most paragraph text.
    best = ""
    for container in soup.find_all(["div", "section"]):
        text = _text_from(container)
        if len(text) > len(best):
            best = text
    return best


def _looks_like_article(text: str) -> tuple:
    """Returns (ok, reason). Rejects nav/headline soup and error pages."""
    stripped = text.strip()
    if len(stripped) < 250:
        return False, f"본문이 너무 짧습니다 ({len(stripped)}자)."

    lowered = stripped[:1500].lower()
    for marker in ERROR_PAGE_MARKERS:
        if marker in lowered or marker in stripped[:1500]:
            return False, "삭제되었거나 존재하지 않는 기사 페이지입니다."

    # A real article is made of sentences. A scraped headline list is a pile of
    # short fragments with almost no sentence enders.
    enders = stripped.count(". ") + stripped.count("다.") + stripped.count("요.") + stripped.count("? ")
    if enders < 3:
        return False, "기사 본문이 아니라 목록/메뉴 텍스트로 보입니다."

    return True, ""


def get_article_text(url: str = None) -> dict:
    """
    Crawls article text from the given URL.
    If no URL is provided, falls back to the top trending article from Hankyoreh RSS.
    Returns a dictionary with 'title', 'url', and 'content'.

    Raises ArticleFetchError when the page cannot be read or does not look like
    an article, so the caller can tell the user instead of generating cards from
    junk (and without spending money on the AI calls).
    """
    selected_url = url.strip() if url else None

    # Fallback to Hankyoreh RSS if no URL is provided
    if not selected_url:
        print("No URL provided. Fetching top trending article from Hankyoreh RSS...")
        rss_url = "https://www.hani.co.kr/rss/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(rss_url, headers=headers, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall(".//item")
                if items:
                    top_item = items[0]
                    title_elem = top_item.find("title")
                    link_elem = top_item.find("link")

                    selected_url = link_elem.text.strip() if link_elem is not None else None
                    fallback_title = title_elem.text.strip() if title_elem is not None else "Trending News"
                    print(f"Top trending article found: {fallback_title} ({selected_url})")
                else:
                    raise Exception("No RSS items found in feed.")
            else:
                raise Exception(f"RSS feed request failed with status: {response.status_code}")
        except Exception as e:
            raise ArticleFetchError(
                f"기사 URL을 입력하지 않았고, 자동으로 가져올 최신 기사도 불러오지 못했습니다. ({e})"
            )

    # Crawl the selected URL
    # We use a dual strategy:
    # 1. No User-Agent (useful for Next.js SSR sites like Newneek that return SPA blank shell to Chrome)
    # 2. Browser User-Agent (useful for standard news sites that block default Python requests)
    strategies = [
        None,
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        }
    ]

    last_error = "알 수 없는 오류"
    for headers in strategies:
        try:
            print(f"Scraping content from URL: {selected_url} (Headers: {'Browser' if headers else 'Default'})")
            res = requests.get(selected_url, headers=headers, timeout=10)
            res.raise_for_status()

            # Decode encoding if not set correctly
            if res.encoding == 'ISO-8859-1':
                res.encoding = res.apparent_encoding

            soup = BeautifulSoup(res.text, 'html.parser')

            # Drop chrome that would otherwise be mistaken for article text.
            for element in soup(["script", "style", "header", "footer", "nav",
                                 "aside", "iframe", "form", "noscript"]):
                element.decompose()

            title = _extract_title(soup)
            content = _extract_body(soup)
            content = re.sub(r'\n{2,}', '\n', content).strip()
            content = content[:6000]

            ok, reason = _looks_like_article(content)
            if ok:
                print(f"Scrape OK: title={title[:40]!r}, {len(content)} chars")
                return {
                    "title": title or "제목 없음",
                    "url": selected_url,
                    "content": content
                }
            last_error = reason
            print(f"Rejected scrape from {selected_url}: {reason}")

        except Exception as e:
            last_error = str(e)
            print(f"Strategy failed for {selected_url}: {e}")

    raise ArticleFetchError(
        f"이 링크의 기사 본문을 읽지 못했습니다. ({last_error}) "
        "기사 본문이 보이는 주소인지 확인해 주세요. 로그인이 필요하거나 "
        "스크래핑을 차단하는 사이트일 수 있습니다."
    )


if __name__ == "__main__":
    # Test execution
    res = get_article_text()
    print("TEST CRAWL RESULT:")
    print("Title:", res["title"])
    print("Content length:", len(res["content"]))
