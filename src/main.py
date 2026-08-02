import os
from fastapi import FastAPI

app = FastAPI()

SYSTEM = (
    "Eres un profesor de japonés especializado en preparación JLPT N2. "
    "Generas input comprensible: una oración por vez, contexto empresarial "
    "y de seguros. Respondes solo con el contenido pedido, sin preámbulo."
)

def build_prompt(word: str) -> str:
    return (
        f"Palabra objetivo: 「{word}」\n"
        "Genera una oración nivel N2 que la use naturalmente.\n"
        "Formato:\n1. Oración\n2. Lectura en hiragana\n"
        "3. Traducción al español\n4. Nota breve sobre el uso"
    )

USE_API_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))

if USE_API_KEY:
    from anthropic import Anthropic
    _client = Anthropic()

    async def generate(prompt: str) -> str:
        msg = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
else:
    from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

    async def generate(prompt: str) -> str:
        options = ClaudeAgentOptions(system_prompt=SYSTEM, max_turns=1, allowed_tools=[])
        out = []
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        out.append(block.text)
        return "\n".join(out)


@app.get("/")
def root():
    return {"status": "ok", "backend": "api_key" if USE_API_KEY else "claude_code"}

@app.get("/sentence")
async def sentence(word: str = "契約"):
    return {"output": await generate(build_prompt(word))}

