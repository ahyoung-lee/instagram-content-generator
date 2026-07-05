import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def generate_instagram_plan(article_title: str, article_content: str) -> dict:
    """
    Analyzes article content using OpenAI and generates an Instagram carousel plan.
    Includes a hooking title, slides (2-10 pages), and a monetization caption with 30 hashtags.
    Returns a dictionary matching the specified JSON schema.
    """
    openai_key = os.getenv("OPENAI_API_KEY")

    # Fallback response if API key is missing or invalid
    fallback_response = {
        "total_pages": 4,
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
                "main_text": "1단계: TrendScout 에이전트 🕵️‍♂️\n실시간으로 트렌딩 뉴스를 크롤링하여\n핫한 주제를 선별합니다 🔥."
            },
            {
                "page": 3,
                "type": "content",
                "main_text": "2단계: CreativeWriter ✍️\n도파민을 자극하는 문구와\n수익화 CTA가 담긴 슬라이드를 구성합니다 💰."
            },
            {
                "page": 4,
                "type": "cta",
                "main_text": "여러분 생각은 어떠신가요?\n이 정보를 필요한 친구에게 공유하세요♡"
            }
        ],
        "final_caption": "🔥 AI로 인스타그램 자동화 시작하기!\n\n매일 무슨 콘텐츠 올릴지 고민되셨나요?\n이제 AI 에이전트 시스템이 실시간 트렌드를 읽어와 최적화된 카드뉴스와 해시태그까지 자동으로 만들어 드립니다!\n\n시간은 절약하고, 수익은 극대화하는 비결이 궁금하다면?\n지금 바로 프로필 링크를 확인해 보세요! 👇\n\n#인스타그램자동화 #인스타마케팅 #부업추천 #AI마케팅 #콘텐츠제작",
        "image_prompt": "A modern premium digital illustration of a sleek glowing artificial intelligence robot head, side profile, centered, minimalist dark studio background, cinematic lighting, gold and blue accents."
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
   - 1번째 줄: "번호. 핵심 소제목 [이모지]" (예: "1. 실시간 트렌드 분석 🧠") — 요점의 제목. 12자 이내로 간결하게.
   - 2번째 줄부터: 그 요점의 구체적 설명(수치·사실·예시·팁 포함)을 담되, 한 슬라이드는 '하나의 핵심 요점'만 깊이 있게 다뤄줘.
   - (매우 중요) 설명이 길면 의미 단위(구/절)로 `\n`을 직접 넣어 한 줄이 대략 16자 이내가 되도록 2~4줄로 자연스럽게 끊어줘. 조사(을/를/이/가/은/는/와/과/의/로)나 접속사(그리고/하지만 등)로 줄을 끝내지 마. 한 문장이 어색하게 잘리지 않도록 읽기 흐름에 맞게 끊는 게 핵심이야.
   - 각 요점·문맥마다 딱 들어맞는 직관적이고 다채로운 이모지(예: 🧠, 👁️, ✍️, 🎨, 🤖, 🚀, 🔥, 💡, 📈, 💬 등)를 슬라이드당 2~4개 이상 풍부하게 섞어 가독성을 극대화해줘. 절대 이모지 없이 텍스트만 밋밋하게 나열되지 않게 해줘!
5. 카드뉴스의 첫 페이지는 'cover', 마지막 페이지는 'cta' 타입이어야 하고, 중간 페이지들은 'content' 타입이어야 해.
6. 마지막 'cta' 페이지의 `main_text`는 다른 문장을 절대 섞지 말고, 반드시 정확히 아래의 2줄로만 고정해서 반환해줘 (매우 중요):
여러분 생각은 어떠신가요?\n이 정보를 필요한 친구에게 공유하세요♡
7. 동일한 기사 링크로 여러 번 요청될 수 있으니, 매번 텍스트 생성 시 이전 버전과 다른 깊이 있는 분석 각도나 새로운 유용한 디테일을 찾아 독창적이고 심도 있게 작성해줘.
8. `final_caption`에는 풍부하고 유용한 정보성 본문 텍스트를 작성하고, 마지막에 관련 해시태그는 뉴스 기사의 핵심 키워드를 반영한 대표적인 해시태그 딱 5개만 공백으로 구분해서 한 줄에 적어줘. 절대 5개를 초과하거나 미달하지 않도록 정확히 5개의 해시태그로 작성해줘.
9. (매우 중요) 두 번째 카드뉴스 슬라이드부터는 문장 곳곳에 이모지를 다채롭게 배치하여, 스마트폰으로 보는 독자들이 한눈에 직관적으로 이해하고 쉽게 읽을 수 있도록 써야 해.
10. (매우 중요) 제공된 뉴스 제목과 본문을 분석하여 대표 키워드를 선정하고, 그 키워드에 맞는 고품질 DALL-E 이미지용 영문 프롬프트(`image_prompt`)를 작성해줘. 인스타그램 카드뉴스의 전체적인 배경 이미지로 사용될 것이므로, 절대 텍스트(글자), 워터마크, 서명, 지저분한 패턴, 세부 얼굴 묘사 등은 제외하고, 중심이 되는 주요 상징 오브젝트(예: 로봇, 뇌, 스마트폰, 돈, 차트 등)가 입체적이고 고급스럽게 묘사된 3D 렌더링 혹은 미래지향적인 프리미엄 일러스트 스타일로 작성해줘. 배경은 어둡고 깔끔한 스튜디오 조명 느낌을 권장해. (예시: "A premium 3D render of a futuristic glowing brain icon, cybernetic lines, centered on a clean dark gradient background, cinematic lighting, gold and blue highlights")

반드시 아래 JSON 스키마 구조의 유효한 JSON 객체로만 응답해야 해. 다른 부가적인 텍스트(예: ```json 등)는 제외해줘.

JSON 스키마:
{{
  "total_pages": 7,
  "hooking_title": "대제목 텍스트",
  "slides": [
    {{"page": 1, "type": "cover", "main_text": "호기심 유발 표지 문구"}},
    {{"page": 2, "type": "content", "main_text": "1. 실시간 개인화 🧠\\n사용자 행동을 즉시 학습해\\n맞춤 콘텐츠를 추천합니다 🔥\\n체류 시간이 40% 늘었어요 📈"}},
    {{"page": 3, "type": "content", "main_text": "2. 시각 지능 👁️\\n사진 한 장만 올려도\\n핵심 정보를 자동으로 정리해줘요 🚀"}},
    {{"page": 4, "type": "content", "main_text": "3. 글쓰기 도구 ✍️\\n초안 작성 시간을 절반으로 줄이고\\n톤앤매너까지 맞춰줍니다 💬"}},
    {{"page": 5, "type": "content", "main_text": "4. 이미지 생성 🎨\\n텍스트 설명만으로\\n고품질 이미지를 몇 초 만에 만들어요 ✨"}},
    {{"page": 6, "type": "content", "main_text": "5. 시리 통합 🤖\\n음성 명령 한마디로\\n앱 실행부터 요약까지 처리합니다 💡"}},
    {{"page": 7, "type": "cta", "main_text": "여러분 생각은 어떠신가요?\\n이 정보를 필요한 친구에게 공유하세요♡"}}
  ],
  "final_caption": "인스타그램 업로드용 전체 본문 텍스트 및 CTA 구문... \\n\\n#해시태그1 #해시태그2 #해시태그3 #해시태그4 #해시태그5",
  "image_prompt": "A premium detailed English prompt for DALL-E based on the selected keywords"
}}
"""

        # High-quality Korean copywriter persona shared across all model calls.
        system_prompt = (
            "너는 인스타그램 트래픽을 지배하는 천재 카피라이터이자 깊이 있는 정보 분석가다. "
            "기사를 꼼꼼히 정독해 핵심 요점을 하나도 빠짐없이 뽑아내고, 각 요점을 "
            "구체적인 수치·사실·근거·실전 팁 중심으로 밀도 있게 정리한다. "
            "2번째 카드뉴스(content)부터는 각 슬라이드가 '하나의 핵심 요점'만 깊이 있게 다루도록 하고, "
            "요점마다 딱 맞는 다채로운 이모지를 2개 이상 적극적으로 배치해 가독성을 극대화한다. "
            "본문(main_text)은 의미 단위(구/절)로 자연스럽게 줄바꿈(\\n)하되, 조사(을/를/이/가/와/과/의)나 "
            "접속사로 줄을 끝내지 않는다. 근거 없는 추측이나 밋밋한 텍스트 나열은 절대 허용하지 않는다."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.75,
                max_tokens=3000
            )
        except Exception as chat_err:
            print(f"gpt-4o failed: {chat_err}. Trying gpt-4o-mini fallback...")
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
            except Exception as chat_err2:
                print(f"gpt-4o-mini failed: {chat_err2}. Trying gpt-3.5-turbo fallback...")
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
        fallback_copy["final_caption"] = f"📢 화제의 이슈 소식 안내\n\n{article_title}\n\n상세한 트렌드 분석과 비즈니스 활용 팁은 프로필 링크에서 만나보세요! 👇\n\n#트렌드이슈 #뉴스요약 #실시간트렌드 #이슈분석 #핫토픽"
        fallback_copy["image_prompt"] = f"A premium 3D digital illustration representing {article_title[:20]}, dark clean background, sleek glowing design, neon lighting, cinematic rendering."
        return fallback_copy

if __name__ == "__main__":
    # Test execution
    test_res = generate_instagram_plan("테스트 뉴스 제목", "테스트 본문 내용입니다. 인공지능 마케팅이 화제입니다.")
    print("TEST CREATIVE RESULT:")
    print(json.dumps(test_res, indent=2, ensure_ascii=False))
