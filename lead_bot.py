import os
import requests
from apify_client import ApifyClient
from google import genai

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

ai_client = genai.Client(api_key=GEMINI_API_KEY)
apify_client = ApifyClient(APIFY_TOKEN)

seen_ids = set()

def send_discord_alert(platform, title, url, pitch):
    payload = {
        "embeds": [{
            "title": f"🚨 NEW LEAD [{platform}]: {title}",
            "url": url,
            "color": 5814783,
            "fields": [{"name": "AI Pitch", "value": pitch}]
        }]
    }
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        print(f"--> Sent {platform} lead to Discord (Status: {res.status_code})")
    except Exception as e:
        print(f"Error sending Discord webhook: {e}")

def check_reddit_public():
    print("🔍 Searching Reddit feeds...")
    subreddits = ["smallbusiness", "Entrepreneur", "webdesign", "freelance", "Startups"]
    keywords = ["need a website", "looking for web designer", "website redesign"]
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadHunter/1.0"}
    
    for sub in subreddits:
        for query in keywords:
            url = f"https://www.reddit.com/r/{sub}/search.json?q={query}&sort=new&limit=2"
            try:
                res = requests.get(url, headers=headers)
                if res.status_code == 200:
                    posts = res.json().get("data", {}).get("children", [])
                    for post in posts:
                        data = post.get("data", {})
                        post_id = data.get("id")
                        
                        if post_id not in seen_ids:
                            seen_ids.add(post_id)
                            title = data.get("title")
                            permalink = f"https://reddit.com{data.get('permalink')}"
                            
                            prompt = f"Draft a short, compelling 2-sentence pitch offering custom web design to this Reddit post: '{title}'"
                            response = ai_client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=prompt
                            )
                            send_discord_alert("Reddit", title, permalink, response.text)
            except Exception as e:
                print(f"Reddit error on r/{sub}: {e}")

def check_tiktok_apify():
    print("🔍 Fetching TikTok business leads via Apify...")
    try:
        # Reliable clockworks/free-tiktok-scraper parameters
        run_input = {
            "searchSection": "users",
            "searchKeywords": "small business web design",
            "maxItems": 3
        }
        run = apify_client.actor("clockworks/free-tiktok-scraper").call(run_input=run_input)
        
        for item in apify_client.dataset(run["defaultDatasetId"]).iterate_items():
            author_info = item.get("author", {})
            unique_id = author_info.get("uniqueId") or item.get("uniqueId")
            
            if unique_id and unique_id not in seen_ids:
                seen_ids.add(unique_id)
                profile_url = f"https://www.tiktok.com/@{unique_id}"
                
                prompt = f"Write a punchy 2-sentence DM pitch to TikTok user @{unique_id} offering a modern website build."
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                send_discord_alert("TikTok", f"@{unique_id}", profile_url, response.text)
    except Exception as e:
        print(f"Apify TikTok Error: {e}")

if __name__ == "__main__":
    print("🚀 Running Lead Hunter Engine...")
    check_reddit_public()
    check_tiktok_apify()
