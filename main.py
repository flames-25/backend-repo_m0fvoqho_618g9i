import os
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime

from database import create_document
from schemas import Analysis

app = FastAPI(title="YouTube Content Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "YouTube Analyzer Backend Running"}


class AnalyzeRequest(BaseModel):
    topic: str = Field(..., description="Topik video")
    keywords: List[str] = Field(default_factory=list, description="Kata kunci utama")
    niche: str | None = Field(None, description="Niche konten")
    audience: str | None = Field(None, description="Audiens target")
    platform: str = Field("youtube", description="youtube atau shorts")
    region: str | None = Field("WIB", description="Zona waktu, misal WIB/WITA/WIT")


def pick_best_time(region: str | None, platform: str) -> str:
    # Simple heuristic for Indonesia
    if platform == "shorts":
        base = ["07:30", "12:30", "18:30", "21:00"]
    else:
        base = ["11:00", "16:00", "19:00", "21:00"]

    tz = region or "WIB"
    return f"{base[2]} {tz} (±1 jam)"


def build_hashtags(keywords: List[str], niche: str | None) -> List[str]:
    pool = []
    for k in keywords[:5]:
        k2 = k.strip().replace(" ", "")
        if k2:
            pool.append(f"#{k2}")
            pool.append(f"#{k2.capitalize()}")
    if niche:
        n = niche.strip().replace(" ", "")
        pool += [f"#{n}", f"#{n}Indonesia", "#YouTubeTips"]
    # unique and length 3-10
    seen = set()
    uniq = []
    for h in pool:
        if h.lower() not in seen and len(uniq) < 10:
            uniq.append(h)
            seen.add(h.lower())
    while len(uniq) < 3:
        uniq.append(f"#contentcreator")
    return uniq[:10]


def make_hook(topic: str, audience: str | None) -> str:
    base = f"{topic}: rahasia yang jarang dibahas"
    if audience:
        base = f"{topic} untuk {audience}: rahasia yang jarang dibahas"
    # ensure 6-16 words
    words = base.split()
    if len(words) < 6:
        base += " yang wajib kamu tahu sekarang"
    elif len(words) > 16:
        base = " ".join(words[:16])
    return base


def make_title(topic: str, keywords: List[str]) -> str:
    kw = keywords[0] if keywords else topic.split()[0]
    return f"{kw.capitalize()}: {topic} | Panduan Lengkap"


def choose_angle(format_hint: str, topic: str) -> str:
    mapping = {
        "tutorial": f"Tutorial langkah-demi-langkah: {topic} dari nol sampai jadi",
        "listicle": f"Daftar 7 langkah/ide untuk {topic} beserta contoh praktis",
        "study": f"Studi kasus nyata menerapkan {topic} dan hasilnya",
        "review": f"Review tools/strategi untuk {topic} beserta cara pakainya",
    }
    return mapping.get(format_hint.lower(), f"Kerangka eksekusi praktis untuk {topic} (hook > value > CTA)")


def make_cta(audience: str | None) -> str:
    base = "Subscribe untuk tips tiap minggu dan tinggalkan komentar pertanyaanmu!"
    if audience:
        base = f"Subscribe untuk {audience} tips mingguan, like & komentar topik selanjutnya!"
    return base


def make_description(topic: str, keywords: List[str]) -> str:
    core = f"Bahas {topic} dengan contoh praktis dan langkah yang bisa langsung dipakai."
    if keywords:
        core += f" Kata kunci: {', '.join(keywords[:3])}."
    # 80–220 chars
    if len(core) < 80:
        core += " Tonton sampai akhir untuk rangkuman dan template gratis."
    return core[:220]


def evaluate(criteria_input: Dict[str, Any]) -> Dict[str, Any]:
    # Compute boolean flags according to provided rules
    hook_words = len(criteria_input.get("hook", "").split())
    title = criteria_input.get("seo_title", "")
    keywords = criteria_input.get("keywords", [])
    angle = criteria_input.get("angle", "")
    cta = criteria_input.get("cta", "")
    hashtags = criteria_input.get("hashtags", [])
    description = criteria_input.get("description", "")
    post_time = criteria_input.get("post_time", "")

    checks = {
        "hook_6_16_kata": 6 <= hook_words <= 16,
        "judul_mengandung_kata_kunci": any(k.lower() in title.lower() for k in keywords) if keywords else True,
        "angle_spesifik": any(word in angle.lower() for word in ["langkah", "studi", "review", "kerangka", "daftar"]),
        "cta_jelas": any(x in cta.lower() for x in ["subscribe", "ikuti", "simpan", "komentar", "like"]),
        "hashtag_3_10": 3 <= len(hashtags) <= 10,
        "deskripsi_80_220": 80 <= len(description) <= 220,
        "ada_rekomendasi_jam": bool(post_time),
    }
    score = int(round(sum(1 for v in checks.values() if v) / len(checks) * 100))
    return {"score": score, "criteria": checks}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    seo_title = make_title(req.topic, req.keywords)
    hook = make_hook(req.topic, req.audience)
    angle = choose_angle(req.platform, req.topic) if req.platform in ["tutorial", "listicle", "study", "review"] else choose_angle("tutorial", req.topic)
    cta = make_cta(req.audience)
    hashtags = build_hashtags(req.keywords, req.niche)
    post_time = pick_best_time(req.region, req.platform)
    description = make_description(req.topic, req.keywords)

    result: Dict[str, Any] = {
        "topic": req.topic,
        "keywords": req.keywords,
        "niche": req.niche,
        "audience": req.audience,
        "format": req.platform,
        "platform": "youtube",
        "region": req.region,
        "seo_title": seo_title,
        "hook": hook,
        "angle": angle,
        "cta": cta,
        "description": description,
        "hashtags": hashtags,
        "post_time": post_time,
    }

    scored = evaluate({**result})
    result.update(scored)

    # Persist
    try:
        create_document("analysis", Analysis(**result))
    except Exception:
        pass

    return result


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    from database import db
    status = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            status["database"] = "✅ Available"
            status["database_url"] = "✅ Set"
            status["database_name"] = getattr(db, 'name', 'OK')
            status["connection_status"] = "Connected"
            try:
                status["collections"] = db.list_collection_names()[:10]
                status["database"] = "✅ Connected & Working"
            except Exception as e:
                status["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            status["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        status["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    status["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    status["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return status


# ---- Presets & Templates Endpoint ----

TIMEZONES_PRESET: List[Dict[str, Any]] = [
    {"code": "UTC-10", "examples": ["Hawaii"]},
    {"code": "UTC-9", "examples": ["Alaska"]},
    {"code": "UTC-8", "examples": ["US West", "Vancouver"]},
    {"code": "UTC-7", "examples": ["US MT", "Arizona"]},
    {"code": "UTC-6", "examples": ["Texas", "Mexico City"]},
    {"code": "UTC-5", "examples": ["New York", "Toronto", "Peru", "Colombia"]},
    {"code": "UTC-4", "examples": ["Caribbean", "Venezuela"]},
    {"code": "UTC-3", "examples": ["Brazil", "Argentina", "Uruguay"]},
    {"code": "UTC-1", "examples": ["Azores"]},
    {"code": "UTC±0", "examples": ["UK", "Portugal", "Ghana"]},
    {"code": "UTC+1", "examples": ["Spain", "France", "Germany", "Nigeria"]},
    {"code": "UTC+2", "examples": ["Italy", "Greece", "Egypt", "South Africa"]},
    {"code": "UTC+3", "examples": ["Turkey", "Saudi Arabia", "Kenya"]},
    {"code": "UTC+4", "examples": ["UAE", "Oman", "Azerbaijan"]},
    {"code": "UTC+5", "examples": ["Pakistan", "Uzbekistan"]},
    {"code": "UTC+5:30", "examples": ["India", "Sri Lanka"]},
    {"code": "UTC+6", "examples": ["Bangladesh", "Kazakhstan (E)"]},
    {"code": "UTC+7", "examples": ["Indonesia (WIB)", "Thailand", "Vietnam"]},
    {"code": "UTC+8", "examples": ["Malaysia", "Singapore", "China", "WITA"]},
    {"code": "UTC+9", "examples": ["Japan", "South Korea", "WIT"]},
    {"code": "UTC+9:30", "examples": ["Australia Central"]},
    {"code": "UTC+10", "examples": ["Australia East", "PNG"]},
    {"code": "UTC+12", "examples": ["New Zealand", "Fiji"]},
    {"code": "UTC+13", "examples": ["Samoa"]},
]

# Audience presets (45+ entries)
AUDIENCE_PRESETS: List[Dict[str, Any]] = [
    {"country": "Amerika Serikat", "language": "Inggris", "timezone": "UTC-5..-8", "platforms": ["YouTube", "Shorts", "TikTok"], "interests": ["how-to", "review", "tech", "finance", "lifestyle"], "purchasing_power": "Tinggi", "best_post_times": ["11:30-13:00", "18:00-21:00"], "cultural_notes": "Headline to the point, thumbnail kontras"},
    {"country": "Kanada", "language": "Inggris/Prancis", "timezone": "UTC-5..-8", "platforms": ["YouTube", "TikTok", "Instagram"], "interests": ["edukasi", "outdoor", "teknologi", "karier"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-21:00"], "cultural_notes": "Pertimbangkan EN/FR untuk Quebec"},
    {"country": "Meksiko", "language": "Spanyol", "timezone": "UTC-6..-7", "platforms": ["YouTube", "Facebook", "TikTok"], "interests": ["hiburan", "musik", "lifestyle hemat", "sepak bola"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Gaya hangat dan komunikatif"},
    {"country": "Brasil", "language": "Portugis", "timezone": "UTC-3", "platforms": ["YouTube", "Instagram", "TikTok"], "interests": ["musik", "sepak bola", "komedi", "DIY"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Enerjik, visual kuat"},
    {"country": "Argentina", "language": "Spanyol", "timezone": "UTC-3", "platforms": ["YouTube", "TikTok"], "interests": ["sepak bola", "opini", "edukasi singkat"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "20:00-22:00"], "cultural_notes": "Humor dan konteks lokal"},
    {"country": "Kolombia", "language": "Spanyol", "timezone": "UTC-5", "platforms": ["YouTube", "Facebook", "TikTok"], "interests": ["tutorial praktis", "bisnis kecil", "hiburan ringan"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Judul jelas, tanpa jargon"},
    {"country": "Peru", "language": "Spanyol", "timezone": "UTC-5", "platforms": ["YouTube", "Facebook", "TikTok"], "interests": ["tutorial", "edukasi", "hiburan"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Praktis dan relevan"},
    {"country": "Inggris", "language": "Inggris", "timezone": "UTC±0/UTC+1", "platforms": ["YouTube", "TikTok", "Instagram"], "interests": ["edukasi", "commentary", "tech", "finansial"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-21:00"], "cultural_notes": "Bukti/data singkat menaikkan trust"},
    {"country": "Irlandia", "language": "Inggris/Irlandia", "timezone": "UTC±0", "platforms": ["YouTube", "TikTok"], "interests": ["edukasi", "karier", "finansial"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-21:00"], "cultural_notes": "Nada ramah"},
    {"country": "Jerman", "language": "Jerman", "timezone": "UTC+1", "platforms": ["YouTube", "Instagram"], "interests": ["engineering", "review", "produktif"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Struktur rapi, to the point"},
    {"country": "Prancis", "language": "Prancis", "timezone": "UTC+1", "platforms": ["YouTube", "Instagram"], "interests": ["lifestyle", "kuliner", "fashion"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Storytelling dan estetika"},
    {"country": "Spanyol", "language": "Spanyol", "timezone": "UTC+1", "platforms": ["YouTube", "TikTok"], "interests": ["hiburan", "sepak bola", "travel"], "purchasing_power": "Menengah-tinggi", "best_post_times": ["13:00-15:00", "20:00-22:00"], "cultural_notes": "Nada akrab"},
    {"country": "Italia", "language": "Italia", "timezone": "UTC+1", "platforms": ["YouTube", "Instagram"], "interests": ["kuliner", "design", "otomotif"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Tekankan kualitas & estetika"},
    {"country": "Belanda", "language": "Belanda/Inggris", "timezone": "UTC+1", "platforms": ["YouTube", "Instagram"], "interests": ["startup", "produktif", "sustainability"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Langsung"},
    {"country": "Swedia", "language": "Swedia/Inggris", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["tech", "minimalism", "karier"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Nada tenang, informatif"},
    {"country": "Norwegia", "language": "Norwegia", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["outdoor", "tech", "produktif"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Ringkas"},
    {"country": "Denmark", "language": "Denmark", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["design", "tech", "edukasi"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Sederhana & fungsional"},
    {"country": "Polandia", "language": "Polandia", "timezone": "UTC+1", "platforms": ["YouTube", "Facebook"], "interests": ["edukasi", "gaming", "DIY"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "18:00-21:00"], "cultural_notes": "Praktis"},
    {"country": "Turki", "language": "Turki", "timezone": "UTC+3", "platforms": ["YouTube", "Instagram"], "interests": ["bisnis kecil", "hiburan", "kuliner"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Sensitif budaya"},
    {"country": "Rusia (barat)", "language": "Rusia", "timezone": "UTC+3", "platforms": ["YouTube"], "interests": ["tech", "edukasi", "sains"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "18:00-21:00"], "cultural_notes": "Detail"},
    {"country": "Arab Saudi", "language": "Arab", "timezone": "UTC+3", "platforms": ["YouTube", "Snapchat", "TikTok"], "interests": ["religi", "otomotif", "keluarga"], "purchasing_power": "Tinggi", "best_post_times": ["13:00-15:00", "20:00-23:00"], "cultural_notes": "Hormati norma"},
    {"country": "UEA", "language": "Arab/Inggris", "timezone": "UTC+4", "platforms": ["YouTube", "Instagram"], "interests": ["luxury", "karier", "travel"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-22:00"], "cultural_notes": "Visual premium"},
    {"country": "Mesir", "language": "Arab", "timezone": "UTC+2", "platforms": ["YouTube", "Facebook"], "interests": ["berita", "edukasi praktis", "hiburan"], "purchasing_power": "Menengah", "best_post_times": ["13:00-15:00", "19:00-21:00"], "cultural_notes": "Narasi sederhana"},
    {"country": "Nigeria", "language": "Inggris/Pidgin", "timezone": "UTC+1", "platforms": ["YouTube", "TikTok"], "interests": ["musik", "komedi", "bisnis digital"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Enerjik"},
    {"country": "Afrika Selatan", "language": "Inggris + lokal", "timezone": "UTC+2", "platforms": ["YouTube", "TikTok"], "interests": ["travel", "otomotif", "DIY"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Konteks lokal"},
    {"country": "Kenya", "language": "Inggris/Swahili", "timezone": "UTC+3", "platforms": ["YouTube", "Facebook"], "interests": ["edukasi", "agribisnis", "tech mobile"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Solusi praktis"},
    {"country": "Ethiopia", "language": "Amharic/Inggris", "timezone": "UTC+3", "platforms": ["YouTube"], "interests": ["edukasi", "musik", "komedi"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Sederhana"},
    {"country": "India", "language": "Hindi/Inggris + regional", "timezone": "UTC+5:30", "platforms": ["YouTube", "Shorts"], "interests": ["exam prep", "coding", "finansial", "cricket"], "purchasing_power": "Beragam", "best_post_times": ["12:00-14:00", "19:00-22:00"], "cultural_notes": "Nilai praktis & harga"},
    {"country": "Pakistan", "language": "Urdu/Inggris", "timezone": "UTC+5", "platforms": ["YouTube", "TikTok"], "interests": ["edukasi", "religi", "hiburan"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Hormati norma"},
    {"country": "Bangladesh", "language": "Bengali", "timezone": "UTC+6", "platforms": ["YouTube", "Facebook"], "interests": ["tutorial", "mobile tech"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Manfaat langsung"},
    {"country": "Indonesia (WIB)", "language": "Indonesia", "timezone": "UTC+7", "platforms": ["YouTube", "TikTok", "Instagram"], "interests": ["gaming", "kuliner", "daily life", "tips kerja"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Ramah & to the point"},
    {"country": "Indonesia (WITA)", "language": "Indonesia", "timezone": "UTC+8", "platforms": ["YouTube", "TikTok", "Instagram"], "interests": ["gaming", "kuliner", "daily life", "tips kerja"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Ramah & to the point"},
    {"country": "Indonesia (WIT)", "language": "Indonesia", "timezone": "UTC+9", "platforms": ["YouTube", "TikTok", "Instagram"], "interests": ["gaming", "kuliner", "daily life", "tips kerja"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Ramah & to the point"},
    {"country": "Malaysia", "language": "Melayu/Inggris/Chinese", "timezone": "UTC+8", "platforms": ["YouTube", "TikTok"], "interests": ["kuliner", "review", "finansial pemula"], "purchasing_power": "Menengah-tinggi", "best_post_times": ["12:00-14:00", "20:00-22:00"], "cultural_notes": "Campuran BM/EN efektif"},
    {"country": "Singapura", "language": "Inggris/Chinese/Melayu/Tamil", "timezone": "UTC+8", "platforms": ["YouTube", "Instagram"], "interests": ["karier", "finansial", "tech"], "purchasing_power": "Sangat tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Efisien & kredibel"},
    {"country": "Thailand", "language": "Thai", "timezone": "UTC+7", "platforms": ["YouTube", "Facebook"], "interests": ["kuliner", "travel", "komedi"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Visual cerah"},
    {"country": "Vietnam", "language": "Vietnam", "timezone": "UTC+7", "platforms": ["YouTube", "TikTok"], "interests": ["produktif", "belajar", "kuliner"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Praktis & ringkas"},
    {"country": "Filipina", "language": "Filipino/Inggris", "timezone": "UTC+8", "platforms": ["YouTube", "Facebook"], "interests": ["musik", "vlog", "karier"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Ramah & personal"},
    {"country": "Jepang", "language": "Jepang", "timezone": "UTC+9", "platforms": ["YouTube"], "interests": ["DIY", "teknologi", "belajar"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Detail & kualitas"},
    {"country": "Korea Selatan", "language": "Korea", "timezone": "UTC+9", "platforms": ["YouTube", "Shorts"], "interests": ["K-culture", "tech", "kecantikan"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-22:00"], "cultural_notes": "Visual rapi & cepat"},
    {"country": "Tiongkok (urban)", "language": "Mandarin", "timezone": "UTC+8", "platforms": ["YouTube (internasional)"], "interests": ["tech", "edukasi", "bisnis"], "purchasing_power": "Tinggi (urban)", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Sensitivitas regulasi"},
    {"country": "Hong Kong", "language": "Cantonese/Inggris", "timezone": "UTC+8", "platforms": ["YouTube", "Instagram"], "interests": ["bisnis", "finansial", "tech"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Cepat & profesional"},
    {"country": "Taiwan", "language": "Mandarin", "timezone": "UTC+8", "platforms": ["YouTube"], "interests": ["tech", "edukasi", "gaming"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Detail"},
    {"country": "Australia Timur", "language": "Inggris", "timezone": "UTC+10", "platforms": ["YouTube"], "interests": ["outdoor", "keuangan pribadi", "karier"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Langsung"},
    {"country": "Australia Tengah", "language": "Inggris", "timezone": "UTC+9:30", "platforms": ["YouTube"], "interests": ["outdoor", "DIY", "karier"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Santai"},
    {"country": "Australia Barat", "language": "Inggris", "timezone": "UTC+8", "platforms": ["YouTube"], "interests": ["outdoor", "tech"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Straightforward"},
    {"country": "Selandia Baru", "language": "Inggris/Te Reo", "timezone": "UTC+12", "platforms": ["YouTube"], "interests": ["travel", "keluarga", "produktif"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Humanis, ringan"},
    {"country": "Portugal", "language": "Portugis", "timezone": "UTC±0", "platforms": ["YouTube"], "interests": ["travel", "kuliner", "lifestyle"], "purchasing_power": "Menengah-tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Ramah"},
    {"country": "Yunani", "language": "Yunani", "timezone": "UTC+2", "platforms": ["YouTube"], "interests": ["travel", "kuliner", "sejarah"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Story"},
    {"country": "Ceko", "language": "Ceko", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["gaming", "tech", "DIY"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "18:00-21:00"], "cultural_notes": "Praktis"},
    {"country": "Hungaria", "language": "Hungaria", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["edukasi", "tech"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Ringkas"},
    {"country": "Rumania", "language": "Rumania", "timezone": "UTC+2", "platforms": ["YouTube"], "interests": ["tutorial", "gaming"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Langsung"},
    {"country": "Ukraina", "language": "Ukraina/Rusia", "timezone": "UTC+2/+3", "platforms": ["YouTube"], "interests": ["edukasi", "tech"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "18:00-21:00"], "cultural_notes": "Informasi jelas"},
    {"country": "Belgia", "language": "Belanda/Prancis", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["edukasi", "kuliner", "tech"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Multibahasa"},
    {"country": "Swiss", "language": "DE/FR/IT", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["keuangan", "tech", "travel"], "purchasing_power": "Sangat tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Akurat"},
    {"country": "Austria", "language": "Jerman", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["edukasi", "musik", "tech"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Terstruktur"},
    {"country": "Finlandia", "language": "Finlandia/Swedia", "timezone": "UTC+2", "platforms": ["YouTube"], "interests": ["gaming", "tech", "edukasi"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "18:00-20:00"], "cultural_notes": "Ringkas"},
    {"country": "Maroko", "language": "Arab/Prancis", "timezone": "UTC±0", "platforms": ["YouTube"], "interests": ["kuliner", "travel", "edukasi"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Hangat"},
    {"country": "Aljazair", "language": "Arab/Prancis", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["edukasi", "otomotif"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Praktis"},
    {"country": "Tunisia", "language": "Arab/Prancis", "timezone": "UTC+1", "platforms": ["YouTube"], "interests": ["kuliner", "edukasi"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Friendly"},
    {"country": "Ghana", "language": "Inggris", "timezone": "UTC±0", "platforms": ["YouTube"], "interests": ["musik", "bisnis digital"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Relatable"},
    {"country": "Kenya", "language": "Inggris/Swahili", "timezone": "UTC+3", "platforms": ["YouTube"], "interests": ["edukasi", "agribisnis", "tech mobile"], "purchasing_power": "Menengah", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Solusi praktis"},
    {"country": "Israel", "language": "Ibrani/Inggris", "timezone": "UTC+2/+3", "platforms": ["YouTube"], "interests": ["tech", "startup", "edukasi"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-21:00"], "cultural_notes": "Data-driven"},
    {"country": "Qatar", "language": "Arab/Inggris", "timezone": "UTC+3", "platforms": ["YouTube", "Instagram"], "interests": ["luxury", "olahraga"], "purchasing_power": "Sangat tinggi", "best_post_times": ["12:00-14:00", "19:00-22:00"], "cultural_notes": "Premium"},
    {"country": "Oman", "language": "Arab", "timezone": "UTC+4", "platforms": ["YouTube"], "interests": ["travel", "keluarga"], "purchasing_power": "Tinggi", "best_post_times": ["12:00-14:00", "19:00-22:00"], "cultural_notes": "Hangat"},
]

# Creator analysis template and a few presets
CREATOR_TEMPLATE: Dict[str, Any] = {
    "identity": {
        "handle": "@NamaYouTuber",
        "niche": "",
        "persona": "",
        "audience_core": "(negara/zona waktu, bahasa)",
    },
    "content_pattern": {
        "format": "talking head / b-roll / screencast / vlog",
        "duration": "short 30-60s / long 8-12m",
        "hook": "pertanyaan berani / angka / sebelum-sesudah",
        "angle": "list / studi kasus 30-hari / before-after / checklist",
        "cta": "subscribe/like/komentar",
    },
    "title_thumbnail": {
        "title_formula": "angka + manfaat + batas waktu",
        "keywords_common": ["contoh", "kata", "kunci"],
        "thumbnail_style": "close-up + teks 2-4 kata + warna kontras",
    },
    "schedule": {
        "days_hours": "hari & jam unggah lokal",
        "frequency": "x video/minggu",
        "top_videos_theme": "tema bersama dari 3-5 video teratas",
    },
    "gaps_opportunities": {
        "missing_topics": [],
        "format_variations": [],
        "collab_candidates": [],
    },
    "output_structure": {
        "seo_title": "",
        "hook": "",
        "angle": "",
        "cta": "",
        "description": "",
        "hashtags": [],
        "post_time": "",
    },
}

CREATOR_PRESETS: List[Dict[str, Any]] = [
    {"handle": "@AliAbdaal", "niche": "produktif/edukasi", "persona": "mentor santai", "patterns": {"format": "talking head + b-roll", "title": "angka + manfaat jelas", "cta": "subscribe mingguan"}},
    {"handle": "@MarquesBrownlee", "niche": "tech review", "persona": "analis tenang", "patterns": {"format": "review sinematik", "title": "model + tahun + verdict", "cta": "komentar pendapat"}},
    {"handle": "@MrBeast", "niche": "entertainment/mega challenge", "persona": "high energy", "patterns": {"format": "challenge besar", "title": "premis ekstrem", "cta": "like/subscribe awal"}},
    {"handle": "@JoshuaWeissman", "niche": "kuliner", "persona": "chef edukatif", "patterns": {"format": "cooking + humor", "title": "resep + benefit", "cta": "coba dan komentar"}},
    {"handle": "@Fireship", "niche": "coding/tech", "persona": "cepat & lucu", "patterns": {"format": "screencast cepat", "title": "buzzword + hot take", "cta": "subscribe singkat"}},
]

@app.get("/api/presets")
def get_presets() -> Dict[str, Any]:
    return {
        "timezones": TIMEZONES_PRESET,
        "audiences": AUDIENCE_PRESETS,
        "creator_template": CREATOR_TEMPLATE,
        "creator_presets": CREATOR_PRESETS,
        "notes": "Semua nilai bersifat heuristik. Sesuaikan dengan data analitik channel Anda.",
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
