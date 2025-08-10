import os
import requests
import re
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")

def fetch_articles():
    feed = feedparser.parse("https://www.sciencedaily.com/rss/all.xml")
    articles = []
    for entry in feed.entries[:1]:  # Ambil 1 artikel terbaru
        title = entry.title
        url = entry.link

        # Scrap halaman artikel penuh
        try:
            page = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(page.content, "html.parser")
            story_div = soup.find("div", id="story_text")

            if story_div:
                full_text = story_div.get_text(separator="\n", strip=True)
            else:
                full_text = BeautifulSoup(entry.summary, "html.parser").get_text()

        except Exception as e:
            print(f"Gagal mengambil artikel: {e}")
            full_text = BeautifulSoup(entry.summary, "html.parser").get_text()

        articles.append({
            "title": title,
            "url": url,
            "summary": full_text
        })
    return articles

def rewrite_article(article):
    prompt = f"""
Tulis ulang artikel ilmiah ini ke dalam 17 paragraf dengan gaya populer yang mudah dipahami pembaca awam seperti blog. Gunakan bahasa Indonesia sesuai Ejaan yang Disempurnakan (EYD). Gunakan kalimat pendek dan aktif (maksimal 20 kata per kalimat). Jangan lebih dari 80 kata per paragraf.

Judul artikel: {article['title']}

Isi artikel:
{article['summary']}

Instruksi penulisan:
1. Gunakan nada human-friendly dan tetap sesuai fakta ilmiah.
2. Tambahkan transisi antarparagraf agar alur tulisan mengalir.
3. Tambahkan analogi, perumpamaan, atau pertanyaan retoris jika relevan.
4. Tambahkan penjelasan untuk istilah ilmiah sulit.
5. Tidak menggunakan subjudul di tengah tulisan.
6. Tambahkan 1 paragraf resume singkat di akhir.
7. Tambahkan 1 kalimat meta-deskripsi pasif (maks. 150 karakter) untuk SEO.
8. Tambahkan 5 frasa kata kunci utama yang relevan.
9. Tambahkan 1 kalimat keterangan gambar yang lebih menarik dari judul.
10. Tambahkan 1 kalimat caption gambar dalam format khusus:
[[CAPTION]] Teks keterangan gambar di sini.
11. Gunakan struktur: Judul, paragraf isi, lalu elemen SEO di akhir.
12. Jangan menyebut nama situs atau sumber asli di teks.
13. Gunakan gaya bertutur, tidak kaku.
14. Buat seolah-olah ini ditulis oleh penulis blog.
15. Gunakan gaya penyampaian populer yang mendorong pembaca paham topik ilmiah.
16. Hindari kata-kata klise atau kalimat membosankan.

Langsung mulai dengan judul, bukan pengantar!
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

def generate_image(title, caption):
    prompt = f"Ilustrasi realistik modern tentang: {title}, gaya sinematik, HD, landscape, 1152x768"

    image_request = {
        "prompt": prompt,
        "modelId": "realistic-vision-v5.1",
        "width": 1152,
        "height": 768,
        "num_images": 1,
        "guidance_scale": 7,
        "promptMagic": True
    }

    response = requests.post(
        "https://cloud.leonardo.ai/api/rest/v1/generations",
        headers={
            "Authorization": f"Bearer {LEONARDO_API_KEY}",
            "Content-Type": "application/json"
        },
        json=image_request
    )

    data = response.json()
    generation_id = data["sdGenerationJob"]["generationId"]

    # Polling sampai gambar jadi
    image_url = None
    while not image_url:
        status = requests.get(
            f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}",
            headers={"Authorization": f"Bearer {LEONARDO_API_KEY}"}
        ).json()
        if status["generations_by_pk"]["status"] == "COMPLETE":
            image_url = status["generations_by_pk"]["generated_images"][0]["url"]

    # Download gambar
    img_data = requests.get(image_url).content
    img = Image.open(BytesIO(img_data)).convert("RGB")

    # Tambah overlay caption
    draw = ImageDraw.Draw(img)
    font_path = os.path.join("assets", "fonts", "DejaVuSans-Bold.ttf")
    font = ImageFont.truetype(font_path, 28)

    text = caption
    margin = 30
    text_position = (margin, img.height - 60)
    draw.text(text_position, text, font=font, fill="white")

    # Tambah logo jika ada
    logo_path = os.path.join("assets", "logo.png")
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((100, 100))
        img.paste(logo, (img.width - 120, img.height - 120), logo)

    # Simpan gambar
    filename = f"article-{datetime.now().strftime('%Y%m%d')}.jpg"
    img.save(os.path.join("static", "images", filename))
    return filename

def save_to_markdown(content, image_filename):
    today = datetime.now().strftime("%Y-%m-%d")
    title_match = re.search(r"^(.+)", content)
    title = title_match.group(1).strip() if title_match else "Artikel Sains"
    filename = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()) + ".md"

    image_path = f"/images/{image_filename}"
    front_matter = f"""---
title: "{title}"
date: {today}
categories: ["Ilmiah Populer"]
image: "{image_path}"
---
"""

    with open(os.path.join("content", "posts", filename), "w", encoding="utf-8") as f:
        f.write(front_matter + "\n" + content)

def main():
    articles = fetch_articles()
    for article in articles:
        rewritten = rewrite_article(article)

        # Ekstrak caption dari tanda [[CAPTION]]
        caption_match = re.search(r"\[\[CAPTION\]\]\s*(.+)", rewritten)
        caption = caption_match.group(1).strip() if caption_match else article['title']

        image_filename = generate_image(article["title"], caption)
        save_to_markdown(rewritten, image_filename)
        print(f"Artikel '{article['title']}' berhasil disimpan.")

if __name__ == "__main__":
    main()
