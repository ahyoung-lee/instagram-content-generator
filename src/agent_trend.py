import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re

def get_article_text(url: str = None) -> dict:
    """
    Crawls article text from the given URL.
    If no URL is provided, falls back to the top trending article from Hankyoreh RSS.
    Returns a dictionary with 'title', 'url', and 'content'.
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
            print(f"Failed to fetch RSS feed: {e}")
            # Absolute fallback
            return {
                "title": "인공지능과 생산성 혁신",
                "url": "N/A",
                "content": "최근 생성형 AI 기술의 급격한 발전으로 많은 지식 노동자와 창작자들의 업무 프로세스가 변화하고 있습니다. 특히 마케팅 문구 작성, 이미지 생성, 소셜 미디어 관리 등 자동화할 수 있는 영역이 확대되며 적은 시간으로 최대의 효율을 내는 1인 기업 및 크리에이터들이 증가하고 있습니다. 이러한 트렌드는 단순 기술 활용을 넘어 수익 모델의 변화로 이어지고 있습니다."
            }

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

    last_error = ""
    for headers in strategies:
        try:
            print(f"Scraping content from URL: {selected_url} (Headers: {'Browser' if headers else 'Default'})")
            res = requests.get(selected_url, headers=headers, timeout=10)
            res.raise_for_status()
            
            # Decode encoding if not set correctly
            if res.encoding == 'ISO-8859-1':
                res.encoding = res.apparent_encoding
                
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Get title
            title = ""
            if soup.title:
                title = soup.title.string.strip()
            if not title:
                title = soup.find('h1')
                title = title.text.strip() if title else "Scraped Article"
                
            # Clean article text
            # Remove script, style and navigation elements
            for element in soup(["script", "style", "header", "footer", "nav", "aside", "iframe"]):
                element.decompose()
                
            # Extract paragraph text
            paragraphs = soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4'])
            text_lines = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 30: # Only keep lines with substantial text to avoid nav links
                    text_lines.append(text)
                    
            content = "\n".join(text_lines)
            content = re.sub(r'\n+', '\n', content) # normalize newlines
            content = content[:4000]
            
            if len(content.strip()) > 150: # Check if we got substantial content
                return {
                    "title": title,
                    "url": selected_url,
                    "content": content
                }
            else:
                last_error = f"Content extracted was too short ({len(content.strip())} chars)."
                
        except Exception as e:
            last_error = str(e)
            print(f"Strategy failed for {selected_url}: {e}")

    # Fallback response if all strategies failed
    return {
        "title": f"크롤링 대체: {selected_url}",
        "url": selected_url,
        "content": f"입력하신 URL({selected_url})을 크롤링하는 데 실패하여 기본 정보로 대체합니다. 원인은 네트워크 차단, 보안 설정(Robots.txt) 또는 동적 클라이언트 렌더링일 수 있습니다. (오류 메시지: {last_error})"
    }

if __name__ == "__main__":
    # Test execution
    res = get_article_text()
    print("TEST CRAWL RESULT:")
    print("Title:", res["title"])
    print("Content length:", len(res["content"]))
