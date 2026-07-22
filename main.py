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
GROQ_API_KEY_PYT = os.getenv("GROQ_API_KEY_PYT")

if not BOT_TOKEN: raise ValueError("BOT_TOKEN is missing")
if not GROQ_API_KEY_THET_HTAR: raise ValueError("GROQ_API_KEY_THET_HTAR is missing")
if not GROQ_API_KEY_PHOE_MAUNG: raise ValueError("GROQ_API_KEY_PHOE_MAUNG is missing")
if not GROQ_API_KEY_PYT: raise ValueError("GROQ_API_KEY_PYT is missing")

# -------------------- LOGGING --------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# -------------------- CONFIG --------------------
CHANNEL_CONFIGS = {
    -1003882901649: {
        "name": "သက်ထား",
        "api_key": GROQ_API_KEY_THET_HTAR,
        "prompt": (
            "You are 'Thet Htar', a trendy female Burmese influencer. "
            "YOUR TASK: COMPLETELY REWRITE the news text provided. DO NOT copy the original text.\n\n"
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
        "api_key": GROQ_API_KEY_PHOE_MAUNG,
        "prompt": (
            "You are 'Phoe Maung', a professional Burmese news editor. "
            "YOUR TASK: PARAPHRASE and REWRITE the news into a professional report. DO NOT copy-paste.\n\n"
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
    -1004313131336: {
        "name": "ပြည်သူ့ရင်ဖွင့်သံ",
        "api_key": GROQ_API_KEY_PYT,
        "prompt": (
            "You are 'ပြည်သူ့ရင်ဖွင့်သံ', a neutral and objective Burmese news reporter. "
            "YOUR TASK: REWRITE the news content into a factual and unbiased report. "
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
RSSHUB_MIRRORS = ["https://rsshub.rssforever.com", "https://rsshub.app", "https://rsshub.moeyy.cn"]
DB_FILE = "processed_posts.txt"
VERSIONS_FILE = "ai_versions.json"

# -------------------- DATABASE --------------------
def load_processed_posts():
    if not os.path.exists(DB_FILE): return set()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f: return set(line.strip() for line in f if line.strip())
    except: return set()

PROCESSED_POSTS = load_processed_posts()

def add_processed_post(post_id):
    global PROCESSED_POSTS
    if post_id not in PROCESSED_POSTS:
        PROCESSED_POSTS.add(post_id)
        with open(DB_FILE, "a", encoding="utf-8") as f: f.write(f"{post_id}\n")

def is_post_processed(post_id): return post_id in PROCESSED_POSTS

def load_ai_versions():
    if os.path.exists(VERSIONS_FILE):
        try:
            with open(VERSIONS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {}

def save_ai_versions(data):
    with open(VERSIONS_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

AI_DATA_STORE = load_ai_versions()

def update_store(key, value):
    global AI_DATA_STORE
    AI_DATA_STORE[key] = value
    save_ai_versions(AI_DATA_STORE)

def get_from_store(key, default=None): return AI_DATA_STORE.get(key, default)

def delete_store(key):
    global AI_DATA_STORE
    if key in AI_DATA_STORE:
        del AI_DATA_STORE[key]
        save_ai_versions(AI_DATA_STORE)

# -------------------- HELPERS --------------------
def normalize_url(url):
    if not url: return None
    url = html.unescape(url.strip())
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "url" in qs: url = qs["url"][0]
    except: pass
    return unquote(url).strip()

def extract_image_url_from_item(item, desc_html=""):
    try:
        if desc_html:
            soup = BeautifulSoup(desc_html, "html.parser")
            img = soup.find("img")
            if img: return normalize_url(img.get("src") or img.get("data-src"))
        media = item.find("media:content") or item.find("media:thumbnail") or item.find("enclosure")
        if media: return normalize_url(media.get("url") or media.get("href"))
    except: pass
    return None

def download_media_as_bytes(url):
    if not url: return None
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if res.status_code == 200:
            bio = io.BytesIO(res.content)
            bio.name = "image.jpg"
            return bio
    except: pass
    return None

def ai_rewrite_text(original_text, prompt_style, api_key):
    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": prompt_style}, {"role": "user", "content": original_text}],
            temperature=0.9
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return original_text

def make_safe_key(post_id): return hashlib.md5(post_id.encode()).hexdigest()[:15]

def rebuild_preview_text(safe_id):
    raw = get_from_store(f"raw_{safe_id}")
    if not raw: return None
    
    text = f"<b>မူရင်းသတင်း:</b>\n<b>Source:</b> {html.escape(raw['source'])}\n"
    if raw.get("image_url"): text += f"🖼 <a href='{html.escape(raw['image_url'])}'>[ View Photo ]</a>\n"
    text += f"\n{html.escape(raw['text'][:800])}...\n\n"
    
    for ch_id, config in CHANNEL_CONFIGS.items():
        edited = get_from_store(f"edited_{safe_id}_{ch_id}")
        ai_ver = get_from_store(f"versions_{safe_id}", {}).get(str(ch_id))
        is_rewriting = get_from_store(f"is_rewriting_{safe_id}_{ch_id}", False)
        is_editing = get_from_store(f"is_editing_{safe_id}_{ch_id}", False)
        
        if is_editing:
            status = "✍️ Editing..."
        elif edited:
            status = "✅ Edited"
        elif is_rewriting:
            status = "⌛ Writing..."
        elif ai_ver:
            status = "🤖 AI"
        else:
            status = "🌑 Original"
            
        display_text = edited or ai_ver or "မူရင်းအတိုင်း"
        # We don't escape display_text if it's edited or ai_ver because they might have HTML tags
        # But for "မူရင်းအတိုင်း", we should escape the original text if we were to show it.
        if not edited and not ai_ver:
            display_text = html.escape(raw['text'][:500])
        else:
            # If it's AI or Edited, it might have tags. We limit length for preview.
            display_text = display_text[:500]
            
        text += f"====================\n📌 <b>{config['name']}</b> ({status}):\n{display_text}\n\n"
    return text

def get_post_buttons(safe_id):
    buttons = []
    for ch_id, config in CHANNEL_CONFIGS.items():
        is_posted = get_from_store(f"is_posted_{safe_id}_{ch_id}", False)
        is_editing = get_from_store(f"is_editing_{safe_id}_{ch_id}", False)
        edited = get_from_store(f"edited_{safe_id}_{ch_id}")
        
        edit_label = f"✍️ Editing ({config['name']})" if is_editing else (f"✅ Edited ({config['name']})" if edited else f"✍️ Edit ({config['name']})")
        
        row = [
            InlineKeyboardButton(edit_label, callback_data=f"edit|{safe_id}|{ch_id}"),
            InlineKeyboardButton(f"✨ AI Rewrite ({config['name']})", callback_data=f"ai|{safe_id}|{ch_id}"),
            InlineKeyboardButton("🟢 Posted" if is_posted else f"➡️ Post ({config['name']})", callback_data=f"post|{safe_id}|{ch_id}")
        ]
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔴 DELETE", callback_data=f"delete|{safe_id}")])
    return buttons

# -------------------- ACTIONS --------------------
async def check_news(context: ContextTypes.DEFAULT_TYPE):
    for ch in CHANNELS:
        for mirror in RSSHUB_MIRRORS:
            try:
                res = requests.get(f"{mirror}/telegram/channel/{ch}", timeout=15)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.content, "xml")
                    for item in soup.find_all("item")[:3]:
                        guid = item.find("guid").text
                        if not is_post_processed(guid):
                            await send_review(context, guid, ch, item)
                    break
            except: continue

async def send_review(context, guid, ch_name, item):
    safe_id = make_safe_key(guid)
    desc = item.find("description").text
    soup = BeautifulSoup(desc, "html.parser")
    clean_text = soup.get_text(separator="\n").strip()
    img_url = extract_image_url_from_item(item, desc)
    
    update_store(f"raw_{safe_id}", {"text": clean_text, "source": f"Telegram @{ch_name}", "image_url": img_url})
    add_processed_post(guid)
    
    if img_url:
        img = download_media_as_bytes(img_url)
        if img:
            try:
                media_msg = await context.bot.send_photo(chat_id=ADMIN_ID, photo=img)
                update_store(f"media_msg_{safe_id}", media_msg.message_id)
            except Exception as e:
                logger.error(f"Error sending photo: {e}")
    
    review_msg = await context.bot.send_message(
        chat_id=ADMIN_ID, text=rebuild_preview_text(safe_id),
        reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)), parse_mode=ParseMode.HTML
    )
    update_store(f"review_msg_{safe_id}", review_msg.message_id)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    action, safe_id = parts[0], parts[1]

    if action == "ai":
        ch_id = int(parts[2])
        update_store(f"is_rewriting_{safe_id}_{ch_id}", True)
        # Update UI to show "Writing..."
        await query.edit_message_text(text=rebuild_preview_text(safe_id), reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)), parse_mode=ParseMode.HTML)
        
        raw = get_from_store(f"raw_{safe_id}")
        rewritten = ai_rewrite_text(raw["text"], CHANNEL_CONFIGS[ch_id]["prompt"], CHANNEL_CONFIGS[ch_id]["api_key"])
        
        versions = get_from_store(f"versions_{safe_id}", {})
        versions[str(ch_id)] = rewritten
        update_store(f"versions_{safe_id}", versions)
        update_store(f"is_rewriting_{safe_id}_{ch_id}", False)
        # Final update
        await query.edit_message_text(text=rebuild_preview_text(safe_id), reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)), parse_mode=ParseMode.HTML)

    elif action == "post":
        ch_id = int(parts[2])
        raw = get_from_store(f"raw_{safe_id}")
        edited = get_from_store(f"edited_{safe_id}_{ch_id}")
        ai_ver = get_from_store(f"versions_{safe_id}", {}).get(str(ch_id))
        
        # Priority: Edited > AI > Original (escaped)
        post_text = edited or ai_ver or html.escape(raw["text"])
        
        try:
            img = download_media_as_bytes(raw.get("image_url"))
            if img: await context.bot.send_photo(chat_id=ch_id, photo=img, caption=post_text, parse_mode=ParseMode.HTML)
            else: await context.bot.send_message(chat_id=ch_id, text=post_text, parse_mode=ParseMode.HTML)
            
            update_store(f"is_posted_{safe_id}_{ch_id}", True)
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)))
        except Exception as e: 
            logger.error(f"Post Error: {e}")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Post Error: {e}")

    elif action == "edit":
        ch_id = int(parts[2])
        user_id = update.effective_user.id
        # Set context for the specific user
        update_store(f"edit_context_{user_id}", {"safe_id": safe_id, "ch_id": ch_id})
        # Set status to editing
        update_store(f"is_editing_{safe_id}_{ch_id}", True)
        # Update the preview message immediately to show "Editing..."
        await query.edit_message_text(text=rebuild_preview_text(safe_id), reply_markup=InlineKeyboardMarkup(get_post_buttons(safe_id)), parse_mode=ParseMode.HTML)
        # Ask user for input
        await context.bot.send_message(chat_id=user_id, text=f"✍️ <b>{CHANNEL_CONFIGS[ch_id]['name']}</b> အတွက် စာသားပို့ပေးပါ။", parse_mode=ParseMode.HTML)

    elif action == "delete":
        m_id, r_id = get_from_store(f"media_msg_{safe_id}"), get_from_store(f"review_msg_{safe_id}")
        if m_id: 
            try: await context.bot.delete_message(ADMIN_ID, m_id)
            except: pass
        if r_id: 
            try: await context.bot.delete_message(ADMIN_ID, r_id)
            except: pass

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ctx = get_from_store(f"edit_context_{user_id}")
    if not ctx: return
    
    safe_id = ctx['safe_id']
    ch_id = ctx['ch_id']
    
    # Save the text with HTML formatting
    update_store(f"edited_{safe_id}_{ch_id}", update.message.text_html or update.message.text)
    # Clear states
    delete_store(f"edit_context_{user_id}")
    update_store(f"is_editing_{safe_id}_{ch_id}", False)
    
    # Update the original review message
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
            logger.error(f"Update Preview Error: {e}")
            
    await update.message.reply_text("✅ ပြင်ဆင်ပြီးပါပြီ။")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(button_callback))
    # Handle text messages from anyone, context check will filter it
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_reply))
    app.job_queue.run_repeating(check_news, interval=300, first=5)
    app.run_polling()

if __name__ == "__main__": main()
