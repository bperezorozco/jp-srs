import os
import json
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

    async def generate(prompt: str, system: str) -> str:
        msg = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
else:
    from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

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

def build_prompt(word: str, language: str) -> str:
    lang_name = LANGUAGES[language]
    return (
        f"Palabra objetivo: {word}\n\n"
        "Genera una oración de ejemplo usando esta palabra. "
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


@app.get("/")
def root():
    return {"status": "ok", "backend": "api_key" if USE_API_KEY else "claude_code"}

@app.get("/app")
def serve_app():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/sentence", dependencies=[Depends(check_auth)])
async def sentence(word: str = "契約", level: str = "N5", language: str = "es"):
    if level not in JLPT_LEVELS:
        raise HTTPException(status_code=400, detail=f"level inválido, debe ser uno de {sorted(JLPT_LEVELS)}")
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"language inválido, debe ser uno de {sorted(LANGUAGES)}")
    raw = await generate(build_prompt(word, language), build_system(level))
    try:
        return parse_response(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="El modelo no devolvió JSON válido")
