import os
import asyncio
import aiohttp
import json
import logging
import re
import random
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from google import genai

# --- ANSI TERMINAL COLORS ---
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'

logging.basicConfig(level=logging.INFO, format=f"{Colors.CYAN}%(asctime)s{Colors.RESET} - %(levelname)s - %(message)s")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

CUSTOM_OFFER_INSTRUCTIONS = """
- PRIMARY FOCUS: Sell custom web dev, dynamic portfolios, landing pages, and complex Minecraft server setups (Velocity, Paper, Skript). Emphasize fast deployment via modern hosting. Portfolio: https://yazoniplay.is-a.dev
- SECONDARY FOCUS: Recruit for 'Skyfall SMP'. Highlight custom Lifesteal/PvP mechanics.
- MANDATORY PREFIX: 'LEAD: '
"""

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- ENTERPRISE ARCHITECTURE ---
ai_semaphore = asyncio.Semaphore(3) # Increased concurrent AI processing
lead_queue = asyncio.Queue()
DB_PATH = "hunter_engine.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS leads 
                 (id TEXT PRIMARY KEY, platform TEXT, origin TEXT, title TEXT, 
                  permalink TEXT, author TEXT, category TEXT, score INTEGER, 
                  est_value TEXT, pitch TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

def is_seen(post_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM leads WHERE id = ?", (post_id,))
    result = c.fetchone()
    conn.close()
    return bool(result)

def save_lead_to_db(post_id, data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO leads 
                 (id, platform, origin, title, permalink, author, category, score, est_value, pitch, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (post_id, data['platform'], data['origin'], data['title'], data['permalink'], 
               data['author'], data['category'], data['score'], data['est_value'], data['pitch'], datetime.utcnow()))
    conn.commit()
    conn.close()

init_db()

# --- DYNAMIC ROTATION & EVASION ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
]

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json", "Connection": "keep-alive"}

# --- TARGET VECTORS ---
REDDIT_SUBS = ["forhire", "freelance_forhire", "webdev", "slavelabour", "startups", "smallbusiness", "Entrepreneur", "MinecraftServer", "mcserver", "smp", "admincraft"]
LEMMY_COMMUNITIES = ["freelance@lemmy.world", "webdev@lemmy.world", "minecraft@lemmy.world", "smallbusiness@lemmy.world"]
GITHUB_QUERIES = ["label:hiring", "need a developer", "website bounty"]
SOCIAL_QUERIES = ['site:twitter.com "looking for a web developer"', 'site:twitter.com "need a frontend dev"', 'site:tiktok.com "looking for an smp"']

# --- HEURISTIC PRE-FILTERING ENGINE ---
# We score the text locally before wasting AI bandwidth.
HIGH_VALUE_TRIGGERS = ["hiring", "budget is", "paid gig", "looking to hire", "pay you to", "freelance project", "need a dev"]
SMP_TRIGGERS = ["looking for smp", "smp to join", "need an smp", "lifesteal smp", "crystal pvp"]
NEGATIVE_TRIGGERS = ["how to", "tutorial", "guide", "help with", "error", "bug fix", "my code", "open source"]

def heuristic_score(text):
    text = text.lower()
    if any(neg in text for neg in NEGATIVE_TRIGGERS):
        return -1 # Instantly drop tutorials/errors
    
    score = 0
    for trigger in HIGH_VALUE_TRIGGERS + SMP_TRIGGERS:
        if trigger in text:
            score += 3
    return score

# --- AI NEURAL PROCESSOR ---
async def analyze_with_gemini(title, body):
    if not ai_client: return {"category": "CLIENT", "score": 6, "est_value": "N/A", "pitch": "LEAD: AI Offline.", "failed": True}

    prompt = f"""
    Elite Growth Engine AI. Analyze this potential lead:
    Title: "{title}"
    Body: "{body}"

    Determine Category: "CLIENT" (Web/Server Dev) or "PLAYER" (SMP).
    Guidelines: {CUSTOM_OFFER_INSTRUCTIONS}
    
    Output STRICT JSON: {{"category": "CLIENT", "score": 9, "est_value": "$300", "pitch": "LEAD: <custom pitch>"}}
    """
    
    async with ai_semaphore:
        for attempt in range(1, 4): # 3 retry tiers
            try:
                await asyncio.sleep(1.5)
                resp = ai_client.models.generate_content(
                    model='gemini-3.5-flash-lite', contents=prompt,
                    config={"automatic_function_calling": {"disable": True}}
                )
                if resp.text:
                    cleaned = re.sub(r'```(?:json)?', '', resp.text).strip()
                    data = json.loads(cleaned)
                    data["failed"] = False
                    return data
            except Exception as e:
                await asyncio.sleep(2 ** attempt) # Exponential backoff
    return {"category": "CLIENT", "score": 5, "est_value": "N/A", "pitch": "LEAD: Check portfolio [https://yazoniplay.is-a.dev](https://yazoniplay.is-a.dev)", "failed": True}

async def dispatch_webhook(session, data):
    if not DISCORD_WEBHOOK_URL: return
    color = 0x9B59B6 if data['category'] == "CLIENT" else (0x2ECC71 if data['score'] >= 8 else 0xF1C40F)
    icon = "💼" if data['category'] == "CLIENT" else "🎮"
    
    payload = {
        "username": "Leviathan Lead Engine v9.0",
        "avatar_url": "[https://i.imgur.com/8Np8Z9Y.png](https://i.imgur.com/8Np8Z9Y.png)",
        "embeds": [{
            "title": f"{icon} [{data['category']}] • {data['platform']} ({data['origin']})",
            "description": f"**Title:** [{data['title'][:150]}]({data['permalink']})\n**Target:** `{data['author']}`",
            "url": data['permalink'],
            "color": color,
            "fields": [
                {"name": "🎯 Confidence", "value": f"**{data['score']}/10**", "inline": True},
                {"name": "💰 Est. Value", "value": f"**{data['est_value']}**", "inline": True},
                {"name": "🚀 Neural Pitch", "value": f"```{data['pitch']}```"},
            ],
            "footer": {"text": "v9.0 Leviathan Architecture • AES-256 Logged"}
        }]
    }
    try:
        await session.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        logging.error(f"{Colors.RED}Webhook failure: {e}{Colors.RESET}")

async def ai_worker(session):
    while True:
        post_id, platform, origin, title, body, permalink, author = await lead_queue.get()
        
        logging.info(f"{Colors.MAGENTA}🧠 Processing target: {title[:30]}...{Colors.RESET}")
        analysis = await analyze_with_gemini(title, body)
        
        if analysis.get("score", 0) >= 7 or analysis.get("failed"):
            full_data = {
                "platform": platform, "origin": origin, "title": title, 
                "permalink": permalink, "author": author, 
                "category": analysis.get("category", "CLIENT"),
                "score": analysis.get("score", 5), "est_value": analysis.get("est_value", "N/A"),
                "pitch": analysis.get("pitch", "")
            }
            if not full_data['pitch'].startswith("LEAD:"):
                full_data['pitch'] = f"LEAD: {full_data['pitch']}"
                
            save_lead_to_db(post_id, full_data)
            await dispatch_webhook(session, full_data)
            logging.info(f"{Colors.GREEN}✅ High-value lead secured! Dispatched to Discord.{Colors.RESET}")
            
        lead_queue.task_done()

# --- MULTI-THREADED SCRAPERS ---
async def fetch_reddit(session, sub):
    url = f"[https://www.reddit.com/r/](https://www.reddit.com/r/){sub}/new.json?limit=25"
    try:
        async with session.get(url, headers=get_headers(), timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                for post in data.get("data", {}).get("children", []):
                    p = post.get("data", {})
                    post_id, title, body = f"rd_{p.get('id')}", p.get("title", ""), p.get("selftext", "")
                    
                    if not is_seen(post_id) and heuristic_score(f"{title} {body}") > 0:
                        await lead_queue.put((post_id, "Reddit", f"r/{sub}", title, body, f"[https://reddit.com](https://reddit.com){p.get('permalink')}", f"u/{p.get('author')}"))
    except Exception: pass

async def fetch_github(session, query):
    url = f"[https://api.github.com/search/issues?q=](https://api.github.com/search/issues?q=){urllib.parse.quote(query)}+state:open&sort=created&order=desc"
    try:
        async with session.get(url, headers=get_headers(), timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                for issue in data.get("items", [])[:10]:
                    post_id, title, body = f"gh_{issue.get('id')}", issue.get("title", ""), issue.get("body", "") or ""
                    if not is_seen(post_id) and heuristic_score(f"{title} {body}") > 0:
                        await lead_queue.put((post_id, "GitHub", "Issues", title, body, issue.get("html_url"), f"@{issue.get('user', {}).get('login')}"))
    except Exception: pass

async def fetch_hackernews(session):
    try:
        async with session.get("[https://hacker-news.firebaseio.com/v0/newstories.json](https://hacker-news.firebaseio.com/v0/newstories.json)", timeout=10) as resp:
            if resp.status == 200:
                story_ids = (await resp.json())[:15]
                for sid in story_ids:
                    post_id = f"hn_{sid}"
                    if is_seen(post_id): continue
                    
                    async with session.get(f"[https://hacker-news.firebaseio.com/v0/item/](https://hacker-news.firebaseio.com/v0/item/){sid}.json") as item_resp:
                        if item_resp.status == 200:
                            item = await item_resp.json()
                            title, text = item.get("title", ""), item.get("text", "") or ""
                            if heuristic_score(f"{title} {text}") > 0:
                                await lead_queue.put((post_id, "HackerNews", "New", title, text, f"[https://news.ycombinator.com/item?id=](https://news.ycombinator.com/item?id=){sid}", f"@{item.get('by')}"))
    except Exception: pass

async def main():
    print(f"{Colors.RED}/// INITIATING LEVIATHAN ENGINE v9.0 ///{Colors.RESET}")
    logging.info("Booting connection pools, DB systems, and Neural workers...")
    
    # TCP Connector with pooling to prevent socket exhaustion during aggressive sweeps
    connector = aiohttp.TCPConnector(limit=50, keepalive_timeout=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        asyncio.create_task(ai_worker(session))
        
        while True:
            logging.info(f"{Colors.YELLOW}⚡ Executing Multi-Vector Network Sweep...{Colors.RESET}")
            
            tasks = []
            tasks.extend([fetch_reddit(session, sub) for sub in REDDIT_SUBS])
            tasks.extend([fetch_github(session, q) for q in GITHUB_QUERIES])
            tasks.append(fetch_hackernews(session))
            
            await asyncio.gather(*tasks)
            
            q_size = lead_queue.qsize()
            logging.info(f"🛡️ Sweep complete. {Colors.CYAN}{q_size} targets{Colors.RESET} passed pre-filtering. Sleeping 90s...")
            await asyncio.sleep(90)

if __name__ == "__main__":
    asyncio.run(main())
