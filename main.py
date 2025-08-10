# main.py
import os
import re
import time
import base64
import feedparser
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

# === Load env ===
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")
WP_URL = os.getenv("WP_URL")              # e.g. https://www.sunashadi.com
WP_USER = os.getenv("WP_USER")            # WP username (admin)
WP_APP_PASS = os.getenv("WP_APP_PASS")    # Application password
POSTS_ENDPOINT = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
MEDIA_ENDPOINT = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media"

# === Folders ===
IMG_DIR = "static/images"
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs("assets/fonts", exist_ok=True)  # ensure folder exists for font if you add

# === Helpers ===

def fetch_articles_from_rss(rss_url="https://www.sciencedaily.com/rss/all.xml", limit=1):
    feed = feedparser.parse(rss_url)
    articles = []
    for entry in feed.entries[:limit]:
        title = entry.title
        url = entry.link
        summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()
        articles.append({"title": title, "url": url, "summary": summary})
    return articles

def fetch_full_article_text(url, user_agent="Mozilla/5.0"):
    """Scrape article full text from ScienceDaily page. Returns text or None."""
    try:
        r = requests.get(url, headers={"User-Agent": user_agent}, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # ScienceDaily: try common containers
        body_div = soup.find("div", id="story_text") or soup.find("div", id="text") or soup.find("div", class_="article-body")
        if not body_div:
            return None
        paras = [p.get_text(strip=True) for p in body_div.find_all("p") if p.get_text(strip=True)]
        return "\n\n".join(paras).strip() if paras else None
    except Exception as e:
        print(f"[fetch_full_article_text] error: {e}")
        return None

# --- OpenAI rewrite/translate using gpt-3.5-turbo ---
def rewrite_article_with_openai(title, text):
    prompt = f"""
Kamu adalah penulis artikel blog profesional.

Tulis ulang (terjemahkan jika perlu) teks berikut menjadi sebuah artikel BERBAHASA INDONESIA:
- Minimal 17 paragraf.
- Gaya: mudah dipahami oleh orang awam, human-friendly, SEO friendly.
- EYD (Ejaan Yang Disempurnakan).
- Kalimat aktif, maksimal 20 kata / kalimat.
- Paragraf maksimal 4 kalimat.
- Sertakan kata transisi (selain itu, karena itu, di sisi lain, namun, dsb.).
- Hindari pasif berlebihan. Jelaskan istilah sulit secara sederhana.
- Struktur logis: pembuka, isi, penutup.
- Di akhir tambahkan paragraf “Sumber” yang menyebutkan link jurnal/tautan dan tanggal publikasi jika ada.
- Di bagian paling akhir tuliskan:
  - Resume (kalimat pasif) -- berikan label: [[RESUME]]
  - Meta-deskripsi (kalimat pasif, max 150 chars) -- berikan label: [[META]]
  - 5 frasa kata kunci utama (comma separated) -- label: [[KEYPHRASES]]
  - Satu kalimat keterangan gambar yang lebih menarik dari judul, lalu tampilkan sebagai: [[CAPTION]] kalimat
Teks sumber:
Judul: {title}

Teks lengkap:
{text}

Mulai langsung dengan judul (judul yang menarik sesuai SEO), lalu isi paragraf.
"""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 3500
    }
    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        text_out = data["choices"][0]["message"]["content"].strip()
        return text_out
    except Exception as e:
        print(f"[rewrite_article_with_openai] error: {e} - resp: {getattr(e, 'response', None)}")
        return None

# --- Leonardo image generation (start job, poll, download) ---
def generate_image_leonardo(prompt_text, slug, caption_text):
    """
    Returns local filename or None.
    """
    try:
        url = "https://cloud.leonardo.ai/api/rest/v1/generations"
        headers = {"Authorization": f"Bearer {LEONARDO_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "prompt": prompt_text,
            "modelId": "realistic-vision-v5.1",  # may need update to your available modelId
            "width": 1152,
            "height": 768,
            "num_images": 1,
            "guidance_scale": 7,
            "promptMagic": True
        }
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        # Leonardo may return job id under sdGenerationJob or similar
        gen_id = None
        if "sdGenerationJob" in data and "generationId" in data["sdGenerationJob"]:
            gen_id = data["sdGenerationJob"]["generationId"]
        elif "id" in data:
            gen_id = data["id"]
        else:
            # try common path
            gen_id = data.get("generation_id") or data.get("job_id")

        if not gen_id:
            print("[generate_image_leonardo] no generation id in response; raw:", data)
            return None

        # poll for result
        image_url = None
        poll_url_base = f"{url}/{gen_id}"
        for i in range(60):  # up to ~2 minutes (60*2s)
            time.sleep(2)
            s = requests.get(poll_url_base, headers=headers, timeout=30)
            if s.status_code != 200:
                continue
            js = s.json()
            gens = js.get("generations_by_pk", js).get("generated_images") if isinstance(js.get("generations_by_pk", js), dict) else js.get("generated_images", [])
            # support multiple shapes
            if isinstance(gens, list) and len(gens) > 0:
                image_url = gens[0].get("url") or gens[0].get("secure_url") or gens[0].get("uri")
                if image_url:
                    break
            # some returns different keys:
            if js.get("status") == "FAILED":
                print("[generate_image_leonardo] generation failed:", js)
                break

        if not image_url:
            print("[generate_image_leonardo] image_url not ready or not found")
            return None

        # download
        img_resp = requests.get(image_url, timeout=60)
        img_resp.raise_for_status()
        img = Image.open(BytesIO(img_resp.content)).convert("RGBA")

        # overlay caption text
        draw = ImageDraw.Draw(img)
        font_path = os.path.join("assets", "fonts", "DejaVuSans-Bold.ttf")
        # fallback font
        try:
            font = ImageFont.truetype(font_path, 28)
        except Exception:
            font = ImageFont.load_default()

        # wrap text if long
        caption = caption_text.strip()
        x = 30
        y = img.height - 60
        draw.text((x, y), caption, font=font, fill="white")

        # add logo (external url)
        logo_url = "https://i.imgur.com/SppIZHH.png"
        try:
            logo_r = requests.get(logo_url, timeout=20)
            logo_img = Image.open(BytesIO(logo_r.content)).convert("RGBA")
            logo_img = logo_img.resize((175, 158))
            img.paste(logo_img, (img.width - logo_img.width - 20, img.height - logo_img.height - 20), logo_img)
        except Exception as e:
            # ignore if logo fails
            pass

        # save locally
        filename = f"{slug}-{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        local_path = os.path.join(IMG_DIR, filename)
        img.convert("RGB").save(local_path, "PNG")
        return local_path

    except Exception as e:
        print(f"[generate_image_leonardo] error: {e}")
        return None

# --- Upload media to WordPress (returns media id) ---
def upload_image_to_wp(image_path):
    try:
        with open(image_path, "rb") as f:
            filename = os.path.basename(image_path)
            headers = {
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
            resp = requests.post(
                MEDIA_ENDPOINT,
                headers=headers,
                files={"file": (filename, f, "image/png")},
                auth=HTTPBasicAuth(WP_USER, WP_APP_PASS),
                timeout=60
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        print(f"[upload_image_to_wp] error: {e} - resp: {getattr(e, 'response', None)}")
        return None

# --- Create draft post on WordPress ---
def create_wp_draft(title, content, featured_media_id=None):
    try:
        post_data = {
            "title": title,
            "content": content,
            "status": "draft"
        }
        if featured_media_id:
            post_data["featured_media"] = featured_media_id

        resp = requests.post(POSTS_ENDPOINT, json=post_data, auth=HTTPBasicAuth(WP_USER, WP_APP_PASS), timeout=30)
        if resp.status_code in (200, 201):
            print(f"[create_wp_draft] Draft created: {title}")
            return resp.json()
        else:
            print(f"[create_wp_draft] failed {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        print(f"[create_wp_draft] exception: {e}")
        return None

# === Main flow ===
def main():
    articles = fetch_articles_from_rss(limit=1)
    for art in articles:
        print("Processing:", art["title"])
        full_text = fetch_full_article_text(art["url"])
        if not full_text:
            print(" - full article not found, using RSS summary as fallback")
            full_text = art["summary"]

        # rewrite/translate via OpenAI
        rewritten = rewrite_article_with_openai(art["title"], full_text)
        if not rewritten:
            print(" - rewrite failed, skipping")
            continue

        # extract caption from [[CAPTION]] token
        m = re.search(r"\[\[CAPTION\]\]\s*(.+)", rewritten)
        caption = m.group(1).strip() if m else art["title"]

        # generate image (may fail gracefully)
        slug = re.sub(r'[^a-z0-9]+', '-', art["title"].lower()).strip('-')[:50]
        image_prompt = f"Modern realistic illustration, landscape 1152x768 about: {art['title']}. Friendly thumbnail style."
        image_local = generate_image_leonardo(image_prompt, slug, caption)
        media_id = None
        if image_local:
            media_id = upload_image_to_wp(image_local)
            if media_id:
                print(f" - uploaded image to WP media id={media_id}")
            else:
                print(" - upload to WP failed, continuing without featured image")
        else:
            print(" - image generation failed, continue without image")

        # post to WP as draft (use title from rewritten first line)
        title_line = rewritten.splitlines()[0].strip() if rewritten else art["title"]
        created = create_wp_draft(title_line, rewritten, featured_media_id=media_id)
        if created:
            print("✅ Article saved as draft on WordPress:", created.get("link"))
        else:
            print("❌ Failed to create WP draft")

if __name__ == "__main__":
    main()
