# -*- coding: utf-8 -*-
"""🔎 البحث عن أناشيد/أغاني/بودكاست وتحميل الصوت — مجاني وبدون مفاتيح API"""

import asyncio
import logging
import os
import re
import shutil
import time

import config

try:
    import yt_dlp
except Exception:                     # pragma: no cover
    yt_dlp = None

log = logging.getLogger("nova.media")

CACHE_DIR = os.path.join(config.DATA_DIR, "audio")
os.makedirs(CACHE_DIR, exist_ok=True)

MAX_BYTES = 45 * 1024 * 1024          # حد تيليجرام لرفع الملفات
_CLIENTS = ("android", "ios", "tv", "web_safari", "mweb", "default")
_BASE = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 25,
    "retries": 2,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "noprogress": True,
}


def available() -> bool:
    return yt_dlp is not None


def key_from_url(url: str) -> str:
    m = re.search(r"(?:v=|/)([A-Za-z0-9_-]{6,})", url or "")
    raw = m.group(1) if m else "track"
    return re.sub(r"[^A-Za-z0-9_-]", "", raw)[:40] or "track"


def fmt_duration(sec) -> str:
    try:
        sec = int(sec or 0)
    except Exception:
        return ""
    if sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ================= البحث =================
def _search_sync(query: str, limit: int) -> list:
    if not available():
        return []
    for target in (f"ytsearch{limit}:{query}", f"scsearch{limit}:{query}"):
        try:
            opts = dict(_BASE)
            opts.update({"extract_flat": "in_playlist", "skip_download": True})
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=False)
            items = []
            for e in (info or {}).get("entries") or []:
                if not e:
                    continue
                url = e.get("url") or e.get("webpage_url") or ""
                if target.startswith("ytsearch") and e.get("id"):
                    url = f"https://www.youtube.com/watch?v={e['id']}"
                if not url:
                    continue
                items.append({
                    "title": (e.get("title") or "").strip(),
                    "url": url,
                    "duration": e.get("duration"),
                    "uploader": (e.get("uploader") or e.get("channel") or "").strip(),
                })
            if items:
                return items[:limit]
        except Exception:
            continue
    return []


async def search(query: str, limit: int = 5) -> list:
    return await asyncio.to_thread(_search_sync, query, limit)


# ================= التحميل =================
def _cached(key: str):
    for name in os.listdir(CACHE_DIR):
        if name.startswith(key + "."):
            path = os.path.join(CACHE_DIR, name)
            try:
                if os.path.getsize(path) > 1024:
                    return path
            except OSError:
                pass
    return None


def _download_once(url: str, key: str, client: str):
    opts = dict(_BASE)
    opts.update({
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
        "outtmpl": os.path.join(CACHE_DIR, key + ".%(ext)s"),
        "max_filesize": MAX_BYTES,
        "prefer_ffmpeg": True,
    })
    if client != "default":
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        return path
    return None


def _download_sync(url: str, key: str, title: str = ""):
    cached = _cached(key)
    if cached:
        return cached

    last = None
    for client in _CLIENTS:
        try:
            path = _download_once(url, key, client)
            if path:
                log.info("media ok client=%s size=%dKB", client, os.path.getsize(path) // 1024)
                return path
        except Exception as e:
            last = e
            log.warning("media client %s: %s", client, str(e)[:180])

    # بديل: ساوندكلاود بنفس العنوان (لا يحجب سيرفرات الاستضافة عادة)
    if title:
        try:
            for item in _sc_entries(title, 3):
                try:
                    path = _download_once(item["url"], key + "_sc", "default")
                    if path:
                        log.info("media ok via soundcloud: %s", item["url"][:60])
                        return path
                except Exception as e:
                    last = e
        except Exception as e:
            last = e

    log.warning("media failed: %s | last=%s", url, str(last)[:200])
    return None


async def download(url: str, key: str, title: str = ""):
    try:
        return await asyncio.to_thread(_download_sync, url, key, title)
    except Exception as e:
        log.warning("media download error: %s", e)
        return None


def _sc_entries(query: str, limit: int = 3) -> list:
    opts = dict(_BASE)
    opts.update({"extract_flat": "in_playlist", "skip_download": True})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"scsearch{limit}:{query}", download=False)
    items = []
    for e in (info or {}).get("entries") or []:
        if not e:
            continue
        u = e.get("url") or e.get("webpage_url")
        if u:
            items.append({"url": u, "title": e.get("title") or ""})
    return items


# ================= تشخيص عن بُعد =================
def diagnose(url: str = "https://www.youtube.com/watch?v=cZsfAxlix3I", mode: str = "yt"):
    out = {
        "mode": mode,
        "ytdlp": getattr(getattr(yt_dlp, "version", None), "__version__", None),
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }
    if mode == "sc":
        try:
            t = time.time()
            items = _sc_entries("قمري الشهيد", 3)
            out["search"] = {"ok": bool(items), "n": len(items), "sec": round(time.time() - t, 1),
                             "first": items[0]["title"][:50] if items else ""}
            if items:
                t = time.time()
                path = _download_once(items[0]["url"], "diagsc_" + str(int(time.time())), "default")
                out["download"] = {"ok": bool(path), "sec": round(time.time() - t, 1),
                                   "size": os.path.getsize(path) if path else 0}
            else:
                out["download"] = {"ok": False, "err": "no results"}
        except Exception as e:
            out["error"] = str(e)[:300]
        return out

    if mode == "ia":
        try:
            import requests as _rq
            t = time.time()
            r = _rq.get(
                "https://archive.org/advancedsearch.php",
                params={"q": "أناشيد", "fl[]": ["identifier", "title"], "rows": 3, "output": "json"},
                timeout=20,
            )
            j = r.json()
            docs = j.get("response", {}).get("docs", [])
            out["search"] = {"status": r.status_code, "n": len(docs), "sec": round(time.time() - t, 1),
                             "first": (docs[0].get("title") or "")[:50] if docs else ""}
        except Exception as e:
            out["error"] = str(e)[:300]
        return out

    try:
        t = time.time()
        items = _search_sync("test", 2)
        out["search"] = {
            "ok": bool(items),
            "n": len(items),
            "sec": round(time.time() - t, 1),
            "first": (items[0]["title"][:50] if items else ""),
        }
    except Exception as e:
        out["search"] = {"ok": False, "err": repr(e)[:250]}

    key = "diag_" + str(int(time.time()))
    results = {}
    for client in _CLIENTS:
        try:
            t = time.time()
            path = _download_once(url, key, client)
            results[client] = {
                "ok": bool(path),
                "sec": round(time.time() - t, 1),
                "size": (os.path.getsize(path) if path else 0),
            }
            if path:
                break
        except Exception as e:
            results[client] = {"ok": False, "err": str(e)[:160]}
    out["download"] = results
    return out


# ================= كشف النية من النص =================
_TRIGGERS = (
    "بدي عن", "بدّي عن", "بديلي عن", "أريد عن", "اريد عن", "ابحث عن",
    "ابحثلي عن", "ابحث لي عن", "دور عن", "دورلي عن", "دور لي عن",
    "جيب عن", "جيبلي عن", "اطلب عن", "اطلبلي عن",
    "بدي", "بدّي", "أريد", "اريد", "ابحث", "دور", "جيبلي", "جيب", "اطلب", "هات",
)

_KEYWORDS = {
    "podcast": ("بودكاست", "بوتكاست", "podcast"),
    "nasheed": ("نشيد", "أنشودة", "انشودة", "أناشيد", "اناشيد", "نشيدة", "أنشوده"),
    "song": ("أغنية", "اغنية", "أغاني", "اغاني", "مقطع صوتي", "مقطع", "صوتيات"),
}


def detect(text: str):
    """يرجّع (الاستعلام، النوع) أو (None, None) إذا كانت رسالة عادية"""
    t = (text or "").strip()
    if not t:
        return None, None
    low = t.lower()

    kind = None
    for k, words in _KEYWORDS.items():
        if any(w in low for w in words):
            kind = k
            break

    trigger = None
    for p in sorted(_TRIGGERS, key=len, reverse=True):
        if low.startswith(p):
            trigger = p
            break

    if kind is None:
        # «بدي عن قمري الشهيد» — طلب صريح بمقطع، بدون ذكر كلمة أغنية
        if trigger and trigger.endswith("عن") and len(t) <= 80:
            kind = "song"
        else:
            return None, None
    elif len(t) > 120:
        return None, None

    q = t
    for words in _KEYWORDS.values():
        for w in words:
            q = re.sub(re.escape(w), " ", q, flags=re.IGNORECASE)
    if trigger:
        q = q[len(trigger):]
    q = re.sub(r"^(عن|لي)\s+", "", q.strip(), flags=re.IGNORECASE)
    q = re.sub(r"^(صوت|فيديو|مقطع)\s*:\s*", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip(" -،,.:؟?!")
    if len(q) < 2:
        return None, None
    return q, kind
