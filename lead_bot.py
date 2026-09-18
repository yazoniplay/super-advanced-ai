import os
import requests
import xml.etree.ElementTree as ET
from google import genai

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

ai_client = genai.Client(api_key=GEMINI_API_KEY)
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

def check_reddit():
    print("🔍 Searching Reddit...")
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
                        
                        if post_id and post_id not in seen_ids:
                            seen_ids.add(post_id)
                            title = data.get("title")
                            permalink = f"https://reddit.com{data.get('permalink')}"
                            
                            prompt = f"Draft a short, compelling 2-sentence pitch offering custom web design to this Reddit post: '{title}'"
                            response = ai_client.models.generate_content(
                                model='gemini-3.6-flash',
                                contents=prompt
                            )
                            send_discord_alert("Reddit", title, permalink, response.text)
            except Exception as e:
                print(f"Reddit error on r/{sub}: {e}")

def check_google_news():
    print("🔍 Searching Google News RSS...")
    queries = ["looking+for+web+designer", "small+business+needs+website"]
    
    for query in queries:
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        try:
            res = requests.get(url)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for item in root.findall('./channel/item')[:2]:
                    title = item.find('title').text
                    link = item.find('link').text
                    
                    if link not in seen_ids:
                        seen_ids.add(link)
                        prompt = f"Draft a 2-sentence cold pitch offering web development services based on this title: '{title}'"
                        response = ai_client.models.generate_content(
                            model='gemini-3.6-flash',
                            contents=prompt
                        )
                        send_discord_alert("Google News", title, link, response.text)
        except Exception as e:
            print(f"Google News error: {e}")

def check_hacker_news():
    print("🔍 Searching Hacker News Freelance threads...")
    try:
        url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        res = requests.get(url)
        if res.status_code == 200:
            story_ids = res.json()[:15]
            for s_id in story_ids:
                item_res = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{s_id}.json")
                if item_res.status_code == 200:
                    data = item_res.json()
                    title = data.get("title", "")
                    
                    if "Ask HN:" in title or "Seeking" in title:
                        if s_id not in seen_ids:
                            seen_ids.add(s_id)
                            hn_url = f"https://news.ycombinator.com/item?id={s_id}"
                            prompt = f"Write a professional 2-sentence pitch offering web engineering for this HN thread: '{title}'"
                            response = ai_client.models.generate_content(
                                model='gemini-3.6-flash',
                                contents=prompt
                            )
                            send_discord_alert("HackerNews", title, hn_url, response.text)
    except Exception as e:
        print(f"HN error: {e}")

if __name__ == "__main__":
    print("🚀 Running Lead Hunter Engine...")
    check_reddit()
    check_google_news()
    check_hacker_news()
