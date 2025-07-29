import os
import feedparser
import requests
import openai
from bs4 import BeautifulSoup
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import re

# === Konfigurasi ===
RSS_FEED_URL = "https://www.sciencedaily.com/rss/all.xml"
IMG_DIR = "static/images"
POST_DIR = "content/posts"
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# === Persiapan direktori ===
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(POST_DIR, exist_ok=True)

# === Fungsi untuk membersihkan slug judul ===
def slugify(text):
    return re.sub(r'[^a-zA-Z0-9-]', '-', text.lower()).strip('-')

# === Fungsi untuk rewrite artikel ===
def rewrite_article(original_text):
    prompt = f"""
    Tulis ulang artikel berikut ini dengan ketentuan:
    
    1. Artikel minimal 17 paragraf dalam bahasa Indonesia dengan gaya bahasa yang mudah dipahami oleh orang awam, cocok untuk pembaca blog (humanize) sesuai SEO!
    2. Sesuaikan penulisan hurufnya sesuai Ejaan Yang Disempurnakan (EYD)!
    3. Artikel menggunakan kalimat aktif dan pendek (maksimal 20 kata per kalimat).
    4. Artikel paragraf tidak lebih dari 4 kalimat.
    5. Artikel mengandung kata transisi seperti “selain itu”, “karena itu”, “di sisi lain”, “namun”, dan sejenisnya di seluruh artikel.
    6. Artikel menghindari kalimat pasif secara berlebihan.
    7. Artikel menjelaskan setiap istilah atau konsep sulit dengan cara sederhana.
    8. Artikel mengandung struktur logis: pembuka, isi utama, dan penutup.
    9. Tuliskan sumber jurnal dan tanggal publikasi dalam bentuk paragraf sesuai SEO! 
    10. Artikel memiliki tulisan dengan gaya human-friendly, tidak kaku, seolah berbicara langsung kepada pembaca. 
    11. Buatkan dalam bentuk paragraf! Buatkan judul yang menarik sesuai SEO! 
    12. Buatkan 3 sub judul yang menarik dan relevan di dalam badan artikel yang dibuat sesuai SEO!
    13. Buatkan Resume dan meta-deskripsi dalam kalimat pasif sesuai SEO! 
    14. Tuliskan kalimat pendek yang lebih menarik daripada judul untuk keterangan gambar!  
    15. Buatkan 5 frasa kata kunci utama yang unggul sesuai SEO!

    Artikel:
    {original_text}
    """
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content.strip()

# === Fungsi buat gambar ilustrasi otomatis dari Leonardo + Logo + Caption ===
def generate_image(prompt, slug, caption):
    try:
        # Request ke Leonardo
        res = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers={
                "Authorization": f"Bearer {LEONARDO_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "prompt": prompt + ", modern, realistic, landscape",
                "width": 1152,
                "height": 768,
                "num_images": 1,
                "modelId": "realistic-vision-v5.1"
            }
        )
        res.raise_for_status()
        image_url = res.json()["generations_by_pk"]["generated_images"][0]["url"]

        # Download dan buka gambar
        image_data = requests.get(image_url).content
        image = Image.open(BytesIO(image_data)).convert("RGBA")

        # Tambahkan logo
        logo = Image.open(requests.get("https://i.imgur.com/SppIZHH.png", stream=True).raw).convert("RGBA")
        logo = logo.resize((175, 158))
        image.paste(logo, (image.width - logo.width - 20, image.height - logo.height - 20), logo)

        # Tambahkan teks caption
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        draw.text((30, image.height - 60), caption, font=font, fill="white")

        # Simpan
        image_path = f"{IMG_DIR}/{slug}.png"
        image.save(image_path, "PNG")
        return f"/images/{slug}.png"
    except Exception as e:
        print(f"Gagal buat gambar: {e}")
        return ""

# === Ambil feed RSS ===
feed = feedparser.parse(RSS_FEED_URL)

for entry in feed.entries[:3]:  # Ambil 3 artikel pertama
    title = entry.title
    slug = slugify(title)
    link = entry.link
    published = entry.published if 'published' in entry else datetime.utcnow().isoformat()
    date = datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m-%d')

    # Ambil konten
    html = requests.get(link).text
    soup = BeautifulSoup(html, "html.parser")
    paragraphs = soup.find_all("p")
    content = "\n".join([p.get_text() for p in paragraphs])

    if len(content) < 500:
        continue

    rewritten = rewrite_article(content)

    # Ekstrak caption dari hasil rewrite
    caption_match = re.search(r"keterangan gambar yang dibuat oleh Fungsi rewrite.*?\: (.+?)\n", rewritten, re.IGNORECASE)
    caption = caption_match.group(1) if caption_match else title

    image_url = generate_image(title, slug, caption)

    # Simpan file Markdown
    post_path = f"{POST_DIR}/{slug}.md"
    with open(post_path, "w") as f:
        f.write(f"---\ntitle: \"{title}\"\ndate: {date}\ndraft: false\nsummary: \"{entry.summary}\"\nimage: {image_url}\n---\n\n")
        f.write(rewritten)

    print(f"Berhasil buat artikel: {title}")
