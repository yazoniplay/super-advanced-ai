import os
import requests
import time
from google import genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

ai_client = genai.Client(api_key=GEMINI_API_KEY)
seen_ids = set()

def send_discord_alert(lead_category, sub_name, title, url, pitch):
    # Color-coded: Gold for Web Dev, Emerald Green for Minecraft
    embed_color = 15844367 if lead_category == "WEB_DEV" else 3066993
    
    payload = {
        "embeds": [{
            "title": f"🚨 [{lead_category}] Lead in r/{sub_name}: {title}",
            "url": url,
            "color": embed_color,
            "fields": [
                {"name": "🎯 Recommended Cold DM", "value": pitch}
            ],
            "footer": {"text": "Lead Hunter Engine v4.0 • Dual Sector Active"}
        }]
    }
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        print(f"--> [SUCCESS] Sent {lead_category} lead to Discord (Status: {res.status_code})")
    except Exception as e:
        print(f"Error sending Discord webhook: {e}")

def generate_pitch_with_retry(prompt, retries=3, delay=2):
    for attempt in range(retries):
        try:
            response = ai_client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < retries - 1:
                print(f"⚠️ Gemini busy (503). Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise e

def hunt_leads():
    print("🚀 Hunting dual-sector high-intent leads...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadHunter/4.0"}
    
    negative_keywords = [
        "best ai", "top 10", "tutorial", "review", "[for hire]", "showcase", 
        "looking to join", "looking for an smp to play", "looking for server to join"
    ]

    # --- SECTOR 1: WEBSITES & SOFTWARE ---
    web_subs = ["forhire", "freelance_forhire", "smallbusiness", "Entrepreneur", "webdesign"]
    web_keywords = ["website", "web designer", "developer", "redesign", "wordpress", "shopify", "need a site"]

    for sub in web_subs:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit=10"
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                posts = res.json().get("data", {}).get("children", [])
                for post in posts:
                    data = post.get("data", {})
                    post_id = data.get("id")
                    title = data.get("title", "")
                    title_lower = title.lower()

                    if any(kw in title_lower for kw in web_keywords):
                        if any(neg in title_lower for neg in negative_keywords):
                            continue

                        if post_id and post_id not in seen_ids:
                            seen_ids.add(post_id)
                            permalink = f"https://reddit.com{data.get('permalink')}"
                            
                            prompt = (
                                f"Act as an expert freelance web developer. Write a direct, highly persuasive "
                                f"2-sentence cold DM offering web design to this client post: '{title}'."
                            )
                            pitch = generate_pitch_with_retry(prompt)
                            send_discord_alert("WEB_DEV", sub, title, permalink, pitch)
        except Exception as e:
            print(f"Error in web search r/{sub}: {e}")

    # --- SECTOR 2: MINECRAFT SERVERS, CONFIGS & PLUGIN JOBS ---
    mc_subs = ["mcstaff", "admincraft", "MinecraftServer", "forhire", "slavelabour"]
    mc_keywords = [
        "hiring", "need a dev", "plugin", "skript", "server setup", "luckperms", 
        "deluxemenus", "looking for developer", "looking for configurator", "need a server"
    ]

    for sub in mc_subs:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit=10"
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                posts = res.json().get("data", {}).get("children", [])
                for post in posts:
                    data = post.get("data", {})
                    post_id = data.get("id")
                    title = data.get("title", "")
                    title_lower = title.lower()

                    if any(kw in title_lower for kw in mc_keywords):
                        if any(neg in title_lower for neg in negative_keywords):
                            continue

                        if post_id and post_id not in seen_ids:
                            seen_ids.add(post_id)
                            permalink = f"https://reddit.com{data.get('permalink')}"
                            
                            prompt = (
                                f"Act as an expert Minecraft server developer experienced in Paper, Velocity, Skript, "
                                f"LuckPerms, and custom plugins. Write a sharp, professional 2-sentence cold DM "
                                f"offering server configuration and development for this request: '{title}'."
                            )
                            pitch = generate_pitch_with_retry(prompt)
                            send_discord_alert("MINECRAFT", sub, title, permalink, pitch)
        except Exception as e:
            print(f"Error in Minecraft search r/{sub}: {e}")

if __name__ == "__main__":
    hunt_leads()
