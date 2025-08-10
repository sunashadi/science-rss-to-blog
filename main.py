import os
import requests
import re
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WP_USER = os.getenv("WP_USER")  # Username WordPress
WP_APP_PASS = os.getenv("WP_APP_PASS")  # Application Password WordPress
WP_URL = "https://www.sunashadi.com/wp-json/wp/v2/posts"

# Ambil artikel dari RSS + scrap teks penuh
def fetch_articles():
    feed = feedparser.parse("https://www.sciencedaily.com/rss/all.xml")
    articles = []
    for entry in feed.entries[:1]:  # Ambil 1 artikel terbaru
        title = entry.title
        url = entry.link
        print(f"🔗 Mengambil artikel: {title}")
        
        # Scrap halaman penuh
        html = requests.get(url).text
        soup = BeautifulSoup(html, "html.parser")
        story_div = soup.find("div", id="story_text")
        if story_div:
            full_text = " ".join(p.get_text() for p in story_div.find_all("p"))
        else:
            full_text = entry.summary  # fallback
        
        articles.append({"title": title, "url": url, "full_text": full_text})
    return articles

# Rewrite artikel ke bahasa populer
def rewrite_article(article):
    prompt = f"""
Tulis ulang artikel ilmiah ini ke dalam 17 paragraf dengan gaya populer yang mudah dipahami pembaca awam seperti blog.
Gunakan bahasa Indonesia sesuai Ejaan yang Disempurnakan (EYD). Gunakan kalimat pendek dan aktif (maksimal 20 kata per kalimat).
Jangan lebih dari 80 kata per paragraf.

Judul artikel: {article['title']}

Isi artikel:
{article['full_text']}

Instruksi penulisan:
1. Gunakan nada human-friendly dan tetap sesuai fakta ilmiah.
2. Tambahkan transisi antarparagraf agar alur tulisan mengalir.
3. Tambahkan analogi atau perumpamaan bila relevan.
4. Jelaskan istilah ilmiah sulit.
5. Tidak pakai subjudul di tengah tulisan.
6. Tambahkan 1 paragraf ringkasan di akhir.
7. Tambahkan 1 kalimat meta-deskripsi maksimal 150 karakter untuk SEO.
8. Tambahkan 5 frasa kata kunci utama.
9. Tambahkan 1 kalimat keterangan gambar yang menarik.
10. Tambahkan 1 kalimat caption gambar dalam format:
[[CAPTION]] teks keterangan gambar.
11. Jangan sebut nama situs atau sumber asli.
12. Buat seolah ditulis penulis blog.
13. Hindari kata klise dan kalimat membosankan.

Langsung mulai dengan judul!
"""
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
    )
    rewritten = response.json()["choices"][0]["message"]["content"]
    return rewritten

# Posting ke WordPress sebagai draft
def post_to_wordpress(title, content):
    data = {
        'title': title,
        'content': content,
        'status': 'draft'  # Bisa diganti 'publish' kalau mau langsung terbit
    }
    response = requests.post(WP_URL, json=data, auth=HTTPBasicAuth(WP_USER, WP_APP_PASS))
    if response.status_code == 201:
        print(f"✅ Draft '{title}' berhasil dibuat di WordPress")
    else:
        print(f"❌ Gagal posting: {response.status_code} - {response.text}")

def main():
    articles = fetch_articles()
    for article in articles:
        rewritten = rewrite_article(article)

        # Ambil judul dari hasil rewrite
        title_match = re.search(r"^(.+)", rewritten)
        new_title = title_match.group(1).strip() if title_match else article['title']

        # Posting ke WordPress
        post_to_wordpress(new_title, rewritten)

if __name__ == "__main__":
    main()
