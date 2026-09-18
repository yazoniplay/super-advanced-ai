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
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    print(f"--> Sent {platform} lead to Discord (Status Code: {res.status_code})")

def check_reddit_public():
    print("🔍 Fetching Reddit posts...")
    subreddits = ["smallbusiness", "Entrepreneur", "webdesign"]
    
    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/search.json?q=need+a+website&sort=new&limit=3"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadHunter/1.0"}
        
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
                        
                        prompt = f"Draft a short, 2-sentence cold pitch offering custom web development for this post: '{title}'"
                        response = ai_client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt
                        )
                        send_discord_alert("Reddit", title, permalink, response.text)
        except Exception as e:
            print(f"Error fetching Reddit r/{sub}: {e}")

def check_instagram_apify():
    print("🔍 Fetching Instagram profiles via Apify...")
    try:
        # Corrected input parameters for apidojo/instagram-user-scraper
        run_input = {
            "search": ["local business"],
            "searchType": "user",
            "resultsLimit": 3
        }
        run = apify_client.actor("apidojo/instagram-user-scraper").call(run_input=run_input)
        
        for item in apify_client.dataset(run["defaultDatasetId"]).iterate_items():
            username = item.get("username")
            website = item.get("externalUrl")
            
            if username and not website and username not in seen_ids:
                seen_ids.add(username)
                profile_url = f"https://instagram.com/{username}"
                
                prompt = f"Write a 2-sentence direct message pitch to Instagram user @{username} offering a web design upgrade."
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                send_discord_alert("Instagram", f"@{username}", profile_url, response.text)
    except Exception as e:
        print(f"Apify IG Error: {e}")

if __name__ == "__main__":
    print("🚀 Running Lead Hunter Engine...")
    check_reddit_public()
    check_instagram_apify()
