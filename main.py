import os
import re
import html
import logging
import httpx
import io
import warnings
import hashlib
import json
import asyncio
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
GROQ_API_KEY_PYT = os.getenv("GROQ_API_KEY_PYT")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing")

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
            "- Headline: The first line MUST be the headline, bolded using <b> tags, and optionally include a relevant emoji at the beginning (e.g., 💵 <b>ဗဟိုဘဏ်က စားသုံးဆီတင်သွင်းသူများသို အမေရိကန်ဒေါ်လာ ၄ သန်းကျော် ရောင်းချပေး</b>).\n"
            "- Introduction: Write a short introductory paragraph summarizing the main event.\n"
            "- Bullet Points: Extract 2 to 4 key facts and list them using the 🔹 bullet point. Each bullet point must start with 🔹.\n"
            "- Hashtags: Add 3 to 5 relevant English hashtags at the end (e.g., #Myanmar #EconomyNews).\n"
            "- Signature: The very last line MUST be your name 'ဖိုးမောင်' without any formatting.\n"
            "- Content: Ensure 100% accuracy for names, numbers, and dates.\n"
            "- NO links, NO original source signatures, NO promotional text."
        )
    },
    -1004313131336: {
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

CHANNELS = ["Thazinoo969", "popularjournal", "kothetjournalist9000", "hminewai", "snowqueen023"]
RSS_URLS = ["https://popularmyanmar.com/feed", "https://www.bbc.com/burmese/index.xml", "https://www.rfa.org/burmese/rss2.xml"]
RSSHUB_MIRRORS = ["https://rsshub.rssforever.com", "https://rsshub.app", "https://rsshub.moeyy.cn"]

DB_FILE = "processed_posts.txt"
VERSIONS_FILE = "ai_versions.json"

# -------------------- DATABASE --------------------
def load_processed_posts():
    if not os.path.exists(DB_FILE): return set()
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
    return AI_DATA_STORE.get(key, default)

def delete_store(key):
    if key in AI_DATA_STORE:
        del AI_DATA_STORE[key]
        save_ai_versions(AI_DATA_STORE)

# -------------------- ASYNC HELPERS --------------------
async def async_http_get(url, headers=None, timeout=20):
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers, timeout=timeout)
            return resp
        except Exception as e:
            logger.warning(f"Async HTTP GET failed for {url}: {e}")
            return None

def make_soup(content):
    try:
        return BeautifulSoup(content, "xml")
    except Exception:
        return BeautifulSoup(content, "html.parser")

# -------------------- URL / IMAGE HELPERS --------------------
def normalize_url(url):
    if not url: return None
    url = html.unescape(url.strip())
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "url" in qs and qs["url"]: url = qs["url"][0]
    except Exception: pass
    if "url=" in url:
        try: url = url.split("url=", 1)[-1]
        except Exception: pass
    return unquote(url).strip()

def extract_image_url_from_item(item, desc_html=""):
    img_src = None
    if desc_html:
        try:
            d_soup = BeautifulSoup(desc_html, "html.parser")
            for img in d_soup.find_all("img"):
                candidate = img.get("src") or img.get("data-src") or img.get("data-original")
                if candidate: return normalize_url(candidate)
        except Exception: pass
    try:
        media = item.find("media:content") or item.find("media:thumbnail") or item.find("enclosure")
        if media:
            img_src = media.get("url") or media.get("href")
            if img_src: return normalize_url(img_src)
    except Exception: pass
    return None

async def download_media_async(url):
    if not url: return None
    url = normalize_url(url)
    if not url: return None
    
    clean = url.replace("https://", "").replace("http://", "")
    candidates = [
        url,
        f"https://i0.wp.com/{clean}",
        f"https://wsrv.nl/?url={clean}&w=1280&output=jpg"
    ]
    
    for c_url in candidates:
        resp = await async_http_get(c_url, timeout=25)
        if resp and resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "").lower()
            if "image" in content_type or len(resp.content) > 1500:
                media_io = io.BytesIO(resp.content)
                media_io.name = "news_media.jpg"
                return media_io
    return None

# -------------------- AI --------------------
async def ai_rewrite_text_async(original_text, prompt_style, api_key):
    try:
        # Groq client is not natively async, but we can run it in a thread to avoid blocking the loop
        def sync_call():
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
            return completion.choices[0].message.content

        loop = asyncio.get_event_loop()
        rewritten = await loop.run_in_executor(None, sync_call)
        if rewritten and len(rewritten.strip()) > 20:
            return rewritten.strip()
        return original_text
    except Exception as e:
        logger.error(f"Groq AI Error: {e}")
        return original_text

# -------------------- UI / STORAGE HELPERS --------------------
def make_safe_key(post_id):
    return hashlib.md5(post_id.encode("utf-8")).hexdigest()[:15]

def rebuild_preview_text(safe_id):
    raw_data = get_from_store(f"raw_{safe_id}")
    if not raw_data: return None
    
    full_text = f"<b>မူရင်းသတင်း:</b>\n<b>Source:</b> {html.escape(raw_data.get('source', 'Unknown'))}\n"
    if raw_data.get("title"): full_text += f"<b>Title:</b> {html.escape(raw_data['title'])}\n"
    full_text += f"\n{html.escape(raw_data.get('text', ''))}\n"

    versions = get_from_store(f"versions_{safe_id}", {})
    for ch_id, config in CHANNEL_CONFIGS.items():
        v_text = versions.get(str(ch_id))
        e_text = get_from_store(f"edited_{safe_id}_{ch_id}")
        is_rw = get_from_store(f"is_rewriting_{safe_id}_{ch_id}", False)
        is_ed = get_from_store(f"is_edited_{safe_id}_{ch_id}", False)
        is_ps = get_from_store(f"is_posted_{safe_id}_{ch_id}", False)

        status = []
        if is_rw: status.append("🔄 AI Rewriting...")
        elif is_ed: status.append("✍️ Admin Edited")
        elif v_text: status.append("✨ AI Rewritten")
        if is_ps: status.append("✅ Posted")
        
        full_text += f"\n---\n<b>{config['name']}</b>{' (' + ', '.join(status) + ')' if status else ''}:\n"
        full_text += f"{e_text or v_text or '<i>(Not yet processed by AI)</i>'}\n"
    return full_text

def get_post_buttons(safe_id):
    buttons = []
    for ch_id, config in CHANNEL_CONFIGS.items():
        is_rw = get_from_store(f"is_rewriting_{safe_id}_{ch_id}", False)
        is_ps = get_from_store(f"is_posted_{safe_id}_{ch_id}", False)
        is_ed = get_from_store(f"is_editing_{safe_id}_{ch_id}", False)

        row = []
        # AI Rewrite
        row.append(InlineKeyboardButton(
            f"{'🔄' if is_rw else '✨'} {config['name']} AI",
            callback_data=f"ai_rewrite|{safe_id}|{ch_id}" if not (is_ps or is_ed) else "ignore"
        ))
        # Edit
        row.append(InlineKeyboardButton(
            f"{'✍️' if is_ed else '✏️'} {config['name']} Edit",
            callback_data=f"edit|{safe_id}|{ch_id}" if not (is_ps or is_rw) else "ignore"
        ))
        # Post
        row.append(InlineKeyboardButton(
            f"✅ {config['name']} Post",
            callback_data=f"post|{safe_id}|{ch_id}" if not (is_ps or is_rw or is_ed) else "ignore"
        ))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🗑️ Discharge", callback_data=f"discharge|{safe_id}")])
    return buttons

# -------------------- FETCHER --------------------
async def fetch_telegram_news(channel_username):
    extracted = []
    seen = set()
    for mirror in RSSHUB_MIRRORS:
        url = f"{mirror}/telegram/channel/{channel_username}"
        resp = await async_http_get(url)
        if not resp or resp.status_code != 200: continue
        
        soup = make_soup(resp.content)
        items = soup.find_all("item")
        for item in items[:5]:
            guid = (item.find("guid") or item.find("link")).text.strip().split('?')[0].rstrip('/')
            title = item.find("title").text.strip() if item.find("title") else ""
            desc_html = item.find("description").text if item.find("description") else ""
            summary = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n").strip()
            summary = re.sub(r"The post.*?appeared first on.*", "", summary, flags=re.DOTALL | re.IGNORECASE).strip()

            uid = f"tg_{hashlib.md5((guid + title + summary).encode()).hexdigest()[:16]}"
            if is_post_processed(uid) or uid in seen: continue
            seen.add(uid)
            extracted.append({
                "id": uid, "source": f"Telegram @{channel_username}", "title": title,
                "summary": summary, "image_url": extract_image_url_from_item(item, desc_html),
                "link": item.find("link").text.strip() if item.find("link") else guid
            })
        if extracted: break
    return extracted

async def fetch_rss_news(rss_url):
    name = "RSS"
    if "bbc.com" in rss_url: name = "BBC"
    elif "rfa.org" in rss_url: name = "RFA"
    elif "popularmyanmar" in rss_url: name = "Popular"

    resp = await async_http_get(rss_url)
    if not resp or resp.status_code != 200: return []
    
    soup = make_soup(resp.content)
    extracted = []
    seen = set()
    for item in soup.find_all("item")[:5]:
        guid = (item.find("guid") or item.find("link")).text.strip().split('?')[0].rstrip('/')
        title = item.find("title").text.strip() if item.find("title") else ""
        desc = item.find("description").text if item.find("description") else ""
        body = BeautifulSoup(desc, "html.parser").get_text(separator="\n").strip()
        summary = f"<b>{title}</b>\n\n{body}".strip()
        summary = re.sub(r"The post.*?appeared first on.*", "", summary, flags=re.DOTALL | re.IGNORECASE).strip()

        uid = f"rss_{hashlib.md5((guid + title + summary).encode()).hexdigest()[:16]}"
        if is_post_processed(uid) or uid in seen: continue
        seen.add(uid)
        extracted.append({
            "id": uid, "source": name, "title": title, "summary": summary,
            "image_url": extract_image_url_from_item(item, desc),
            "link": item.find("link").text.strip() if item.find("link") else guid
        })
    return extracted

# -------------------- BOT ACTIONS --------------------
async def check_news(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Checking news...")
    tasks = [fetch_telegram_news(ch) for ch in CHANNELS] + [fetch_rss_news(url) for url in RSS_URLS]
    results = await asyncio.gather(*tasks)
    
    for items in results:
        for item in items:
            if not is_post_processed(item["id"]):
                add_processed_post(item["id"])
                await send_review(context, item)

async def send_review(context: ContextTypes.DEFAULT_TYPE, item):
    safe_id = make_safe_key(item["id"])
    update_store(f"raw_{safe_id}", {
        "text": item["summary"], "link": item["link"],
        "image_url": item.get("image_url"), "source": item["source"],
        "title": item.get("title", "")
    })

    img_file = await download_media_async(item.get("image_url"))
    if img_file:
        try:
            m_msg = await context.bot.send_photo(chat_id=ADMIN_ID, photo=img_file)
            update_store(f"media_msg_{safe_id}", m_msg.message_id)
            update_store(f"msg_to_safe_{m_msg.message_id}", safe_id)
        except Exception: pass

    r_msg = await context.bot.send_message(
        chat_id=ADMIN_ID, text=rebuild_preview_text(safe_id),
        reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)),
        parse_mode=ParseMode.HTML
    )
    update_store(f"review_msg_{safe_id}", r_msg.message_id)
    update_store(f"msg_to_safe_{r_msg.message_id}", safe_id)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    if len(parts) < 2 or parts[0] == "ignore": return
    action, safe_id = parts[0], parts[1]

    if action == "ai_rewrite":
        ch_id = int(parts[2])
        update_store(f"is_rewriting_{safe_id}_{ch_id}", True)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)))
        
        raw = get_from_store(f"raw_{safe_id}", {})
        config = CHANNEL_CONFIGS[ch_id]
        rewritten = await ai_rewrite_text_async(raw.get("text", ""), config["prompt"], config["api_key"])
        
        versions = get_from_store(f"versions_{safe_id}", {})
        versions[str(ch_id)] = rewritten
        update_store(f"versions_{safe_id}", versions)
        update_store(f"is_rewriting_{safe_id}_{ch_id}", False)
        
        r_msg_id = get_from_store(f"review_msg_{safe_id}")
        if r_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=ADMIN_ID, message_id=r_msg_id,
                    text=rebuild_preview_text(safe_id),
                    reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)),
                    parse_mode=ParseMode.HTML
                )
            except Exception: pass

    elif action == "post":
        ch_id = int(parts[2])
        raw = get_from_store(f"raw_{safe_id}", {})
        post_text = get_from_store(f"edited_{safe_id}_{ch_id}") or \
                    get_from_store(f"versions_{safe_id}", {}).get(str(ch_id)) or \
                    raw.get("text", "")
        
        try:
            img = await download_media_async(raw.get("image_url"))
            if img: await context.bot.send_photo(chat_id=ch_id, photo=img, caption=post_text, parse_mode=ParseMode.HTML)
            else: await context.bot.send_message(chat_id=ch_id, text=post_text, parse_mode=ParseMode.HTML)
            update_store(f"is_posted_{safe_id}_{ch_id}", True)
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)))
        except Exception as e:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 ERROR posting to {CHANNEL_CONFIGS[ch_id]['name']}: {e}")

    elif action == "edit":
        ch_id = int(parts[2])
        for c in CHANNEL_CONFIGS: update_store(f"is_editing_{safe_id}_{c}", False)
        update_store(f"is_editing_{safe_id}_{ch_id}", True)
        
        cur_text = get_from_store(f"edited_{safe_id}_{ch_id}") or \
                   get_from_store(f"versions_{safe_id}", {}).get(str(ch_id)) or \
                   get_from_store(f"raw_{safe_id}", {}).get("text", "")

        instr = await context.bot.send_message(
            chat_id=ADMIN_ID, text=f"✍️ <b>{CHANNEL_CONFIGS[ch_id]['name']}</b> အတွက် စာသားပြင်ပါ။\nReply ပြန်ပေးပါ။\n\n{html.escape(cur_text[:200])}...",
            parse_mode=ParseMode.HTML, reply_to_message_id=get_from_store(f"review_msg_{safe_id}")
        )
        update_store(f"edit_context_{instr.message_id}", {"safe_id": safe_id, "ch_id": ch_id})
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)))

    elif action == "discharge":
        try:
            m_id, r_id = get_from_store(f"media_msg_{safe_id}"), get_from_store(f"review_msg_{safe_id}")
            if m_id: await context.bot.delete_message(ADMIN_ID, m_id)
            if r_id: await context.bot.delete_message(ADMIN_ID, r_id)
        except Exception: pass

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.reply_to_message: return
    
    reply_id = msg.reply_to_message.message_id
    new_text = msg.text or msg.caption
    if not new_text: return

    ctx = get_from_store(f"edit_context_{reply_id}")
    if ctx:
        safe_id, ch_id = ctx["safe_id"], ctx["ch_id"]
        try: await context.bot.delete_message(ADMIN_ID, reply_id)
        except Exception: pass
        delete_store(f"edit_context_{reply_id}")
    else:
        safe_id = get_from_store(f"msg_to_safe_{reply_id}")
        ch_id = next((c for c in CHANNEL_CONFIGS if get_from_store(f"is_editing_{safe_id}_{c}")), None)
    
    if not safe_id or not ch_id: return

    update_store(f"edited_{safe_id}_{ch_id}", new_text)
    update_store(f"is_editing_{safe_id}_{ch_id}", False)
    update_store(f"is_edited_{safe_id}_{ch_id}", True)

    r_id = get_from_store(f"review_msg_{safe_id}")
    if r_id:
        try:
            await context.bot.edit_message_text(
                chat_id=ADMIN_ID, message_id=r_id, text=rebuild_preview_text(safe_id),
                reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)), parse_mode=ParseMode.HTML
            )
            await context.bot.delete_message(ADMIN_ID, msg.message_id)
        except Exception: pass

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.REPLY & filters.User(ADMIN_ID), handle_admin_reply))
    app.job_queue.run_repeating(check_news, interval=300, first=10)
    logger.info("Bot started (Async Optimized)...")
    app.run_polling()

if __name__ == "__main__":
    main()
