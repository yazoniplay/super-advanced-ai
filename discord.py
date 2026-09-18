import os
import asyncio
import aiohttp
import json
import logging
import re
import random
import sqlite3
import urllib.parse
from datetime import datetime
import discord
from discord.ext import commands, tasks
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
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

CUSTOM_OFFER_INSTRUCTIONS = """
- PRIMARY FOCUS: Sell custom web dev, dynamic portfolios, landing pages, and complex Minecraft server setups. Emphasize fast deployment. Portfolio: https://yazoniplay.is-a.dev
- SECONDARY FOCUS: Recruit for 'Skyfall SMP'.
- MANDATORY PREFIX: 'LEAD: '
"""

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- ENTERPRISE ARCHITECTURE & STATE ---
ai_semaphore = asyncio.Semaphore(3)
lead_queue = asyncio.Queue()
DB_PATH = "hunter_engine.db"

# Engine State
engine_state = {
    "paused": False,
    "cycles_run": 0,
    "leads_processed": 0,
    "high_value_triggers": ["hiring", "budget is", "paid gig", "looking to hire", "pay you to", "freelance project", "need a dev"]
}

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

def get_total_leads():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM leads")
    count = c.fetchone()[0]
    conn.close()
    return count

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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15"
]

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json"}

REDDIT_SUBS = ["forhire", "freelance_forhire", "webdev", "slavelabour", "startups", "smallbusiness", "Entrepreneur"]
LEMMY_COMMUNITIES = ["freelance@lemmy.world", "webdev@lemmy.world"]
GITHUB_QUERIES = ["label:hiring", "need a developer"]

SMP_TRIGGERS = ["looking for smp", "smp to join", "need an smp", "lifesteal smp", "crystal pvp"]
NEGATIVE_TRIGGERS = ["how to", "tutorial", "guide", "help with", "error", "bug fix", "my code", "open source"]

def heuristic_score(text):
    text = text.lower()
    if any(neg in text for neg in NEGATIVE_TRIGGERS):
        return -1 
    
    score = 0
    for trigger in engine_state["high_value_triggers"] + SMP_TRIGGERS:
        if trigger in text:
            score += 3
    return score

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
        for attempt in range(1, 4):
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
            except Exception:
                await asyncio.sleep(2 ** attempt)
    return {"category": "CLIENT", "score": 5, "est_value": "N/A", "pitch": "LEAD: Check portfolio [https://yazoniplay.is-a.dev](https://yazoniplay.is-a.dev)", "failed": True}

async def dispatch_webhook(session, data):
    if not DISCORD_WEBHOOK_URL: return
    color = 0x9B59B6 if data['category'] == "CLIENT" else 0x2ECC71
    icon = "💼" if data['category'] == "CLIENT" else "🎮"
    
    payload = {
        "username": "Leviathan Command v10.0",
        "embeds": [{
            "title": f"{icon} [{data['category']}] • {data['platform']}",
            "description": f"**Title:** [{data['title'][:150]}]({data['permalink']})\n**Target:** `{data['author']}`",
            "url": data['permalink'],
            "color": color,
            "fields": [
                {"name": "🎯 Confidence", "value": f"**{data['score']}/10**", "inline": True},
                {"name": "💰 Est. Value", "value": f"**{data['est_value']}**", "inline": True},
                {"name": "🚀 Neural Pitch", "value": f"```{data['pitch']}```"},
            ]
        }]
    }
    try: await session.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception: pass

# --- DISCORD BOT C2 INTERFACE ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"{Colors.GREEN}📡 C2 Link Established. Logged in as {bot.user}{Colors.RESET}")
    bot.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=50, keepalive_timeout=30))
    bot.loop.create_task(ai_worker(bot.session))
    engine_loop.start()

@bot.command()
async def status(ctx):
    """Check the health and stats of the Leviathan engine."""
    q_size = lead_queue.qsize()
    total_db = get_total_leads()
    status_text = "⏸️ PAUSED" if engine_state["paused"] else "✅ RUNNING"
    
    embed = discord.Embed(title="⚙️ Leviathan Engine Status", color=0x3498DB)
    embed.add_field(name="Engine State", value=status_text, inline=True)
    embed.add_field(name="Queue Backlog", value=f"{q_size} leads", inline=True)
    embed.add_field(name="Total Captured", value=f"{total_db} leads", inline=True)
    embed.add_field(name="Cycles Run", value=str(engine_state["cycles_run"]), inline=True)
    embed.add_field(name="AI Processed", value=str(engine_state["leads_processed"]), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def pause(ctx):
    """Pause the scraping cycles (AI will finish the current queue)."""
    engine_state["paused"] = True
    await ctx.send("⏸️ Engine paused. Scrapers standing by.")

@bot.command()
async def resume(ctx):
    """Resume the scraping cycles."""
    engine_state["paused"] = False
    await ctx.send("▶️ Engine resumed. Scrapers initializing.")

@bot.command()
async def addword(ctx, *, word: str):
    """Add a new high-value trigger word dynamically."""
    engine_state["high_value_triggers"].append(word.lower())
    await ctx.send(f"✅ Added `{word}` to high-value targeting arrays.")

# --- BACKGROUND WORKERS ---
async def ai_worker(session):
    while True:
        post_id, platform, origin, title, body, permalink, author = await lead_queue.get()
        engine_state["leads_processed"] += 1
        
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
            
        lead_queue.task_done()

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

@tasks.loop(seconds=90)
async def engine_loop():
    if engine_state["paused"]:
        return
        
    engine_state["cycles_run"] += 1
    logging.info(f"{Colors.YELLOW}⚡ Executing Multi-Vector Network Sweep (Cycle {engine_state['cycles_run']})...{Colors.RESET}")
    
    tasks = []
    tasks.extend([fetch_reddit(bot.session, sub) for sub in REDDIT_SUBS])
    await asyncio.gather(*tasks)
    
    logging.info(f"🛡️ Sweep complete. {Colors.CYAN}{lead_queue.qsize()} targets{Colors.RESET} passed pre-filtering.")

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print(f"{Colors.RED}FATAL: DISCORD_BOT_TOKEN not found in environment.{Colors.RESET}")
    else:
        print(f"{Colors.RED}/// INITIATING LEVIATHAN C2 ENGINE v10.0 ///{Colors.RESET}")
        bot.run(DISCORD_BOT_TOKEN)
