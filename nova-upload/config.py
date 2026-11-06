# -*- coding: utf-8 -*-
"""إعدادات بوت نوفا — عدّل ما تحتاجه من هنا فقط"""

import os

# ================= المسارات =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _load_env(path: str):
    """قارئ .env بسيط — بدون مكتبات خارجية"""
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


_load_env(os.path.join(BASE_DIR, ".env"))

# ================= التوكن =================
TOKEN = os.getenv("BOT_TOKEN", "")

# ================= الهوية =================
BOT_NAME = "نوفا"
TAGLINE = "مساعدك الذكي"
SUPPORT_URL = "https://t.me/vvfvq"
SUPPORT_USER = "@vvfvq"
CHANNEL_URL = ""          # ضع رابط قناتك هنا (اتركه فارغاً لإخفاء الزر)

# ================= الذكاء الاصطناعي =================
# الوضع الافتراضي: مجاني تماماً بدون مفتاح
KEYLESS = {
    "base": "https://text.pollinations.ai/openai",
    "models": ["openai"],
    "min_gap": 45,       # ثانية بين كل طلب — حد المزوّد المجاني (1 كل 45 ثانية)
}

# لو حصلت على مفتاح مجاني ضعه هنا، أو أرسله للبوت بأمر:
#   /setkey groq gsk_xxx
#   /setkey gemini AIza...
#   /setkey openrouter sk-or-...
PROVIDERS = {
    "groq": (
        "https://api.groq.com/openai/v1",
        ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    ),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.8-flash"],
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        ["deepseek/deepseek-chat-v3-0324:free",
         "meta-llama/llama-3.3-70b-instruct:free"],
    ),
}

AI_KEY = os.getenv("AI_KEY", "")
AI_BASE = os.getenv("AI_BASE", "")
AI_MODELS = []

# المزوّد من متغير البيئة (للاستضافة)
_PROVIDER = os.getenv("AI_PROVIDER", "").lower()
if _PROVIDER in PROVIDERS:
    AI_BASE, AI_MODELS = PROVIDERS[_PROVIDER]

# مفتاح محفوظ من داخل البوت عبر /setkey (بديل محلي)
_SAVED = os.path.join(DATA_DIR, "provider.json")
if not AI_KEY and os.path.exists(_SAVED):
    try:
        import json as _json
        _d = _json.load(open(_SAVED, encoding="utf-8"))
        if _d.get("key") and _d.get("provider") in PROVIDERS:
            AI_BASE, AI_MODELS = PROVIDERS[_d["provider"]]
            AI_KEY = _d["key"]
    except Exception:
        pass

AI_TIMEOUT = 90
AI_MAX_TOKENS = 900
AI_TEMPERATURE = 0.75
MEMORY_TURNS = 10         # كم رسالة سابقة يتذكرها البوت

# ================= الصور (مجاني بدون مفتاح) =================
IMAGE_ENABLED = True
IMAGE_URL = "https://image.pollinations.ai/prompt/{}?width=1024&height=1024&nologo=true"

# ================= قاعدة البيانات =================
DB_PATH = os.path.join(DATA_DIR, "nova.db")

# ================= الاستخدام =================
DAILY_LIMIT = 100         # رسالة مجانية يومياً لكل مستخدم (حماية من الإساءة)
COOLDOWN = 2              # ثانية بين كل رسالة وأخرى
MAX_INPUT = 2000          # أقصى طول للرسالة

# ================= اللمسات المميزة =================
MESSAGE_EFFECT = "5104841245755180586"     # تأثير 🔥 عند /start
STICKER_PACKS = ["UtyaDuck"]               # باكات الملصقات
STICKER_ON_START = False
REACTIONS = True                           # رياكشن على رسائل المستخدم
REACTION_WAIT = "👀"                       # أثناء التفكير
REACTION_DONE = "👍"                       # بعد الإجابة

# ================= الإدارة =================
ADMIN_IDS = [8220826281]   # صاحب البوت — أرسل /id لإضافة رقم آخر

# ================= الأسلوب =================
WELCOME = """\
<b>✨ {name}</b> — {tagline}
━━━━━━━━━━━━━━

أهلاً <b>{first}</b> 👋
<blockquote>أنا هنا لأجيبك، وأكتب لك، وأشرح، وأبرمج.</blockquote>

💎 <b>مجاني بالكامل</b> · {daily} رسالة يومياً
👇 اختر من الأزرار"""

# أفكار جاهزة — ضغطة واحدة والبوت يجاوب
IDEAS = {
    "explain": ("🧠 اشرح الذكاء الاصطناعي", "اشرح لي الذكاء الاصطناعي ببساطة شديدة وفي 5 أسطر فقط، بأسلوب ممتع."),
    "write": ("✍️ اكتب منشوراً", "اكتب منشوراً قصيراً ومؤثراً عن أهمية الاستمرار في التعلم، مناسباً للنشر على وسائل التواصل."),
    "code": ("💻 مثال برمجي", "اكتب لي مثالاً بسيطاً بلغة بايثون يوضح الحلقات، مع شرح سطرين فقط."),
    "plan": ("📚 خطة دراسية", "ضع لي خطة دراسية أسبوعية مختصرة لتعلم البرمجة من الصفر مع ساعات يومية."),
}

IDEAS_TEXT = """\
<b>✨ أفكار جاهزة</b>
━━━━━━━━━━━━━━

<blockquote>اضغط على أي فكرة وسأجيبك فوراً — بدون كتابة.</blockquote>"""


HELP_TEXT = """\
<b>ℹ️ دليل الاستخدام</b>
━━━━━━━━━━━━━━

<blockquote><b>💬 المحادثة</b> — اكتب سؤالك مباشرة، لا تحتاج أي أوامر.
<b>🧹 بداية جديدة</b> — /new لمسح الذاكرة.
<b>🎭 الأسلوب</b> — /mode لاختيار طريقة الرد.
<b>🖼 صورة</b> — اكتب: <code>صورة: وصف</code>
<b>👤 حسابي</b> — /me لمتابعة استخدامك.</blockquote>

<b>💡 نصائح</b>
<blockquote>• كن محدداً في سؤالك لتحصل على أفضل جواب
• البوت يتذكر سياق المحادثة — اسأل متابعةً مباشرة
• /new عندما تريد تغيير الموضوع كلياً</blockquote>"""

ABOUT_TEXT = """\
<b>✨ {name}</b> — {tagline}
━━━━━━━━━━━━━━

<blockquote>بوت ذكاء اصطناعي بالعربية، مجاني بالكامل.
محادثة · كتابة · برمجة · شرح · ترجمة · صور.

الإصدار 1.0 — تم بناؤه بشغف 💙</blockquote>

<b>💬 الدعم:</b> {support}"""

ACCOUNT_TEXT = """\
<b>👤 حسابي</b>
━━━━━━━━━━━━━━

<blockquote><b>الاسم:</b> {first}
<b>الأسلوب:</b> {mode}
<b>رسائل اليوم:</b> {used} / {limit}
<b>الإجمالي:</b> {total}
<b>عضو منذ:</b> {since}</blockquote>"""

LIMIT_TEXT = """\
<b>🌙 وصلت للحد اليومي</b>
━━━━━━━━━━━━━━

<blockquote>استخدمت <b>{limit}</b> رسالة اليوم — يعود رصيدك تلقائياً بعد منتصف الليل.</blockquote>

شكراً لاستخدامك {name} 💙"""

BUSY_TEXT = "⏳ <b>الضغط عالٍ الآن</b>\n\n<blockquote>جرّب سؤالك بعد لحظات.</blockquote>"

ERROR_TEXT = "⚠️ <b>حدث خطأ مؤقت</b>\n\n<blockquote>جرّب مرة أخرى بعد لحظات.</blockquote>"

GENERATING = "🎨 <b>أرسم الآن…</b>"
THINKING = "💭"

MODES = {
    "chat": {
        "label": "💬 محادثة عامة",
        "prompt": "أنت نوفا، مساعد ذكي ودود. أجب مباشرة وبإيجاز ووضوح، بالعربية.\n"
                  "لا تكتب مقدمات مثل «بالتأكيد» أو «سؤال رائع»، ولا تكرر السؤال. ادخل في الجواب فوراً.",
    },
    "write": {
        "label": "✍️ كتابة وتأليف",
        "prompt": "أنت كاتب محترف. اكتب النص المطلوب مباشرة بأسلوب جذاب وواضح، دون شرح أو مقدمات.",
    },
    "code": {
        "label": "💻 برمجة",
        "prompt": "أنت مهندس برمجيات خبير. أعطِ الكود مباشرة في كتلة كود، ثم سطرين شرح كحد أقصى.",
    },
    "study": {
        "label": "📚 شرح ودراسة",
        "prompt": "أنت معلّم صبور. اشرح بإيجاز وبأمثلة بسيطة، خطوة بخطوة، دون إطالة.",
    },
    "translate": {
        "label": "🌐 ترجمة وتلخيص",
        "prompt": "أنت مترجم محترف. أعطِ الترجمة أو الملخص مباشرة دون تعليق.",
    },
}

MODE_MENU = """\
<b>🎭 أسلوب الرد</b>
━━━━━━━━━━━━━━

<blockquote>الأسلوب الحالي: <b>{current}</b></blockquote>"""

IMAGE_MENU = """\
<b>🖼 توليد صورة</b>
━━━━━━━━━━━━━━

<blockquote>اكتب طلبك بهذه الطريقة:
<code>صورة: قطة رائد فضاء على القمر</code></blockquote>

<i>كلما كان الوصف أدق، كانت الصورة أجمل ✨</i>"""

MEDIA_MENU = """\
<b>🎵 أناشيد · أغاني · بودكاست</b>
━━━━━━━━━━━━━━

<blockquote>اكتب طلبك بأي صيغة، مثل:
<code>بدي عن قمري الشهيد</code>
<code>اغنية عن البحر</code>
<code>بودكاست عن فلسطين</code></blockquote>

أو استخدم الأوامر:
<code>/song الاسم</code> · <code>/nasheed الاسم</code> · <code>/podcast الاسم</code>

<i>أجيب لك أفضل 5 نتائج وأرسل الصوت مباشرة 🎧</i>"""

MEDIA_HINT = (
    "🎵 <b>اكتب الاسم بعد الأمر</b>\n\n"
    "<blockquote>مثال:\n"
    "<code>/song قمري الشهيد</code>\n"
    "<code>/podcast عن القدس</code></blockquote>"
)

MEDIA_LABELS = {"song": "🎵", "nasheed": "🕌", "podcast": "🎙"}

NEW_TEXT = """\
🧹 <b>محادثة جديدة</b>

<blockquote>مسحتُ الذاكرة. ابدأ الآن.</blockquote>"""

# أوامر القائمة التي تظهر في تيليجرام
COMMANDS = [
    ("start", "بدء البوت"),
    ("new", "محادثة جديدة"),
    ("mode", "تغيير الأسلوب"),
    ("image", "توليد صورة"),
    ("song", "بحث عن أناشيد وأغاني"),
    ("podcast", "بحث عن بودكاست"),
    ("me", "حسابي"),
    ("id", "رقم حسابي"),
    ("help", "المساعدة"),
    ("about", "عن البوت"),
]
