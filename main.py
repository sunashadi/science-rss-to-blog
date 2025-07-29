import feedparser
import requests
import openai
import os
from bs4 import BeautifulSoup
from datetime import datetime
import re

# Ambil API key dari Secrets GitHub
openai.api_key = os.getenv("OPENAI_API_KEY")

# Ambil isi lengkap dari artikel ScienceDaily
def fetch_article(link):
    try:
        res = requests.get(link)
        soup = BeautifulSoup(res.text, "html.parser")
        content_div = soup.find("div", {"id": "text"})
        if not content_div:
            print("Konten utama tidak ditemukan")
            return ""
        paragraphs = content_div.find_all("p")
        full_text = "\n\n".join(p.get_text().strip() for p in paragraphs)
        return full_text
    except Exception as e:
        print(f"Gagal ambil isi artikel: {e}")
        return ""

# Terjemahkan dan rewrite dengan gaya yang mudah dibaca
def translate_and_rewrite(text):
    prompt = f"""
    Terjemahkan dan tulis ulang artikel berikut ke dalam Bahasa Indonesia. 
    Gunakan bahasa yang mudah dipahami dan cocok untuk pembaca blog.

    Artikel:
    {text}
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7,
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Gagal translate/rewrite: {e}")
        return ""

# Simpan artikel sebagai file Markdown
def save_as_markdown(title, summary, content):
    date = datetime.now().isoformat()
    filename = re.sub(r'[^\w\-]', '-', title.lower())[:50] + ".md"
    path = f"content/posts/{filename}"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"---\n")
            f.write(f"title: \"{title}\"\n")
            f.write(f"date: {date}\n")
            f.write(f"draft: false\n")
            f.write(f"summary: \"{summary.strip()}\"\n")
            f.write(f"---\n\n")
            f.write(content.strip())
        print(f"✅ Artikel disimpan: {path}")
    except Exception as e:
        print(f"Gagal simpan markdown: {e}")

# Fungsi utama
def main():
    print("📥 Memproses RSS ScienceDaily...")
    feed = feedparser.parse("https://www.sciencedaily.com/rss/top/environment.xml")

    if not feed.entries:
        print("❌ Tidak ada entri dalam feed.")
        return

    # Ambil hanya 1 artikel terbaru
    article = feed.entries[0]
    title = article.title
    summary = article.summary
    link = article.link

    print(f"📰 Artikel: {title}")
    print(f"🔗 Link: {link}")

    full_text = fetch_article(link)
    if not full_text:
        print("❌ Gagal ambil isi lengkap artikel.")
        return

    translated = translate_and_rewrite(full_text)
    if not translated:
        print("❌ Gagal terjemahkan/rewrite artikel.")
        return

    save_as_markdown(title, summary, translated)

if __name__ == "__main__":
    main()
