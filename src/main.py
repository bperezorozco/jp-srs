import os
import json
import httpx
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# BACKEND SELECTION — decided automatically based on environment
# ============================================================
# ANTHROPIC_API_KEY not set  -> Agent SDK, uses local Claude Max session (free, dev only)
# ANTHROPIC_API_KEY set      -> normal anthropic SDK (production, Railway)
#
# See CLAUDE.md for full reasoning. Never duplicate prompt/parsing logic
# between the two branches — only generate() changes implementation.

USE_API_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))

if USE_API_KEY:
    from anthropic import Anthropic
    _client = Anthropic()
    # Exposed so eval runs can record which model produced their outputs.
    MODEL = "claude-sonnet-4-6"

    async def generate(prompt: str, system: str) -> str:
        msg = _client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
else:
    from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

    # Whatever model the local Claude Code session is running; not pinned here.
    MODEL = "claude-code-session"

    async def generate(prompt: str, system: str) -> str:
        options = ClaudeAgentOptions(system_prompt=system, max_turns=1, allowed_tools=[])
        out = []
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        out.append(block.text)
        return "\n".join(out)

# ============================================================


app = FastAPI()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

JLPT_LEVELS = {"N1", "N2", "N3", "N4", "N5"}
LANGUAGES = {"es": "español", "en": "inglés", "it": "italiano", "fr": "francés"}

def build_system(level: str) -> str:
    return (
        f"Eres un profesor de japonés especializado en preparación JLPT {level}. "
        f"Generas oraciones de ejemplo usando SOLO vocabulario y gramática "
        f"de nivel {level} o más fácil (JLPT va de N5, el nivel más fácil, "
        f"a N1, el más difícil), nunca vocabulario de un nivel más difícil que {level}. "
        "Respondes ÚNICAMENTE con un objeto JSON válido, sin texto antes ni "
        "después, sin markdown, sin backticks."
    )

def build_prompt(word: str, language: str, is_kanji: bool = False) -> str:
    lang_name = LANGUAGES[language]
    if is_kanji:
        target = (
            f"Kanji objetivo: {word}\n\n"
            "Genera una oración de ejemplo usando una palabra que contenga "
            "este kanji (el kanji no tiene que funcionar como palabra por "
            "sí solo)."
        )
    else:
        target = (
            f"Palabra objetivo: {word}\n\n"
            "Genera una oración de ejemplo usando esta palabra."
        )
    return (
        f"{target} "
        "Devuelve exactamente este JSON, sin nada más:\n"
        "{\n"
        '  "sentence": "oración completa en japonés con kanji",\n'
        '  "furigana": "misma oración con lectura en hiragana",\n'
        f'  "translation": "traducción al {lang_name}",\n'
        '  "note": "nota breve sobre uso o matiz gramatical, o null si no aplica"\n'
        "}"
    )

def parse_response(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


APP_SECRET = os.getenv("APP_SECRET")

def check_auth(x_app_secret: str = Header(None)):
    if not APP_SECRET or x_app_secret != APP_SECRET:
        raise HTTPException(status_code=401)


WANIKANI_API_KEY = os.getenv("WANIKANI_API_KEY")
WANIKANI_HEADERS = {"Authorization": f"Bearer {WANIKANI_API_KEY}"}

# Approximate mapping from WaniKani level (1-60) to JLPT level.
# WaniKani does not expose JLPT levels directly; this is a heuristic
# based on community consensus, not an official source.
def wanikani_level_to_jlpt(level: int) -> str:
    if level <= 10:
        return "N5"
    if level <= 20:
        return "N4"
    if level <= 33:
        return "N3"
    if level <= 44:
        return "N2"
    return "N1"

async def _paginate(client: httpx.AsyncClient, url: str) -> list[dict]:
    items = []
    while url:
        resp = await client.get(url, headers=WANIKANI_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        items.extend(data["data"])
        url = data["pages"]["next_url"]
    return items

WANIKANI_VOCAB_TYPES = "vocabulary,kana_vocabulary"
WANIKANI_KANJI_TYPES = "kanji"

# Subjects (words/kanji + WK level) rarely change, so they are cached in
# memory, keyed by type. Assignments (SRS progress) change with every
# review the user does, so those are fetched fresh on each request.
_wanikani_subjects_cache: dict[str, list[dict]] = {}

async def fetch_wanikani_subjects(client: httpx.AsyncClient, types: str) -> list[dict]:
    if types in _wanikani_subjects_cache:
        return _wanikani_subjects_cache[types]

    raw = await _paginate(client, f"https://api.wanikani.com/v2/subjects?types={types}")
    subjects = [
        {"id": s["id"], "word": s["data"]["characters"], "level": s["data"]["level"]}
        for s in raw
        if s["data"]["characters"]
    ]
    _wanikani_subjects_cache[types] = subjects
    return subjects

async def fetch_wanikani_srs_stages(client: httpx.AsyncClient, types: str) -> dict[int, int]:
    raw = await _paginate(client, f"https://api.wanikani.com/v2/assignments?subject_types={types}")
    return {a["data"]["subject_id"]: a["data"]["srs_stage"] for a in raw}

async def fetch_wanikani_items(types: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        subjects = await fetch_wanikani_subjects(client, types)
        srs_stages = await fetch_wanikani_srs_stages(client, types)

    return [
        {
            "word": s["word"],
            "jlpt_level": wanikani_level_to_jlpt(s["level"]),
            # -1 = not assigned yet (level not reached in WaniKani)
            "srs_stage": srs_stages.get(s["id"], -1),
        }
        for s in subjects
    ]


@app.get("/")
def root():
    return {"status": "ok", "backend": "api_key" if USE_API_KEY else "claude_code"}

@app.get("/app")
def serve_app():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/wanikani")
def serve_wanikani():
    return FileResponse(os.path.join(STATIC_DIR, "wanikani.html"))

@app.get("/wanikani-kanji")
def serve_wanikani_kanji():
    return FileResponse(os.path.join(STATIC_DIR, "wanikani-kanji.html"))

@app.get("/wanikani/words", dependencies=[Depends(check_auth)])
async def wanikani_words():
    if not WANIKANI_API_KEY:
        raise HTTPException(status_code=404, detail="No hay API key de WaniKani configurada")
    words = await fetch_wanikani_items(WANIKANI_VOCAB_TYPES)
    return {"words": words}

@app.get("/wanikani/kanji", dependencies=[Depends(check_auth)])
async def wanikani_kanji():
    if not WANIKANI_API_KEY:
        raise HTTPException(status_code=404, detail="No hay API key de WaniKani configurada")
    words = await fetch_wanikani_items(WANIKANI_KANJI_TYPES)
    return {"words": words}

@app.get("/sentence", dependencies=[Depends(check_auth)])
async def sentence(word: str = "契約", level: str = "N5", language: str = "es", is_kanji: bool = False):
    if level not in JLPT_LEVELS:
        raise HTTPException(status_code=400, detail=f"level inválido, debe ser uno de {sorted(JLPT_LEVELS)}")
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"language inválido, debe ser uno de {sorted(LANGUAGES)}")
    raw = await generate(build_prompt(word, language, is_kanji), build_system(level))
    try:
        return parse_response(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="El modelo no devolvió JSON válido")
