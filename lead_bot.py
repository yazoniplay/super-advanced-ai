import os
import requests
import time
from google import genai

# Load secrets from GitHub Actions environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Initialize Gemini Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)
seen_ids = set()

def send_discord_alert(sub_name, title, url, pitch):
    """Fires structured lead cards straight to your Discord channel"""
    payload = {
        "embeds": [{
            "title": f"💰 HIGH-INTENT LEAD [r/{sub_name}]: {title}",
            "url": url,
            "color": 3066993, # Emerald Green for money/leads
            "fields": [
                {"name": "🎯 Recommended Cold DM Pitch", "value": pitch}
            ],
            "footer": {"text": "Lead Hunter Engine • High Intent Filter Active"}
        }]
    }
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        print(f"--> [SUCCESS] Sent lead from r/{sub_name} to Discord (Status: {res.status_code})")
    except Exception as e:
        print(f"Error sending Discord webhook: {e}")

def generate_pitch_with_retry(prompt, retries=3, delay=2):
    """Generates custom cold pitches with auto-retry if Gemini hits traffic spikes"""
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

def hunt_clients():
    print("🚀 Hunting for active client requests...")
    
    # Subreddits dedicated to hiring or business owners seeking help
    target_subs = ["forhire", "freelance_forhire", "smallbusiness", "Entrepreneur", "webdesign"]
    
    # Precise query strings for client hiring intent
    intent_queries = [
        '"[Hiring]"', 
        '"looking for web designer"', 
        '"need a website"', 
        '"need a developer"', 
        '"redesign my website"'
    ]
    
    # Filters out blog posts, self-promotion, and tutorials
    negative_keywords = ["best ai", "top 10", "how to", "tutorial", "review", "[for hire]", "showcase"]
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadHunter/2.0"}

    for sub in target_subs:
        for query in intent_queries:
            url = f"https://www.reddit.com/r/{sub}/search.json?q={query}&sort=new&restrict_sr=on&limit=4"
            try:
                res = requests.get(url, headers=headers)
                if res.status_code == 200:
                    posts = res.json().get("data", {}).get("children", [])
                    for post in posts:
                        data = post.get("data", {})
                        post_id = data.get("id")
                        title = data.get("title", "")
                        title_lower = title.lower()

                        # Skip self-promotions or general articles
                        if any(neg in title_lower for neg in negative_keywords):
                            continue

                        if post_id and post_id not in seen_ids:
                            seen_ids.add(post_id)
                            permalink = f"https://reddit.com{data.get('permalink')}"
                            
                            prompt = (
                                f"Act as an expert freelance web developer. Write a highly persuasive, "
                                f"2-sentence cold message/DM to a prospective client who made this post: '{title}'. "
                                f"Focus on solving their problem, adding value, and inviting a call or portfolio check."
                            )
                            
                            pitch = generate_pitch_with_retry(prompt)
                            send_discord_alert(sub, title, permalink, pitch)
            except Exception as e:
                print(f"Error fetching r/{sub}: {e}")

if __name__ == "__main__":
    hunt_clients()
