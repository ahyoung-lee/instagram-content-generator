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
                "main_text": "1단계: TrendScout 에이전트가\n실시간으로 트렌딩 뉴스를 크롤링하여\n핫한 주제를 선별합니다."
            },
            {
                "page": 3,
                "type": "content",
                "main_text": "2단계: CreativeWriter가\n도파민을 자극하는 문구와\n수익화 CTA가 담긴 슬라이드를 구성합니다."
            },
            {
                "page": 4,
                "type": "cta",
                "main_text": "이 정보가 마음에 들었다면\n좋아요♥ 부탁드립니다\n감사합니다 ^_^"
            }
        ],
        "final_caption": "🔥 AI로 인스타그램 자동화 시작하기!\n\n매일 무슨 콘텐츠 올릴지 고민되셨나요?\n이제 AI 에이전트 시스템이 실시간 트렌드를 읽어와 최적화된 카드뉴스와 해시태그까지 자동으로 만들어 드립니다!\n\n시간은 절약하고, 수익은 극대화하는 비결이 궁금하다면?\n지금 바로 프로필 링크를 확인해 보세요! 👇\n\n#인스타그램자동화 #인스타마케팅 #수익자동화 #부업추천 #AI마케팅 #1인기업 #디지털노마드 #마케팅에이전트 #인스타성장 #SNS마케팅 #콘텐츠제작 #챗GPT #인공지능 #자동화시스템 #AI비즈니스 #퍼스널브랜딩 #부자되는법 #SNS자동화 #자동수익 #스타트업 #일러스트 #디자인툴 #마케터 #카드뉴스제작 #콘텐츠크리에이터 #트렌드분석 #비즈니스팁 #온라인부업 #재택근무 #alwaysg00d"
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
2. 기사 내용에서 실제로 독자들에게 꼭 필요하고 중요한 정보들을 깊이 있게 파악해 요점을 정리해줘. 단순 요약이 아니라 독자가 이해하기 쉽도록 유용하고 구체적인 수치, 기능, 팁을 포함하여 카드뉴스의 정보 밀도를 높여야 해. 기사의 깊이에 따라 카드뉴스 총 매수는 3장에서 10장 사이로 정해줘.
3. 중간 페이지들('content' 타입)은 핵심 정보를 구조화해서 정리해줘 (예: "1. 핵심기능명 🧠\n상세 정보 내용과 구체적인 예시"). 이모지를 적절히 섞어서 가독성을 높여줘.
4. 카드뉴스의 첫 페이지는 'cover', 마지막 페이지는 'cta' 타입이어야 하고, 중간 페이지들은 'content' 타입이어야 해.
5. 마지막 'cta' 페이지의 `main_text`는 다른 문장을 절대 섞지 말고, 반드시 정확히 아래의 3줄로만 고정해서 반환해줘 (매우 중요):
이 정보가 마음에 들었다면
좋아요♥ 부탁드립니다
감사합니다 ^_^
6. 동일한 기사 링크로 여러 번 요청될 수 있으니, 매번 텍스트 생성 시 이전 버전과 다른 깊이 있는 분석 각도나 새로운 유용한 디테일을 찾아 독창적이고 심도 있게 작성해줘.
7. `final_caption`에는 풍부하고 유용한 정보성 본문 텍스트를 작성하고, 마지막에 관련 해시태그 30개를 공백으로 구분해서 한 줄에 적어줘. 해시태그에는 '#alwaysg00d'가 반드시 포함되어야 해.

반드시 아래 JSON 스키마 구조의 유효한 JSON 객체로만 응답해야 해. 다른 부가적인 텍스트(예: ```json 등)는 제외해줘.

JSON 스키마:
{{
  "total_pages": 4,
  "hooking_title": "대제목 텍스트",
  "slides": [
    {{"page": 1, "type": "cover", "main_text": "호기심 유발 표지 문구"}},
    {{"page": 2, "type": "content", "main_text": "1. 개인화 🧠\n상세 정보 및 예시"}},
    {{"page": 3, "type": "content", "main_text": "2. 시각 지능 👁️\n상세 정보 및 예시"}},
    {{"page": 4, "type": "cta", "main_text": "이 정보가 마음에 들었다면\n좋아요♥ 부탁드립니다\n감사합니다 ^_^"}}
  ],
  "final_caption": "인스타그램 업로드용 전체 본문 텍스트 및 CTA 구문... \\n\\n#해시태그1 #해시태그2 ... #alwaysg00d"
}}
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "너는 인스타그램 트래픽을 지배하는 천재 카피라이터이자 마케팅 에이전트다."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=2000
            )
        except Exception as chat_err:
            print(f"gpt-4o-mini failed: {chat_err}. Trying gpt-4o fallback...")
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "너는 인스타그램 트래픽을 지배하는 천재 카피라이터이자 마케팅 에이전트다."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.8,
                    max_tokens=2000
                )
            except Exception as chat_err2:
                print(f"gpt-4o failed: {chat_err2}. Trying gpt-3.5-turbo fallback...")
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "너는 인스타그램 트래픽을 지배하는 천재 카피라이터이자 마케팅 에이전트다."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.8,
                    max_tokens=2000
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
        fallback_copy["final_caption"] = f"📢 화제의 이슈 소식 안내\n\n{article_title}\n\n상세한 트렌드 분석과 비즈니스 활용 팁은 프로필 링크에서 만나보세요! 👇\n\n#트렌드이슈 #뉴스요약 #alwaysg00d"
        return fallback_copy

if __name__ == "__main__":
    # Test execution
    test_res = generate_instagram_plan("테스트 뉴스 제목", "테스트 본문 내용입니다. 인공지능 마케팅이 화제입니다.")
    print("TEST CREATIVE RESULT:")
    print(json.dumps(test_res, indent=2, ensure_ascii=False))
