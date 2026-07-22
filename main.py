import os
import re
import html
import logging
import requests
import io
import warnings
import hashlib
import json
from urllib.parse import unquote, urlparse, parse_qs

from dotenv import load_dotenv
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from groq import Groq

# -------------------- ENV --------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "-1004435011216"))

GROQ_API_KEY_THET_HTAR = os.getenv("GROQ_API_KEY_THET_HTAR")
GROQ_API_KEY_PHOE_MAUNG = os.getenv("GROQ_API_KEY_PHOE_MAUNG")
GROQ_API_KEY_PYT = os.getenv("GROQ_API_KEY_PYT") # New API Key for ပြည်သူ့ရင်ဖွင့်သံ

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing")

if not GROQ_API_KEY_THET_HTAR:
    raise ValueError("GROQ_API_KEY_THET_HTAR is missing")

if not GROQ_API_KEY_PHOE_MAUNG:
    raise ValueError("GROQ_API_KEY_PHOE_MAUNG is missing")

if not GROQ_API_KEY_PYT:
    raise ValueError("GROQ_API_KEY_PYT is missing")

# -------------------- WARNING FILTER --------------------
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# -------------------- LOGGING --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- CONFIG --------------------
CHANNEL_CONFIGS = {
    -1003882901649: {
        "name": "သက်ထား",
        "signature": "<b>သက်ထား</b>",
        "api_key": GROQ_API_KEY_THET_HTAR,
        "prompt": (
            "You are 'Thet Htar', a trendy female Burmese influencer. "
            "YOUR TASK: COMPLETELY REWRITE the news text provided. Summarize the content to ensure the final output is within 1000 characters. DO NOT copy the original text.\n\n"
            "STYLE REQUIREMENTS:\n"
            "- Language: Burmese (မြန်မာဘာသာ).\n"
            "- Tone: Friendly, conversational, and energetic.\n"
            "- Headline: Bold the headline using <b> tags.\n"
            "- Emojis: Use 3-5 relevant emojis to make it lively.\n"
            "- Structure: Use short, easy-to-read paragraphs.\n"
            "- Content: Keep all facts (names, dates, locations) accurate but change the wording entirely.\n"
            "- NO links, NO source signatures, NO 'The post appeared first on...'"
        )
    },
    -1002001243446: {
        "name": "ဖိုးမောင်",
        "signature": "<b>ဖိုးမောင်</b>",
        "api_key": GROQ_API_KEY_PHOE_MAUNG,
        "prompt": (
            "You are 'Phoe Maung', a professional Burmese news editor. "
            "YOUR TASK: PARAPHRASE and REWRITE the news into a professional report. Summarize the content to ensure the final output is within 1000 characters. DO NOT copy-paste.\n\n"
            "STYLE REQUIREMENTS:\n"
            "- Language: Burmese (မြန်မာဘာသာ).\n"
            "- Tone: Formal, objective, and authoritative.\n"
            "- Headline: Bold the headline using <b> tags.\n"
            "- Bullet Points: Use ✅, 🔰, ☑️, 💚 bullet points for the key facts. Use one type of bullet point for one post. THIS IS MANDATORY.\n"
            "- Structure: Clear, concise, and logical flow.\n"
            "- Content: Ensure 100% accuracy for names, numbers, and dates.\n"
            "- NO links, NO source signatures, NO promotional text."
        )
    },
    -1004313131336: { # New Channel: ပြည်သူ့ရင်ဖွင့်သံ
        "name": "ပြည်သူ့ရင်ဖွင့်သံ",
        "signature": "<b>ပြည်သူ့ရင်ဖွင့်သံ</b>",
        "api_key": GROQ_API_KEY_PYT,
        "prompt": (
            "You are 'ပြည်သူ့ရင်ဖွင့်သံ', a neutral and objective Burmese news reporter. "
            "YOUR TASK: REWRITE the news content into a factual and unbiased report. Summarize the content to ensure the final output is within 1000 characters. "
            "DO NOT copy the original text. Focus on presenting information clearly and neutrally.\n\n"
            "STYLE REQUIREMENTS:\n"
            "- Language: Burmese (မြန်မာဘာသာ).\n"
            "- Tone: Neutral, objective, and factual.\n"
            "- Headline: Bold the headline using <b> tags.\n"
            "- Bullet Points: Use 🔸, 🔹, 🔺, 🔻 bullet points for key facts. Use one type of bullet point for one post. THIS IS MANDATORY.\n"
            "- Structure: Clear, concise, and logical flow.\n"
            "- Content: Ensure 100% accuracy for names, numbers, and dates.\n"
            "- NO links, NO source signatures, NO promotional text."
        )
    }
}

CHANNELS = [
    "Thazinoo969",
    "popularjournal",
    "kothetjournalist9000",
    "hminewai",
    "snowqueen023"
]

RSS_URLS = [
    "https://popularmyanmar.com/feed",
    "https://www.bbc.com/burmese/index.xml",
    "https://www.rfa.org/burmese/rss2.xml"
]

RSSHUB_MIRRORS = [
    "https://rsshub.rssforever.com",
    "https://rsshub.app",
    "https://rsshub.moeyy.cn"
]

DB_FILE = "processed_posts.txt"
VERSIONS_FILE = "ai_versions.json"

# -------------------- DATABASE --------------------
def load_processed_posts():
    if not os.path.exists(DB_FILE):
        return set()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except Exception as e:
        logger.error(f"Failed to load processed posts: {e}")
        return set()

PROCESSED_POSTS = load_processed_posts()

def add_processed_post(post_id):
    global PROCESSED_POSTS
    if post_id not in PROCESSED_POSTS:
        PROCESSED_POSTS.add(post_id)
        try:
            with open(DB_FILE, "a", encoding="utf-8") as f:
                f.write(f"{post_id}\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"Failed to save processed post {post_id}: {e}")

def is_post_processed(post_id):
    return post_id in PROCESSED_POSTS

def load_ai_versions():
    if os.path.exists(VERSIONS_FILE):
        try:
            with open(VERSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load AI versions: {e}")
    return {}

def save_ai_versions(data):
    try:
        with open(VERSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Failed to save AI versions: {e}")

AI_DATA_STORE = load_ai_versions()

def update_store(key, value):
    global AI_DATA_STORE
    AI_DATA_STORE[key] = value
    save_ai_versions(AI_DATA_STORE)

def get_from_store(key, default=None):
    global AI_DATA_STORE
    return AI_DATA_STORE.get(key, default)

def delete_store(key):
    global AI_DATA_STORE
    if key in AI_DATA_STORE:
        del AI_DATA_STORE[key]
        save_ai_versions(AI_DATA_STORE)

# -------------------- PARSER HELPERS --------------------
def make_soup(content):
    try:
        return BeautifulSoup(content, "xml")
    except Exception as e:
        logger.warning(f"XML parser unavailable, fallback to html.parser: {e}")
        return BeautifulSoup(content, "html.parser")

# -------------------- URL / IMAGE HELPERS --------------------
def normalize_url(url):
    if not url:
        return None

    url = html.unescape(url.strip())

    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            url = qs["url"][0]
    except Exception:
        pass

    if "url=" in url:
        try:
            url = url.split("url=", 1)[-1]
        except Exception:
            pass

    url = unquote(url)
    return url.strip()

def get_tg_proxy_url(url):
    if not url:
        return None
    clean_url = normalize_url(url)
    if not clean_url:
        return None
    clean_url = clean_url.replace("https://", "").replace("http://", "")
    return f"https://i0.wp.com/{clean_url}"

def extract_image_from_srcset(srcset):
    if not srcset:
        return None
    try:
        parts = [p.strip() for p in srcset.split(",") if p.strip()]
        if not parts:
            return None
        return parts[-1].split(" ")[0].strip()
    except Exception:
        return None

def find_image_in_html_soup(soup):
    if not soup:
        return None

    for img in soup.find_all("img"):
        candidate = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-original")
            or extract_image_from_srcset(img.get("srcset"))
        )
        if candidate:
            return normalize_url(candidate)

    meta = soup.find("meta", attrs={"property": "og:image"}) or soup.find("meta", attrs={"name": "og:image"})
    if meta and meta.get("content"):
        return normalize_url(meta.get("content"))

    return None

def extract_image_url_from_item(item, desc_html=""):
    img_src = None

    if desc_html:
        try:
            d_soup = BeautifulSoup(desc_html, "html.parser")
            img_src = find_image_in_html_soup(d_soup)
            if img_src:
                return normalize_url(img_src)
        except Exception:
            pass

    try:
        media = item.find("media:content") or item.find("media:thumbnail") or item.find("enclosure")
        if media:
            img_src = media.get("url") or media.get("href")
            if img_src:
                return normalize_url(img_src)
    except Exception:
        pass

    try:
        content_encoded = item.find("content:encoded")
        if content_encoded and content_encoded.text:
            c_soup = BeautifulSoup(content_encoded.text, "html.parser")
            img_src = find_image_in_html_soup(c_soup)
            if img_src:
                return normalize_url(img_src)
    except Exception:
        pass

    try:
        img = item.find("img")
        if img:
            img_src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
                or extract_image_from_srcset(img.get("srcset"))
            )
            if img_src:
                return normalize_url(img_src)
    except Exception:
        pass

    return None

def is_valid_image_response(res):
    if not res or res.status_code != 200:
        return False

    content_type = res.headers.get("Content-Type", "").lower()
    if "image" in content_type:
        return True

    if len(res.content or b"") > 1500:
        return True

    return False

def download_media_as_bytes(url):
    if not url:
        return None

    url = normalize_url(url)
    if not url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": url
    }

    clean = url.replace("https://", "").replace("http://", "")

    candidates = [
        url,
        get_tg_proxy_url(url),
        f"https://wsrv.nl/?url={clean}&w=1280&output=jpg",
        f"https://images.weserv.nl/?url={clean}&w=1280",
    ]

    seen = set()
    unique_candidates = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    for candidate_url in unique_candidates:
        try:
            logger.info(f"Trying image download: {candidate_url}")
            res = requests.get(candidate_url, headers=headers, timeout=25, allow_redirects=True)
            if is_valid_image_response(res):
                media_io = io.BytesIO(res.content)
                media_io.name = "news_media.jpg"
                media_io.seek(0)
                logger.info(f"Image downloaded successfully from: {candidate_url}")
                return media_io
            else:
                logger.warning(
                    f"Invalid image response from {candidate_url} | "
                    f"status={res.status_code}, content-type={res.headers.get('Content-Type')}"
                )
        except Exception as e:
            logger.warning(f"Image download failed from {candidate_url}: {e}")
            continue

    logger.warning(f"All image download attempts failed for URL: {url}")
    return None

# -------------------- AI --------------------
def ai_rewrite_text(original_text, prompt_style, api_key):
    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": prompt_style},
                {"role": "user", "content": f"Please rewrite this news content completely in Burmese:\n\n{original_text}"}
            ],
            temperature=0.9,
            max_tokens=2048,
        )
        rewritten = completion.choices[0].message.content
        if rewritten and len(rewritten.strip()) > 20:
            return rewritten.strip()
        return original_text
    except Exception as e:
        logger.error(f"Groq AI Error: {e}")
        return original_text

# -------------------- UI / STORAGE HELPERS --------------------
def make_safe_key(post_id):
    return hashlib.md5(post_id.encode("utf-8")).hexdigest()[:15]

def get_channel_version_text(safe_id, ch_id):
    edited = get_from_store(f"edited_{safe_id}_{ch_id}")
    if edited:
        return edited
    versions = get_from_store(f"versions_{safe_id}", {})
    return versions.get(str(ch_id), None) # Return None if not processed by AI yet

def rebuild_preview_text(safe_id):
    raw_data = get_from_store(f"raw_{safe_id}")
    if not raw_data:
        return None

    source_info = raw_data.get("source", "Unknown")
    original_text = raw_data.get("text", "")
    img_url = raw_data.get("image_url")
    original_title = raw_data.get("title", "")

    full_text = f"<b>မူရင်းသတင်း:</b>\n<b>Source:</b> {html.escape(source_info)}\n"
    if original_title:
        full_text += f"<b>Title:</b> {html.escape(original_title)}\n"
    if img_url:
        full_text += f"🖼 <a href='{html.escape(img_url)}'>[ View Photo ]</a>\n"
    
    full_text += f"\n{html.escape(original_text[:800])}...\n\n"

    for ch_id, config in CHANNEL_CONFIGS.items():
        is_posted = get_from_store(f"is_posted_{safe_id}_{ch_id}", False)
        is_rewriting = get_from_store(f"is_rewriting_{safe_id}_{ch_id}", False)
        is_editing = get_from_store(f"is_editing_{safe_id}_{ch_id}", False)
        is_edited = get_from_store(f"is_edited_{safe_id}_{ch_id}", False)
        
        # Status Label
        if is_posted:
            status = "✅ Posted"
        elif is_editing:
            status = "✍️ Editing..."
        elif is_edited:
            status = "Edited ✅"
        elif is_rewriting:
            status = "⌛ AI Writing..."
        else:
            ai_ver = get_from_store(f"versions_{safe_id}", {}).get(str(ch_id))
            status = "🤖 AI Ready" if ai_ver else "🌑 Original"

        display_text = get_channel_version_text(safe_id, ch_id) or "မူရင်းအတိုင်း"
        # If display_text is edited or AI, it might contain HTML tags we want to keep, 
        # but for the preview we should handle it carefully.
        # If it's the "မူရင်းအတိုင်း" placeholder, we escape it.
        if display_text == "မူရင်းအတိုင်း":
            display_text = html.escape(display_text)
        
        full_text += f"====================\n📌 <b>{config['name']}</b> ({status}):\n{display_text[:500]}\n\n"

    return full_text

def get_post_buttons(safe_id):
    buttons = []
    for ch_id, config in CHANNEL_CONFIGS.items():
        is_posted = get_from_store(f"is_posted_{safe_id}_{ch_id}", False)
        is_editing = get_from_store(f"is_editing_{safe_id}_{ch_id}", False)
        is_edited = get_from_store(f"is_edited_{safe_id}_{ch_id}", False)
        
        edit_label = f"✍️ Editing..." if is_editing else (f"✅ Edited ({config['name']})" if is_edited else f"✍️ Edit ({config['name']})")
        
        row = [
            InlineKeyboardButton(edit_label, callback_data=f"edit|{safe_id}|{ch_id}"),
            InlineKeyboardButton(f"✨ AI Rewrite", callback_data=f"ai_rewrite|{safe_id}|{ch_id}"),
            InlineKeyboardButton("🟢 Posted" if is_posted else f"➡️ Post", callback_data=f"post|{safe_id}|{ch_id}")
        ]
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("🔴 DISCHARGE (DELETE)", callback_data=f"discharge|{safe_id}")])
    return buttons

# -------------------- FETCHERS --------------------
async def fetch_telegram_news(channel_username):
    extracted_items = []
    seen_in_batch = set()

    for url in RSSHUB_MIRRORS:
        try:
            logger.info(f"Fetching Telegram @{channel_username} via {url}")
            res = requests.get(f"{url}/telegram/channel/{channel_username}", timeout=20)
            if res.status_code != 200:
                continue

            soup = make_soup(res.content)
            items = soup.find_all("item")
            if not items:
                soup = BeautifulSoup(res.content, "html.parser")
                items = soup.find_all("item")

            for item in items[:5]:
                guid_tag = item.find("guid") or item.find("link")
                if not guid_tag or not guid_tag.text:
                    continue
                
                raw_guid = guid_tag.text.strip()
                normalized_guid = raw_guid.split('?')[0].rstrip('/')
                
                title = item.find("title").text.strip() if item.find("title") and item.find("title").text else ""
                desc_html = ""
                desc_tag = item.find("description")
                if desc_tag and desc_tag.text:
                    desc_html = desc_tag.text
                try:
                    d_soup = BeautifulSoup(desc_html, "html.parser")
                    summary_text = d_soup.get_text(separator="\n").strip()
                except Exception:
                    summary_text = desc_html.strip()
                summary_text = re.sub(r"The post.*?appeared first on.*", "", summary_text, flags=re.DOTALL | re.IGNORECASE).strip()

                content_to_hash = (title + summary_text).strip()
                content_hash = hashlib.md5(content_to_hash.encode('utf-8')).hexdigest()
                unique_id = f"tg_{channel_username}_{content_hash[:16]}"
                
                if is_post_processed(unique_id) or unique_id in seen_in_batch:
                    continue
                
                seen_in_batch.add(unique_id)
                img_src = extract_image_url_from_item(item, desc_html)

                extracted_items.append({
                    "id": unique_id,
                    "source": f"Telegram @{channel_username}",
                    "title": title,
                    "summary": summary_text,
                    "image_url": img_src,
                    "link": item.find("link").text.strip() if item.find("link") and item.find("link").text else normalized_guid
                })

            if extracted_items:
                return extracted_items

        except Exception as e:
            logger.warning(f"Failed fetching from mirror {url}: {e}")
            continue

    return []

async def fetch_rss_news(rss_url):
    source_name = "RSS Feed"
    if "bbc.com" in rss_url:
        source_name = "BBC Burmese"
    elif "rfa.org" in rss_url:
        source_name = "RFA Burmese"
    elif "popularmyanmar" in rss_url:
        source_name = "Popular Journal"

    try:
        logger.info(f"Fetching RSS: {rss_url}")
        response = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if response.status_code != 200:
            return []

        soup = make_soup(response.content)
        items = soup.find_all("item")
        if not items:
            soup = BeautifulSoup(response.content, "html.parser")
            items = soup.find_all("item")

        extracted_items = []
        seen_in_batch = set()
        
        for item in items[:5]:
            guid_tag = item.find("guid") or item.find("link")
            if not guid_tag or not guid_tag.text:
                continue
            
            raw_guid = guid_tag.text.strip()
            normalized_guid = raw_guid.split('?')[0].rstrip('/')

            title = item.find("title").text.strip() if item.find("title") and item.find("title").text else ""
            desc = item.find("description").text if item.find("description") and item.find("description").text else ""

            try:
                d_soup = BeautifulSoup(desc, "html.parser")
                body_text = d_soup.get_text(separator="\n").strip()
            except Exception:
                body_text = desc.strip()

            summary_text = f"<b>{title}</b>\n\n{body_text}".strip()
            summary_text = re.sub(r"The post.*?appeared first on.*", "", summary_text, flags=re.DOTALL | re.IGNORECASE).strip()

            content_to_hash = (title + summary_text).strip()
            content_hash = hashlib.md5(content_to_hash.encode('utf-8')).hexdigest()
            unique_id = f"rss_{content_hash[:16]}"
            
            if is_post_processed(unique_id) or unique_id in seen_in_batch:
                continue
            
            seen_in_batch.add(unique_id)
            img_src = extract_image_url_from_item(item, desc)

            extracted_items.append({
                "id": unique_id,
                "source": source_name,
                "title": title,
                "summary": summary_text,
                "image_url": img_src,
                "link": item.find("link").text.strip() if item.find("link") and item.find("link").text else normalized_guid
            })

        return extracted_items

    except Exception as e:
        logger.warning(f"RSS fetch error from {rss_url}: {e}")
        return []

# -------------------- BOT ACTIONS --------------------
async def check_news(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Checking news...")

    for channel in CHANNELS:
        items = await fetch_telegram_news(channel)
        for item in items:
            await send_review(context, item)

    for rss_url in RSS_URLS:
        items = await fetch_rss_news(rss_url)
        for item in items:
            await send_review(context, item)

async def send_review(context: ContextTypes.DEFAULT_TYPE, item):
    bot = context.bot
    if is_post_processed(item["id"]):
        return

    clean_summary = item["summary"]
    if len(clean_summary) < 5:
        add_processed_post(item["id"])
        return

    safe_id = make_safe_key(item["id"])
    add_processed_post(item["id"])

    update_store(f"raw_{safe_id}", {
        "text": clean_summary,
        "link": item["link"],
        "image_url": item.get("image_url"),
        "source": item["source"],
        "title": item.get("title", "")
    })

    preview_text = rebuild_preview_text(safe_id)
    buttons = get_post_buttons(safe_id)

    media_msg_id = None
    if item.get("image_url"):
        img_file = download_media_as_bytes(item["image_url"])
        if img_file:
            try:
                media_msg = await bot.send_photo(chat_id=ADMIN_ID, photo=img_file)
                media_msg_id = media_msg.message_id
            except Exception as e:
                logger.warning(f"Failed to send admin preview image: {e}")

    review_msg = await bot.send_message(
        chat_id=ADMIN_ID,
        text=preview_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )

    if media_msg_id:
        update_store(f"media_msg_{safe_id}", media_msg_id)
        update_store(f"msg_to_safe_{media_msg_id}", safe_id)

    update_store(f"review_msg_{safe_id}", review_msg.message_id)
    update_store(f"msg_to_safe_{review_msg.message_id}", safe_id)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    action, safe_id = parts[0], parts[1]

    if action == "ignore":
        return

    if action == "ai_rewrite":
        ch_id = int(parts[2])
        update_store(f"is_rewriting_{safe_id}_{ch_id}", True)
        # Update UI to show "AI Writing..."
        await query.edit_message_text(
            text=rebuild_preview_text(safe_id),
            reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)),
            parse_mode=ParseMode.HTML
        )
        
        raw_data = get_from_store(f"raw_{safe_id}")
        original_text = raw_data.get("text", "")
        config = CHANNEL_CONFIGS[ch_id]
        
        rewritten_text = ai_rewrite_text(original_text, config["prompt"], config["api_key"])
        
        versions = get_from_store(f"versions_{safe_id}", {})
        versions[str(ch_id)] = rewritten_text
        update_store(f"versions_{safe_id}", versions)
        update_store(f"is_rewriting_{safe_id}_{ch_id}", False)
        
        # Final UI Update
        await query.edit_message_text(
            text=rebuild_preview_text(safe_id),
            reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)),
            parse_mode=ParseMode.HTML
        )

    elif action == "post":
        ch_id = int(parts[2])
        raw = get_from_store(f"raw_{safe_id}") or {}
        img_url = raw.get("image_url")

        post_text = get_from_store(f"edited_{safe_id}_{ch_id}")
        if not post_text:
            post_text = get_from_store(f"versions_{safe_id}", {}).get(str(ch_id))
        if not post_text:
            post_text = raw.get("text", "")
        
        if not post_text:
            return

        try:
            img = download_media_as_bytes(img_url)
            if img:
                await context.bot.send_photo(chat_id=ch_id, photo=img, caption=post_text, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(chat_id=ch_id, text=post_text, parse_mode=ParseMode.HTML)

            update_store(f"is_posted_{safe_id}_{ch_id}", True)
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)))
            # Also update the preview text to show the "Posted" status
            await query.edit_message_text(
                text=rebuild_preview_text(safe_id),
                reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Post Error: {e}")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Post Error: {e}")

    elif action == "edit":
        ch_id = int(parts[2])
        for loop_ch in CHANNEL_CONFIGS:
            update_store(f"is_editing_{safe_id}_{loop_ch}", False)

        update_store(f"is_editing_{safe_id}_{ch_id}", True)
        review_msg_id = get_from_store(f"review_msg_{safe_id}")

        # Update preview to show "Editing..."
        await query.edit_message_text(
            text=rebuild_preview_text(safe_id),
            reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)),
            parse_mode=ParseMode.HTML
        )

        current_text_for_edit = get_channel_version_text(safe_id, ch_id) or get_from_store(f"raw_{safe_id}").get("text", "")

        instruction_msg = await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"✍️ <b>{CHANNEL_CONFIGS[ch_id]['name']}</b> အတွက် စာသားပြင်ဆင်ပါ။\n"
                f"ဒီ message ကို <b>Reply</b> ပြန်ပြီး edited text ပို့ပေးပါ။\n\n"
                f"<b>လက်ရှိစာသား:</b>\n{html.escape(current_text_for_edit[:500])}..."
            ),
            parse_mode=ParseMode.HTML,
            reply_to_message_id=review_msg_id
        )

        update_store(f"edit_context_{instruction_msg.message_id}", {"safe_id": safe_id, "ch_id": ch_id})

    elif action == "discharge":
        m_id = get_from_store(f"media_msg_{safe_id}")
        r_id = get_from_store(f"review_msg_{safe_id}")
        try:
            if m_id: await context.bot.delete_message(ADMIN_ID, m_id)
            if r_id: await context.bot.delete_message(ADMIN_ID, r_id)
        except: pass

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.reply_to_message:
        return

    reply_to_id = msg.reply_to_message.message_id
    # Use text_html to preserve bold/italic tags
    new_text = msg.text_html or msg.caption_html or msg.text or msg.caption
    if not new_text:
        return

    edit_ctx = get_from_store(f"edit_context_{reply_to_id}")
    if edit_ctx:
        safe_id, ch_id = edit_ctx["safe_id"], edit_ctx["ch_id"]
    else:
        # Fallback to searching which one is in editing state
        # This is less reliable if multiple posts are being edited
        # But we use msg_to_safe to help
        safe_id = get_from_store(f"msg_to_safe_{reply_to_id}")
        if not safe_id:
            return
        ch_id = next((c for c in CHANNEL_CONFIGS if get_from_store(f"is_editing_{safe_id}_{c}")), None)
        if not ch_id:
            return

    update_store(f"edited_{safe_id}_{ch_id}", new_text)
    update_store(f"is_editing_{safe_id}_{ch_id}", False)
    update_store(f"is_edited_{safe_id}_{ch_id}", True)

    review_msg_id = get_from_store(f"review_msg_{safe_id}")
    if review_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=ADMIN_ID,
                message_id=review_msg_id,
                text=rebuild_preview_text(safe_id),
                reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning(f"Failed to update preview: {e}")

    await msg.reply_text("✅ ပြင်ဆင်ပြီးပါပြီ။")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_reply))
    app.job_queue.run_repeating(check_news, interval=300, first=5)
    app.run_polling()

if __name__ == "__main__": main()
