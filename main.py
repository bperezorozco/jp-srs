from fastapi import FastAPI
from claude_agent_sdk import (
    query, ClaudeAgentOptions, AssistantMessage, TextBlock
)

app = FastAPI()

SYSTEM = (
    "Eres un profesor de japonés especializado en preparación JLPT N2. "
    "Generas input comprensible: una oración por vez, contexto empresarial "
    "y de seguros. Respondes solo con el contenido pedido, sin preámbulo."
)

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/sentence")
async def sentence(word: str = "契約"):
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM,
        max_turns=1,
        allowed_tools=[],
    )
    prompt = (
        f"Palabra objetivo: 「{word}」\n"
        "Genera una oración nivel N2 que la use naturalmente.\n"
        "Formato:\n1. Oración\n2. Lectura en hiragana\n"
        "3. Traducción al español\n4. Nota breve sobre el uso"
    )
    out = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    out.append(block.text)
    return {"output": "\n".join(out)}

