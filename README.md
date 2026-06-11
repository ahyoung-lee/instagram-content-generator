# Instagram Content Generator & Auto Publisher

A FastAPI-based web dashboard that automatically scraps trending news articles, generates optimized Instagram carousel/slide content (4:5 ratio card news) using OpenAI, and publishes them directly to Instagram via Meta Graph API.

## Features
- **Trend Scraper**: Crawls Korean news RSS feeds (Hankyoreh, etc.) or specific article URLs.
- **AI Copywriting & Strategy**: Generates a structured multi-slide outline and ready-to-copy captions.
- **Image Generator**: Renders slide images using custom background rotation.
- **Meta Publishing**: Pushes generated card news directly to your Instagram Business account.

---

## Local Development Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   OPENAI_API_KEY=your_openai_api_key
   INSTAGRAM_BUSINESS_ACCOUNT_ID=your_instagram_business_account_id
   META_ACCESS_TOKEN=your_meta_access_token
   PUBLIC_BASE_URL=http://localhost:8000
   ```

3. **Run the Server**:
   ```bash
   python -m uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
   ```
   Open `http://localhost:8000` in your web browser.

---

## 🚀 Live Hosting Deployment (Render.com)

Since this project requires a Python backend to run AI generation and image rendering, it cannot be hosted on static hosts like GitHub Pages. You can host it for free/cheap on **Render** linked to your GitHub repository:

1. **Sign up/Log in** to [Render.com](https://render.com).
2. Click **New +** > **Web Service**.
3. Connect your GitHub repository `ahyoung-lee/instagram-content-generator`.
4. Configure the settings:
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn src.app:app --host 0.0.0.0 --port $PORT`
5. Click **Advanced** and add your **Environment Variables** (keys from your `.env` file):
   - `OPENAI_API_KEY`
   - `INSTAGRAM_BUSINESS_ACCOUNT_ID`
   - `META_ACCESS_TOKEN`
   - `PUBLIC_BASE_URL`: (Set this to the public HTTPS URL provided by Render, e.g. `https://instagram-content-generator.onrender.com`)
6. Click **Deploy Web Service**. 

*Every time you push changes to GitHub, Render will automatically pull the updates and redeploy the live website!*
