import os
import asyncio
import aiohttp
import json
import logging
import re
import random
import time
from datetime import datetime
from google import genai

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# --- CUSTOM OFFER INSTRUCTIONS FOR GEMINI ---
CUSTOM_OFFER_INSTRUCTIONS = """
- PRIMARY FOCUS (CLIENT LEADS): Promote custom web development, custom sites, and server setups. Always include portfolio link: https://yazoniplay.is-a.dev
- SECONDARY FOCUS (PLAYER LEADS): Invite active Minecraft players to join 'Skyfall SMP'.
- MANDATORY PREFIX: Every pitch MUST start with 'LEAD: '.
"""

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Concurrency lock to prevent parallel spamming of Gemini API and tripping 429 limits
ai_semaphore = asyncio.Semaphore(1)

CACHE_FILE = "seen_leads.json"
HISTORY_FILE = "lead_history.json"

def load_seen_ids():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            logging.error(f"Failed to load cache: {e}")
            return set()
    return set()

def save_seen_ids(seen_set):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(list(seen_set), f)
    except Exception as e:
        logging.error(f"Failed to save cache: {e}")

def log_lead_to_history(lead_data):
    try:
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        
        history.insert(0, lead_data) # Add newest to the top
        
        # Keep only the last 100 leads to save space
        if len(history) > 100:
            history = history[:100]

        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save lead to history file: {e}")

seen_ids = load_seen_ids()

REDDIT_SUBREDDITS = [
    "forhire", "freelance_forhire", "design_jobs", "webdev", "Wordpress",
    "MinecraftServer", "MinecraftBuddies", "mcserver", "smp", "MinecraftLFG", "LFG", "mcstaff", "admincraft"
]

LEMMY_COMMUNITIES = [
    "freelance@lemmy.world", "webdev@lemmy.world", "minecraft@lemmy.world", "mcservers@feddit.uk"
]

SOCIAL_SEARCH_QUERIES = [
    'site:instagram.com "need a website built"',
    'site:instagram.com "hiring web developer"',
    'site:facebook.com/groups "hiring web developer"',
    'site:facebook.com/groups "need web designer"',
    'site:tiktok.com "need a web developer"',
    'site:instagram.com "looking for smp"',
    'site:tiktok.com "looking for an smp to join"'
]

YOUTUBE_SEARCH_QUERIES = [
    'site:youtube.com "looking for web developer"',
    'site:youtube.com "hiring web designer"',
    'site:youtube.com "need website for business"',
    'site:youtube.com "looking for smp to join"'
]

KEYWORDS = [
    "hiring web", "need a website", "looking for web developer", "website designer", 
    "need a dev", "build me a site", "wordpress", "custom site", "hiring dev", "web design",
    "looking for smp", "looking for a server", "looking for server", "smp to join", 
    "need an smp", "vanilla smp", "lifesteal smp", "pvp smp"
]

async def analyze_with_gemini(title, body):
    if not ai_client:
        return {
            "category": "CLIENT", 
            "score": 6, 
            "estimated_value": "N/A (AI Offline)", 
            "pitch": "LEAD: Saw your post! I build fast, custom websites—check out my work at https://yazoniplay.is-a.dev!",
            "ai_failed": True
        }

    prompt = f"""
    You are an elite Growth Engine for a Web Development Agency & Skyfall SMP.
    Web Development is the MAIN BUSINESS.

    Analyze this post:
    Title/Text: "{title}"
    Body: "{body}"

    Determine Category:
    - "CLIENT": Looking for web development, custom sites, design, or technical setups. (PRIMARY)
    - "PLAYER": Looking for a Minecraft SMP/server to join and play.

    Specific Pitch Guidelines:
    {CUSTOM_OFFER_INSTRUCTIONS}

    Tasks:
    1. Score high intent (1-10). (10 = ready to hire or join RIGHT NOW).
    2. Estimate value range: e.g., "$150 - $600" for web clients, "Active Player" for players.
    3. Generate a killer 2-sentence pitch tailored directly to their post.
    IMPORTANT: You MUST start the pitch with the exact text "LEAD: ".

    Respond STRICTLY in JSON format:
    {{
        "category": "CLIENT",
        "score": 9,
        "estimated_value": "$200 - $500",
        "pitch": "LEAD: Hey! I build fast, tailored websites that drive real growth. Take a look at my portfolio at https://yazoniplay.is-a.dev — open to a quick chat?"
    }}
    """

    # Use standard stable flash models with robust free-tier RPM handling
    fallback_models = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-3.6-flash']
    base_delay = 3

    # Acquire semaphore lock so requests are cleanly queued one at a time
    async with ai_semaphore:
        for model_name in fallback_models:
            for attempt in range(1, 3):
                try:
                    # Built-in spacing between requests to stay safe under RPM limits
                    await asyncio.sleep(1.0)
                    
                    response = ai_client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config={"automatic_function_calling": {"disable": True}}
                    )
                    if response and response.text:
                        cleaned = response.text.replace("```json", "").replace("```", "").strip()
                        data = json.loads(cleaned)
                        data["ai_failed"] = False
                        return data
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "503" in error_str or "ResourceExhausted" in error_str:
                        sleep_time = (base_delay ** attempt) + random.uniform(1, 2)
                        logging.warning(f"⚠️ Rate limit hit on {model_name}. Backing off for {sleep_time:.1f}s...")
                        await asyncio.sleep(sleep_time)
                    else:
                        break

    return {
        "category": "CLIENT", 
        "score": 6, 
        "estimated_value": "N/A (AI Busy)", 
        "pitch": "LEAD: Saw your post! Check out my web dev portfolio here: https://yazoniplay.is-a.dev",
        "ai_failed": True
    }

async def process_found_lead(session, platform, origin, title, permalink, author, analysis):
    category = analysis.get("category", "CLIENT")
    score = analysis.get("score", 5)
    est_val = analysis.get("estimated_value", "N/A")
    pitch = analysis.get("pitch", "")
    ai_failed = analysis.get("ai_failed", False)

    if not pitch.startswith("LEAD:"):
        pitch = f"LEAD: {pitch}"

    # Log to local file automatically
    log_lead_to_history({
        "timestamp": datetime.utcnow().isoformat(),
        "platform": platform,
        "origin": origin,
        "title": title,
        "permalink": permalink,
        "author": author,
        "category": category,
        "score": score,
        "estimated_value": est_val,
        "pitch": pitch
    })

    # Send Discord Alert
    if not DISCORD_WEBHOOK_URL:
        return

    if ai_failed:
        color = 0xE67E22
        header = f"⚠️ [GEMINI OFFLINE / FALLBACK LEAD] • {platform}"
    else:
        color = 0x9B59B6 if category == "CLIENT" else (0x2ECC71 if score >= 8 else 0xF1C40F)
        header = f"💼 [PRIMARY CLIENT LEAD] • {platform}" if category == "CLIENT" else f"🎮 [SKYFALL SMP PLAYER] • {platform}"

    payload = {
        "username": "Web Dev & Skyfall Growth Engine v7.2",
        "avatar_url": "https://i.imgur.com/8Np8Z9Y.png",
        "embeds": [{
            "title": f"{header} ({origin})",
            "description": f"**Title:** [{title[:100]}]({permalink})\n**User/Channel:** `{author}`",
            "url": permalink,
            "color": color,
            "fields": [
                {"name": "🎯 Intent Score", "value": f"**{score}/10**", "inline": True},
                {"name": "💰 Est. Value", "value": f"**{est_val}**", "inline": True},
                {"name": "🚀 Custom Pitch", "value": f"```{pitch}```"},
            ],
            "footer": {"text": "Agency & SMP Growth Engine v7.2 • Auto-Logged to lead_history.json"}
        }]
    }

    try:
        async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
            if resp.status not in (200, 204):
                logging.error(f"Discord Webhook status: {resp.status}")
    except Exception as e:
        logging.error(f"Discord Webhook Error: {e}")

async def send_startup_notification(session):
    if not DISCORD_WEBHOOK_URL:
        return

    # Skip heavy AI call on startup to prevent instant 429 rate limit blocks
    payload = {
        "username": "Web Dev & Skyfall Growth Engine Status",
        "avatar_url": "https://i.imgur.com/8Np8Z9Y.png",
        "embeds": [{
            "title": "🟢 [GROWTH ENGINE CYCLE STARTED v7.2]",
            "description": "10-minute automated loop running. Scrapers active, concurrency queue enabled.",
            "color": 0x2ECC71,
            "fields": [
                {"name": "🤖 AI Engine Status", "value": "Operational (Queued & Protected)", "inline": True},
                {"name": "📁 Local Auto-Logging", "value": "Enabled (`lead_history.json`)", "inline": True},
            ],
            "footer": {"text": "Agency & SMP Growth Engine v7.2 • yazoniplay.is-a.dev"}
        }]
    }

    try:
        async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
            if resp.status not in (200, 204):
                logging.error(f"Discord Startup Webhook status: {resp.status}")
    except Exception as e:
        logging.error(f"Discord Startup Webhook Error: {e}")

# --- SCRAPERS ---
async def fetch_reddit(session, sub):
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=20"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ScaleEngine/7.2"}

    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                posts = data.get("data", {}).get("children", [])

                for post in posts:
                    p_data = post.get("data", {})
                    post_id = f"reddit_{p_data.get('id')}"
                    title = p_data.get("title", "") or ""
                    body = p_data.get("selftext", "") or ""
                    author = f"u/{p_data.get('author', 'Unknown')}"
                    combined = f"{title} {body}".lower()

                    if any(kw in combined for kw in KEYWORDS):
                        if post_id not in seen_ids:
                            seen_ids.add(post_id)
                            permalink = f"https://reddit.com{p_data.get('permalink')}"
                            analysis = await analyze_with_gemini(title, body)
                            if analysis.get("score", 5) >= 6 or analysis.get("ai_failed"):
                                await process_found_lead(
                                    session, "Reddit", f"r/{sub}", title, permalink, author, analysis
                                )
    except Exception as e:
        logging.error(f"Error scraping Reddit r/{sub}: {e}")

async def fetch_lemmy(session, community):
    url = f"https://lemmy.world/api/v3/post/list?community_name={community.split('@')[0]}&limit=15&sort=Active"
    headers = {"User-Agent": "ScaleEngine/7.2"}

    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                posts = data.get("posts", [])

                for item in posts:
                    post = item.get("post", {})
                    creator = item.get("creator", {})
                    post_id = f"lemmy_{post.get('id')}"
                    title = post.get("name", "") or ""
                    body = post.get("body", "") or ""
                    author = f"@{creator.get('name', 'Unknown')}"
                    combined = f"{title} {body}".lower()

                    if any(kw in combined for kw in KEYWORDS):
                        if post_id not in seen_ids:
                            seen_ids.add(post_id)
                            permalink = post.get("ap_id", "")
                            analysis = await analyze_with_gemini(title, body)
                            if analysis.get("score", 5) >= 6 or analysis.get("ai_failed"):
                                await process_found_lead(
                                    session, "Lemmy", community, title, permalink, author, analysis
                                )
    except Exception as e:
        logging.error(f"Error scraping Lemmy {community}: {e}")

async def fetch_social_search(session, query):
    url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                html = await resp.text()
                platform = "Instagram" if "instagram" in query else ("Facebook" if "facebook" in query else "TikTok")
                
                raw_snippets = re.findall(r'class="result__snippet[^">]*">(.*?)</a>', html, re.DOTALL)
                for snippet in raw_snippets[:4]:
                    clean_text = re.sub(r'<[^>]+>', '', snippet).strip()
                    if not clean_text:
                        continue

                    post_id = f"{platform.lower()}_{hash(clean_text)}"
                    
                    if any(kw in clean_text.lower() for kw in KEYWORDS):
                        if post_id not in seen_ids:
                            seen_ids.add(post_id)
                            analysis = await analyze_with_gemini(clean_text, "")
                            if analysis.get("score", 5) >= 6 or analysis.get("ai_failed"):
                                await process_found_lead(
                                    session, platform, "Social Index", clean_text[:80] + "...", 
                                    f"https://www.google.com/search?q={query.replace(' ', '+')}", 
                                    f"{platform} User", analysis
                                )
    except Exception as e:
        logging.error(f"Error searching {query}: {e}")

async def fetch_youtube(session, query):
    url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                html = await resp.text()
                raw_snippets = re.findall(r'class="result__snippet[^">]*">(.*?)</a>', html, re.DOTALL)
                
                for snippet in raw_snippets[:5]:
                    clean_text = re.sub(r'<[^>]+>', '', snippet).strip()
                    if not clean_text:
                        continue

                    post_id = f"youtube_{hash(clean_text)}"

                    if any(kw in clean_text.lower() for kw in KEYWORDS):
                        if post_id not in seen_ids:
                            seen_ids.add(post_id)
                            analysis = await analyze_with_gemini(clean_text, "YouTube Content")
                            if analysis.get("score", 5) >= 6 or analysis.get("ai_failed"):
                                await process_found_lead(
                                    session, "YouTube", "Search Index", clean_text[:80] + "...",
                                    f"https://www.youtube.com/results?search_query={query.replace('site:youtube.com ', '').replace(' ', '+')}",
                                    "YouTube Creator", analysis
                                )
    except Exception as e:
        logging.error(f"Error searching YouTube for {query}: {e}")

async def main():
    logging.info("🚀 Launching Web Dev Agency & Skyfall SMP Growth Engine v7.2...")
    while True:
        async with aiohttp.ClientSession() as session:
            await send_startup_notification(session)

            reddit_tasks = [fetch_reddit(session, sub) for sub in REDDIT_SUBREDDITS]
            lemmy_tasks = [fetch_lemmy(session, comm) for comm in LEMMY_COMMUNITIES]
            social_tasks = [fetch_social_search(session, q) for q in SOCIAL_SEARCH_QUERIES]
            youtube_tasks = [fetch_youtube(session, yq) for yq in YOUTUBE_SEARCH_QUERIES]
            
            await asyncio.gather(*reddit_tasks, *lemmy_tasks, *social_tasks, *youtube_tasks)
        
        save_seen_ids(seen_ids)
        
        logging.info("⏳ Cycle complete. Waiting 10 minutes before next scan...")
        await asyncio.sleep(600)

if __name__ == "__main__":
    asyncio.run(main())
