import feedparser
import requests
from bs4 import BeautifulSoup
from googletrans import Translator
import datetime
import os

rss_url = "https://www.sciencedaily.com/rss/all.xml"
feed = feedparser.parse(rss_url)
translator = Translator()

def get_full_article(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, 'html.parser')
    content = soup.find('div', id='text')
    if not content:
        return ""
    return "\n\n".join(p.get_text() for p in content.find_all('p'))

folder = "artikel"
os.makedirs(folder, exist_ok=True)

for entry in feed.entries[:5]:
    title = entry.title.strip()
    link = entry.link
    published = entry.published
    slug = title.lower().replace(" ", "-").replace("/", "-")

    full_text_en = get_full_article(link)
    if not full_text_en:
        continue
    translated = translator.translate(full_text_en, src='en', dest='id').text

    filename = f"{folder}/{slug}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"*Dipublikasikan: {published}*\n\n")
        f.write(translated)

    print(f"[✓] Artikel disimpan: {filename}")
