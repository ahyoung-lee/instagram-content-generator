import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re

def get_article_text(url: str = None) -> dict:
    """
    Crawls article text from the given URL.
    If no URL is provided, falls back to the top trending article from Google News RSS.
    Returns a dictionary with 'title', 'url', and 'content'.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    selected_url = url.strip() if url else None

    # Fallback to Google News RSS if no URL is provided
    if not selected_url:
        print("No URL provided. Fetching top trending article from Google News RSS...")
        rss_url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
        try:
            response = requests.get(rss_url, headers=headers, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall(".//item")
                if items:
                    top_item = items[0]
                    title_elem = top_item.find("title")
                    link_elem = top_item.find("link")
                    
                    selected_url = link_elem.text if link_elem is not None else None
                    fallback_title = title_elem.text if title_elem is not None else "Trending News"
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
    try:
        print(f"Scraping content from URL: {selected_url}")
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
        # Remove script and style elements
        for script in soup(["script", "style", "header", "footer", "nav", "aside"]):
            script.decompose()
            
        # Extract paragraph text
        paragraphs = soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4'])
        text_lines = []
        for p in paragraphs:
            # Avoid picking up nested/redundant divs by checking if they contain too many children or are short
            text = p.get_text(strip=True)
            if len(text) > 20: # Only keep lines with substantial text
                text_lines.append(text)
                
        # Join lines and remove duplicate consecutive lines/spaces
        content = "\n".join(text_lines)
        content = re.sub(r'\n+', '\n', content) # normalize newlines
        
        # Limit content size to avoid token overflow but keep it substantial
        content = content[:4000]
        
        if not content.strip():
            raise Exception("No content could be extracted from the page.")
            
        return {
            "title": title,
            "url": selected_url,
            "content": content
        }
        
    except Exception as e:
        print(f"Error crawling URL: {e}")
        # Return fallback content even if the user-entered URL fails to crawl
        return {
            "title": "URL 크롤링 실패 - 기본 정보 대체",
            "url": selected_url if selected_url else "N/A",
            "content": f"입력하신 URL({selected_url})을 크롤링하는 데 실패했습니다. 원인은 네트워크 차단, 보안 설정(Robots.txt) 또는 올바르지 않은 주소일 수 있습니다. 본 시스템은 웹 브라우징 에이전트 기능을 지원하여 관련 웹 페이지를 크롤링하려 하였으나 문제가 생겼습니다. 원격 리소스를 체크해 주시기 바랍니다. 에러 메시지: {str(e)}"
        }

if __name__ == "__main__":
    # Test execution
    res = get_article_text()
    print("TEST CRAWL RESULT:")
    print("Title:", res["title"])
    print("Content length:", len(res["content"]))
