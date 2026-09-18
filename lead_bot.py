import os
import asyncio
import aiohttp
import json
import logging
import re
import random
from datetime import datetime
import urllib.parse
from google import genai

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

CUSTOM_OFFER_INSTRUCTIONS = """
- PRIMARY FOCUS (CLIENT LEADS): Promote custom web development, custom sites, landing pages, and server setups. Emphasize fast, modern deployment. Always include portfolio link: https://yazoniplay.is-a.dev
- SECONDARY FOCUS (PLAYER LEADS): Invite active Minecraft players to join 'Skyfall SMP'. Mention intense PvP, Lifesteal mechanics, or custom experiences if relevant to their post.
- MANDATORY PREFIX: Every pitch MUST start with 'LEAD: '.
"""

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Enterprise async scaling: decoupled queue system
ai_semaphore = asyncio.Semaphore(2) # Safely bumped to 2 for Flash-Lite
lead_queue = asyncio.Queue()

CACHE_FILE = "seen_leads.json"
HISTORY_FILE = "lead_history.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
]

def load_seen_ids():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_ids(seen_set):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(list(seen_set), f)
    except Exception as e:
        logging.error(f"Failed to save cache: {e}")

seen_ids = load_seen_ids()

# Expanded targets for maximum lead flow
REDDIT_SUBREDDITS = [
    "forhire", "freelance_forhire", "design_jobs", "webdev", "Wordpress", "slavelabour",
    "startups", "smallbusiness", "Entrepreneur",
    "MinecraftServer", "MinecraftBuddies", "mcserver", "smp", "MinecraftLFG", "admincraft"
]

LEMMY_COMMUNITIES = [
    "freelance@lemmy.world", "webdev@lemmy.world", "minecraft@lemmy.world", "mcservers@feddit.uk",
    "technology@lemmy.world", "smallbusiness@lemmy.world"
]

# Advanced Google Dorks routed through DuckDuckGo HTML
SOCIAL_SEARCH_QUERIES = [
    'site:instagram.com "need a website built"',
    'site:instagram.com "hiring web developer"',
    'site:facebook.com/groups "hiring web developer"',
    'site:tiktok.com "need a web developer"',
    'site:twitter.com "looking for a web developer"',
    'site:twitter.com "need a frontend dev"',
    'site:instagram.com "looking for smp"',
    'site:tiktok.com "looking for an smp to join"',
    'site:twitter.com "any good minecraft smps"'
]

WEB_KEYWORDS = ["hiring web", "need a website", "looking for web developer", "website designer", "need a dev", "build me a site", "wordpress", "custom site", "hiring dev", "landing page", "frontend dev"]
SMP_KEYWORDS = ["looking for smp", "looking for a server", "smp to join", "need an smp", "vanilla smp", "lifesteal smp", "pvp smp", "crystal pvp", "looking for players"]
ALL_KEYWORDS = WEB_KEYWORDS + SMP_KEYWORDS

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS)}

async def analyze_with_gemini(title, body):
    if not ai_client:
        return {"category": "CLIENT", "score": 6, "estimated_value": "N/A", "pitch": "LEAD: AI Offline - Check manually.", "ai_failed": True}

    prompt = f"""
    You are an elite Growth Engine for a Web Development Agency & Skyfall SMP.
    Web Development is the MAIN BUSINESS. Find high-value clients.

    Analyze this post:
    Title: "{title}"
    Body: "{body}"

    Determine Category:
    - "CLIENT": Looking for web development, design, portfolio sites, or server configs. (PRIMARY)
    - "PLAYER": Looking for a Minecraft SMP/server.

    Specific Pitch Guidelines:
    {CUSTOM_OFFER_INSTRUCTIONS}

    Tasks:
    1. Score high intent (1-10). (10 = ready to hire/join RIGHT NOW).
    2. Estimate value range: e.g., "$150 - $600" for web clients, "Active Player" for players.
    3. Generate a killer 2-sentence pitch tailored directly to their post.
    IMPORTANT: You MUST start the pitch with the exact text "LEAD: ".

    Respond STRICTLY in JSON format:
    {{"category": "CLIENT", "score": 9, "estimated_value": "$200 - $500", "pitch": "LEAD: Hey! I build fast, tailored websites that drive real growth..."}}
    """

    fallback_models = ['gemini-3.5-flash-lite', 'gemini-3.6-flash', 'gemini-3.1-pro']
    
    async with ai_semaphore:
        for model_name in fallback_models:
            for attempt in range(1, 3):
                try:
                    await asyncio.sleep(1.5) # Slight delay to keep APIs happy
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
                    if "429" in str(e) or "503" in str(e):
                        await asyncio.sleep((4 ** attempt) + random.uniform(1, 3))
                    else:
                        break
    return {"category": "CLIENT", "score": 5, "estimated_value": "N/A", "pitch": "LEAD: Saw your post! Check out my web dev portfolio here: https://yazoniplay.is-a.dev", "ai_failed": True}

async def process_found_lead(session, platform, origin, title, permalink, author, analysis):
    category = analysis.get("category", "CLIENT")
    score = analysis.get("score", 5)
    est_val = analysis.get("estimated_value", "N/A")
    pitch = analysis.get("pitch", "")
    
    if not pitch.startswith("LEAD:"):
        pitch = f"LEAD: {pitch}"

    lead_data = {
        "timestamp": datetime.utcnow().isoformat(), "platform": platform, "origin": origin,
        "title": title, "permalink": permalink, "author": author, "category": category,
        "score": score, "estimated_value": est_val, "pitch": pitch
    }

    try:
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        history.insert(0, lead_data)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history[:200], f, indent=4) # Expanded history to 200
    except Exception:
        pass

    if not DISCORD_WEBHOOK_URL: return

    color = 0x9B59B6 if category == "CLIENT" else (0x2ECC71 if score >= 8 else 0xF1C40F)
    header = f"💼 [CLIENT LEAD] • {platform}" if category == "CLIENT" else f"🎮 [PLAYER] • {platform}"
    
    payload = {
        "username": "Web Dev & Skyfall Growth Engine v8.0",
        "avatar_url": "https://i.imgur.com/8Np8Z9Y.png",
        "embeds": [{
            "title": f"{header} ({origin})",
            "description": f"**Title:** [{title[:150]}]({permalink})\n**Author:** `{author}`",
            "url": permalink,
            "color": color,
            "fields": [
                {"name": "🎯 Intent Score", "value": f"**{score}/10**", "inline": True},
                {"name": "💰 Est. Value", "value": f"**{est_val}**", "inline": True},
                {"name": "🚀 Custom Pitch", "value": f"```{pitch}```"},
            ],
            "footer": {"text": "v8.0 Deep Search Engine • Auto-Logged"}
        }]
    }
    try:
        await session.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        logging.error(f"Discord Webhook Error: {e}")

# --- WORKER QUEUE ---
async def ai_worker(session):
    """Pulls leads from the queue and processes them sequentially to avoid rate limits."""
    while True:
        lead = await lead_queue.get()
        platform, origin, title, body, permalink, author = lead
        
        analysis = await analyze_with_gemini(title, body)
        if analysis.get("score", 0) >= 6 or analysis.get("ai_failed"):
            await process_found_lead(session, platform, origin, title, permalink, author, analysis)
        
        lead_queue.task_done()

# --- SCRAPERS ---
async def fetch_reddit_deep(session, sub):
    """Fetches 'new' posts instead of hot, PLUS historical search for older missed leads."""
    
    # 1. Fetch live new posts
    urls = [f"https://www.reddit.com/r/{sub}/new.json?limit=30"]
    
    # 2. Fetch older unfulfilled posts (Last 30 days and 1 year)
    queries = ["hiring web", "need website", "looking for smp"]
    for q in queries:
        safe_q = urllib.parse.quote(q)
        urls.append(f"https://www.reddit.com/r/{sub}/search.json?q={safe_q}&sort=new&restrict_sr=on&t=month&limit=20")

    for url in urls:
        try:
            async with session.get(url, headers=get_headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for post in data.get("data", {}).get("children", []):
                        p_data = post.get("data", {})
                        post_id = f"reddit_{p_data.get('id')}"
                        title = p_data.get("title", "") or ""
                        body = p_data.get("selftext", "") or ""
                        combined = f"{title} {body}".lower()

                        if any(kw in combined for kw in ALL_KEYWORDS):
                            if post_id not in seen_ids:
                                seen_ids.add(post_id)
                                permalink = f"https://reddit.com{p_data.get('permalink')}"
                                author = f"u/{p_data.get('author', 'Unknown')}"
                                await lead_queue.put(("Reddit", f"r/{sub}", title, body, permalink, author))
        except Exception as e:
            logging.error(f"Error scraping Reddit {sub}: {e}")

async def fetch_lemmy(session, community):
    url = f"https://lemmy.world/api/v3/post/list?community_name={community.split('@')[0]}&limit=30&sort=New"
    try:
        async with session.get(url, headers=get_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                for item in data.get("posts", []):
                    post, creator = item.get("post", {}), item.get("creator", {})
                    post_id = f"lemmy_{post.get('id')}"
                    title, body = post.get("name", "") or "", post.get("body", "") or ""
                    
                    if any(kw in f"{title} {body}".lower() for kw in ALL_KEYWORDS):
                        if post_id not in seen_ids:
                            seen_ids.add(post_id)
                            await lead_queue.put(("Lemmy", community, title, body, post.get("ap_id", ""), f"@{creator.get('name', 'Unknown')}"))
    except Exception:
        pass

async def fetch_social_search(session, query):
    url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
    try:
        async with session.get(url, headers=get_headers()) as resp:
            if resp.status == 200:
                html = await resp.text()
                platform = "Twitter" if "twitter" in query else ("Instagram" if "instagram" in query else "TikTok")
                raw_snippets = re.findall(r'class="result__snippet[^">]*">(.*?)</a>', html, re.DOTALL)
                
                for snippet in raw_snippets[:10]: # Look deeper into search pages
                    clean_text = re.sub(r'<[^>]+>', '', snippet).strip()
                    if not clean_text: continue
                    post_id = f"{platform.lower()}_{hash(clean_text)}"
                    
                    if any(kw in clean_text.lower() for kw in ALL_KEYWORDS):
                        if post_id not in seen_ids:
                            seen_ids.add(post_id)
                            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                            await lead_queue.put((platform, "Deep Search Index", clean_text[:100] + "...", "", search_url, f"{platform} User"))
    except Exception:
        pass

async def main():
    logging.info("🚀 Launching Web Dev Agency & Skyfall SMP Growth Engine v8.0...")
    
    async with aiohttp.ClientSession() as session:
        # Start AI Background Worker
        worker_task = asyncio.create_task(ai_worker(session))
        
        while True:
            logging.info("🕸️ Scrapers firing: Digging for new and historical leads...")
            
            tasks = []
            tasks.extend([fetch_reddit_deep(session, sub) for sub in REDDIT_SUBREDDITS])
            tasks.extend([fetch_lemmy(session, comm) for comm in LEMMY_COMMUNITIES])
            tasks.extend([fetch_social_search(session, q) for q in SOCIAL_SEARCH_QUERIES])
            
            await asyncio.gather(*tasks)
            save_seen_ids(seen_ids)
            
            logging.info(f"⏳ Scraping cycle complete. {lead_queue.qsize()} leads currently in AI processing queue. Sleeping 5 mins...")
            await asyncio.sleep(300) # Scan more aggressively (5 mins instead of 10)

if __name__ == "__main__":
    asyncio.run(main())
