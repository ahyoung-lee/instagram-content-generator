import os
import json
import random
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Available color themes. The theme for each carousel is chosen at random
# (independent of the article topic) so the visual palette stays varied.
AVAILABLE_THEMES = ["orange", "blue", "green", "purple", "pink", "teal", "yellow", "red"]

def generate_instagram_plan(article_title: str, article_content: str) -> dict:
    """
    Analyzes article content using OpenAI and generates an Instagram carousel plan.
    Includes a hooking title, slides (2-10 pages), and a concise caption with 4 hashtags.
    Returns a dictionary matching the specified JSON schema.
    """
    openai_key = os.getenv("OPENAI_API_KEY")

    # Fallback response if API key is missing or invalid
    fallback_response = {
        "total_pages": 4,
        "theme": "orange",
        "hooking_title": "AI로 인스타 운영 자동화하는 충격적인 방법?!",
        "slides": [
            {
                "page": 1,
                "type": "cover",
                "main_text": "AI로 인스타그램\n콘텐츠 제작부터 발행까지\n100% 자동화하는 법!"
            },
            {
                "page": 2,
                "type": "content",
                "main_text": "1. 트렌드 수집\n실시간으로 트렌딩 뉴스를 크롤링해\n**핫한 주제를 자동으로 선별합니다**"
            },
            {
                "page": 3,
                "type": "content",
                "main_text": "2. 카피 작성\n도파민을 자극하는 문구와\n**수익화 CTA까지 한 번에 완성**"
            },
            {
                "page": 4,
                "type": "cta",
                "main_text": "여러분 생각은 어떠신가요?\n이 정보를 필요한 친구에게 공유하세요♡"
            }
        ],
        "final_caption": "AI 에이전트로 인스타그램 콘텐츠를 자동 생성하세요\n\n· 실시간 트렌드를 읽어 카드뉴스를 자동 제작\n· 최적화된 본문과 해시태그까지 한 번에 완성\n· 콘텐츠 기획 시간을 절반 이하로 단축\n\n· 제공 시점: 지금 바로 이용 가능\n· 비용: 무료\n· 공식사이트: 공식 홈페이지\n\n#인스타그램자동화 #AI마케팅 #콘텐츠제작 #부업추천",
        "image_prompt": "A photorealistic photograph of a modern laptop and smartphone on a dark walnut desk, soft window light from the side, shallow depth of field, realistic metal and glass texture, empty dark surface across the bottom third."
    }

    if not openai_key or "your_openai_api_key" in openai_key:
        print("Warning: OPENAI_API_KEY is not configured or invalid. Using mock fallback data.")
        return fallback_response

    try:
        client = OpenAI(api_key=openai_key)
        
        prompt = f"""
다음 뉴스 기사의 제목과 내용을 기반으로, 인스타그램 카드뉴스 기획안과 피드 업로드용 본문 캡션을 작성해줘.

[뉴스 제목]: {article_title}
[뉴스 내용]: {article_content}

[작성 요구사항]:
1. 대중의 호기심을 자극하는 강력하고 명확한 대제목(Hooking Title)을 정해줘.
2. 기사 내용을 아주 꼼꼼하고 깊이 있게 정독하여 독자에게 실질적으로 가치 있는 정보와 요점을 빠짐없이 파악해야 해. 요식 행위 수준의 단순 나열이 아니라, 핵심 구체적 수치(날짜·금액·비율·순위 등), 원인·배경, 근거, 그리고 독자가 바로 써먹을 수 있는 실전 팁을 밀도 있게 정리해줘. 각 요점은 '무엇이(핵심 사실)'에 더해 '왜 중요한지 / 어떤 영향이 있는지'까지 한 단계 더 깊이 짚어줘. 추측성 정보나 기사에 없는 내용을 지어내지 말고, 반드시 기사 근거에 기반해서 작성해. 특히, 기사 내에 나열된 핵심 키포인트나 세부 기능/방법의 개수를 명확히 세어보고(예: 기사 제목이나 본문에 6가지 방법이 있다면), 그 개수 그대로 내용 슬라이드를 구성하여 누락되는 부분이 단 하나도 없게 해야 해.
3. 기사 본문의 풍부함과 요점 개수(N개)에 맞게 카드뉴스 총 매수를 **최대 10장(권장: 6장 ~ 10장)**까지 충분히 할애하여 중요 정보가 누락되지 않도록 설계해줘. 예컨대 6가지 핵심 항목이 있다면 표지/마지막을 제외한 중간 내용('content' 타입) 슬라이드를 정확히 6개 생성해야 해.
4. 2번째 카드뉴스 내용부터 중간 페이지들('content' 타입)의 `main_text`는 반드시 아래 구조로 작성해줘:
   - 1번째 줄: "번호. 핵심 소제목" (예: "1. 실시간 트렌드 분석") — 요점의 제목. 12자 이내로 간결하게.
   - 2번째 줄부터: 그 요점의 구체적 설명(수치·사실·예시·팁 포함)을 담되, 한 슬라이드는 '하나의 핵심 요점'만 깊이 있게 다뤄줘. 군더더기 없이 핵심만 깔끔하게 정리해.
   - (매우 중요) 설명이 길면 의미 단위(구/절)로 `\n`을 직접 넣어 한 줄이 대략 16자 이내가 되도록 2~4줄로 자연스럽게 끊어줘. 조사(을/를/이/가/은/는/와/과/의/로)나 접속사(그리고/하지만 등)로 줄을 끝내지 마. 한 문장이 어색하게 잘리지 않도록 읽기 흐름에 맞게 끊는 게 핵심이야.
   - (매우 중요) 각 content 슬라이드에서 독자가 꼭 기억해야 할 '가장 핵심적인 문장 딱 1개'를 골라, 그 문장 전체(제목 줄 제외)를 `**문장**` 형태로 감싸줘. 이렇게 감싼 문장은 이미지에서 키컬러로 강조 표시돼. 예: "구독자가 **3개월 만에 2배 늘었어요**". 강조는 슬라이드당 1개만, 소제목(제목 줄)에는 절대 쓰지 마.
   - (매우 중요) 이모지나 이모티콘은 절대 사용하지 마. 모든 슬라이드는 이모지 없이 오직 텍스트만으로 깔끔하게 작성해줘.
5. 카드뉴스의 첫 페이지는 'cover', 마지막 페이지는 'cta' 타입이어야 하고, 중간 페이지들은 'content' 타입이어야 해.
6. 마지막 'cta' 페이지의 `main_text`는 다른 문장을 절대 섞지 말고, 반드시 정확히 아래의 2줄로만 고정해서 반환해줘 (매우 중요):
여러분 생각은 어떠신가요?\n이 정보를 필요한 친구에게 공유하세요♡
7. 동일한 기사 링크로 여러 번 요청될 수 있으니, 매번 텍스트 생성 시 이전 버전과 다른 깊이 있는 분석 각도나 새로운 유용한 디테일을 찾아 독창적이고 심도 있게 작성해줘.
8. `final_caption`은 장황하게 늘어놓지 말고, 독자가 스크롤하며 3초 안에 핵심을 파악할 수 있도록 아래 구조로 밀도 있게 '핵심화'해서 작성해줘 (매우 중요):
   - (1) 첫 1~2줄: 이 콘텐츠의 가장 중요한 핵심 메시지 한 방(무엇에 관한 것인지, 왜 중요한지)을 강력하게 압축해서 제시해.
   - (2) 그 다음: 기사에서 독자가 꼭 알아야 할 핵심 요점 2~3개만 골라, 각 항목을 짧은 한 줄로 간결하게 정리해(불필요한 미사여구·중복 설명 금지). 각 줄 앞에 '·' 기호를 붙여 목록처럼 보이게 해줘.
   - (3) 실용 정보 블록: 기사가 다루는 대상이 '제품'인지 '정보/서비스'인지 판단해서 아래에 맞게 핵심 실용 정보를 각각 짧은 한 줄로 정리해줘. 각 줄 앞에 '·' 기호를 붙여. 기사에 해당 정보가 실제로 언급된 경우에만 적고, 없는 항목은 억지로 지어내지 말고 생략해.
     · 제품인 경우: 판매가격, 판매처(구매처)를 적어줘. (예: "가격: 89,000원 / 판매처: 공식몰·쿠팡")
     · 정보/서비스인 경우: 언제부터 제공되는지(시행/출시 시점), 비용은 어떻게 드는지(무료/유료·요금), 공식사이트를 적어줘. (예: "제공 시점: 2026년 8월부터 / 비용: 무료 / 공식사이트: example.go.kr")
   - 각 블록 사이에는 `\\n\\n`으로 여백을 줘서 가독성을 확보해. 전체 본문은 군더더기 없이 핵심만 담아 간결하게 유지하고, 별도의 마무리 CTA 문구는 넣지 마.
   - 본문 맨 마지막 줄에는 뉴스 기사의 핵심 키워드를 반영한 대표 해시태그를 딱 4개만 공백으로 구분해서 한 줄에 적어줘. 절대 4개를 초과하거나 미달하지 않도록 정확히 4개의 해시태그로 작성해줘.
9. (매우 중요) 모든 슬라이드와 캡션(main_text, hooking_title, final_caption 등)에 이모지·이모티콘·특수 픽토그램을 절대 넣지 마. 오직 한글/숫자/기본 문장부호 텍스트만 사용해서 깔끔하고 정돈된 느낌으로 작성해줘. (단, 캡션 맨 끝의 해시태그는 예외)
10. (매우 중요) 제공된 뉴스 제목과 본문을 분석하여 대표 키워드를 선정하고, 그 키워드에 맞는 고품질 이미지 생성용 영문 프롬프트(`image_prompt`)를 작성해줘. 인스타그램 카드뉴스의 배경 이미지로 사용되며 **반드시 실사 사진(photorealistic photograph) 스타일**이어야 해. 일러스트, 3D 렌더링, CGI, 만화, 벡터 아트 같은 표현은 절대 쓰지 마. 실제 사진작가가 카메라로 찍을 수 있는 장면만 묘사해줘 — 구체적인 사물, 풍경, 건축물, 클로즈업 질감 위주로 쓰고, 상징적인 아이콘이나 그림은 쓰지 마. 텍스트(글자), 워터마크, 서명, 로고, 사람 얼굴과 인물은 절대 넣지 마. 주제를 대표하는 피사체를 화면 위쪽 2/3에 배치하고 아래쪽 1/3은 단순하고 어둡게 비워두라고 명시해줘 (그 위에 흰 제목 글씨가 올라가기 때문). (예시: "A photorealistic close-up photograph of stacked Korean won banknotes on a dark wooden desk, natural window light from the left, shallow depth of field, realistic paper texture, uncluttered dark shadow across the bottom third")
11. 카드뉴스 강조 색상 테마(`theme`)는 시스템이 랜덤으로 배정하므로 네가 주제에 맞춰 고민할 필요는 없어. `theme` 값은 아무 값이나 넣어도 되고 생략해도 돼 (어차피 무시되고 랜덤 값으로 덮어써져).

반드시 아래 JSON 스키마 구조의 유효한 JSON 객체로만 응답해야 해. 다른 부가적인 텍스트(예: ```json 등)는 제외해줘.

JSON 스키마:
{{
  "total_pages": 7,
  "hooking_title": "대제목 텍스트",
  "theme": "blue",
  "slides": [
    {{"page": 1, "type": "cover", "main_text": "호기심 유발 표지 문구"}},
    {{"page": 2, "type": "content", "main_text": "1. 실시간 개인화\\n사용자 행동을 즉시 학습해\\n맞춤 콘텐츠를 추천합니다\\n**체류 시간이 40% 늘었어요**"}},
    {{"page": 3, "type": "content", "main_text": "2. 시각 지능\\n사진 한 장만 올려도\\n**핵심 정보를 자동으로 정리해줘요**"}},
    {{"page": 4, "type": "content", "main_text": "3. 글쓰기 도구\\n**초안 작성 시간을 절반으로 줄이고**\\n톤앤매너까지 맞춰줍니다"}},
    {{"page": 5, "type": "content", "main_text": "4. 이미지 생성\\n텍스트 설명만으로\\n**고품질 이미지를 몇 초 만에 만들어요**"}},
    {{"page": 6, "type": "content", "main_text": "5. 시리 통합\\n음성 명령 한마디로\\n**앱 실행부터 요약까지 처리합니다**"}},
    {{"page": 7, "type": "cta", "main_text": "여러분 생각은 어떠신가요?\\n이 정보를 필요한 친구에게 공유하세요♡"}}
  ],
  "final_caption": "핵심 메시지 한 방\\n\\n· 핵심 요점 1\\n· 핵심 요점 2\\n· 핵심 요점 3\\n\\n· 가격: 89,000원\\n· 판매처: 공식몰·쿠팡\\n\\n#해시태그1 #해시태그2 #해시태그3 #해시태그4",
  "image_prompt": "A detailed English prompt for a photorealistic photograph based on the selected keywords"
}}
"""

        # High-quality Korean copywriter persona shared across all model calls.
        system_prompt = (
            "너는 인스타그램 트래픽을 지배하는 천재 카피라이터이자 깊이 있는 정보 분석가다. "
            "기사를 꼼꼼히 정독해 핵심 요점을 하나도 빠짐없이 뽑아내고, 각 요점을 "
            "구체적인 수치·사실·근거·실전 팁 중심으로 밀도 있게 정리한다. "
            "2번째 카드뉴스(content)부터는 각 슬라이드가 '하나의 핵심 요점'만 깊이 있게 다루도록 한다. "
            "이모지나 이모티콘은 절대 사용하지 않고, 오직 텍스트만으로 깔끔하고 정돈되게 작성한다. "
            "본문(main_text)은 의미 단위(구/절)로 자연스럽게 줄바꿈(\\n)하되, 조사(을/를/이/가/와/과/의)나 "
            "접속사로 줄을 끝내지 않는다. 각 content 슬라이드에서 가장 핵심적인 문장 1개는 반드시 **문장** 형태로 "
            "감싸 키컬러 강조 대상으로 표시하고, 기사 분위기에 맞는 색상 테마(theme)를 정확히 하나 고른다. "
            "근거 없는 추측이나 밋밋한 텍스트 나열은 절대 허용하지 않는다."
        )

        # Primary model: gpt-4o-mini (this project's API key currently has no
        # access to gpt-4o). gpt-3.5-turbo is kept only as a safety fallback.
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.75,
                max_tokens=3000
            )
        except Exception as chat_err:
            print(f"gpt-4o-mini failed: {chat_err}. Trying gpt-3.5-turbo fallback...")
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.75,
                max_tokens=3000
            )
        
        result_content = response.choices[0].message.content
        data = json.loads(result_content)
        
        # Validate keys in response
        required_keys = ["total_pages", "hooking_title", "slides", "final_caption"]
        if all(key in data for key in required_keys):
            # Assign the color theme at random (ignore any topic-based value the model returned)
            data["theme"] = random.choice(AVAILABLE_THEMES)
            return data
        else:
            raise ValueError("Response missing required keys")

    except Exception as e:
        print(f"Error generating content via OpenAI: {e}")
        # Customize fallback with article-specific basic info if API fails
        fallback_copy = fallback_response.copy()
        fallback_copy["hooking_title"] = f"이슈 분석: {article_title[:20]}..."
        fallback_copy["slides"][0]["main_text"] = f"화제의 이슈!\n{article_title[:15]}\n핵심 요약 정리"
        fallback_copy["slides"][1]["main_text"] = f"기사 본문 내용 요약:\n{article_content[:50]}..."
        fallback_copy["slides"][2]["main_text"] = "트렌드 변화 속에서\n우리가 준비해야 할\n비즈니스 기회는 무엇일까요?"
        fallback_copy["final_caption"] = f"{article_title}\n\n· 지금 가장 주목받는 핵심 이슈 정리\n· 놓치면 안 되는 배경과 포인트\n\n#트렌드이슈 #뉴스요약 #실시간트렌드 #이슈분석"
        fallback_copy["image_prompt"] = f"A photorealistic editorial photograph representing {article_title[:20]}, real objects and natural materials, soft directional daylight, shallow depth of field, dark uncluttered bottom third."
        fallback_copy["theme"] = random.choice(AVAILABLE_THEMES)
        return fallback_copy

if __name__ == "__main__":
    # Test execution
    test_res = generate_instagram_plan("테스트 뉴스 제목", "테스트 본문 내용입니다. 인공지능 마케팅이 화제입니다.")
    print("TEST CREATIVE RESULT:")
    print(json.dumps(test_res, indent=2, ensure_ascii=False))
