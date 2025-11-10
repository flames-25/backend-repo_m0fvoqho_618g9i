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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
