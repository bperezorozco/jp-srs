# jp-srs

App personal de vocabulario JLPT con oraciones generadas por LLM y
repetición espaciada (FSRS). Sesgo de contenido hacia vocabulario
corporativo y de seguros. Nivel JLPT (N1-N5) e idioma de traducción
(es/en/it/fr) son seleccionables por el usuario, no fijos.

## Arquitectura

- Backend: FastAPI, en `src/main.py`
- DB: SQLite, path via `DB_PATH` env var (Railway Volume en prod, montado en `/data`)
- Generación de contenido: backend dual, elegido automáticamente por
  presencia de `ANTHROPIC_API_KEY`:
  - Sin la key seteada → Agent SDK, corre sobre sesión de Claude Max local, gratis
  - Con la key seteada → SDK `anthropic` normal, usado en producción (Railway)
  - NUNCA duplicar lógica de prompt/parseo entre las dos ramas; solo
    la función `generate()` cambia de implementación
- `claude-agent-sdk` vive en `[dependency-groups] dev`, nunca en
  dependencies normales — no se necesita en producción
- `pyproject.toml` tiene `[tool.uv] package = false` — esto es una app,
  no un paquete instalable, no tocar el build-system ni agregar [project.scripts]

## Formato de generación (crítico)

- El modelo SIEMPRE debe responder JSON estricto: `sentence`, `furigana`,
  `translation`, `note`. Nunca texto libre.
- Motivo: sin JSON forzado, el modelo divaga, repite la oración con
  variaciones, y mezcla markdown con el contenido — inutilizable para
  guardar o mostrar en tarjetas.
- `parse_response()` tolera que el modelo envuelva la salida en
```json ``` por hábito, pero el prompt pide explícitamente que no lo haga.
- Todo output se cachea en SQLite antes de mostrarse; nunca regenerar
  una palabra ya generada.
- `/sentence` acepta `level` (N1-N5, default N5) y `language` (es/en/it/fr,
  default es) como query params. `build_system(level)` restringe el
  vocabulario/gramática al nivel pedido (o más fácil); `build_prompt(word,
  language)` pide la traducción en el idioma pedido. Valores inválidos
  devuelven 400, nunca se le pasan al modelo sin validar.

## Seguridad

- Endpoint `/sentence` protegido por header `X-App-Secret`, comparado
  contra env var `APP_SECRET`. Esto es un candado básico contra tráfico
  automatizado, NO autenticación real de usuarios — suficiente para
  proyecto personal de un solo usuario, no escalar a multi-usuario sin
  repensar esto.
- `/` (root/healthcheck) queda sin auth a propósito.
- Pendiente: rate limiting cuando exista frontend real.

## Deploy

- Railway, conectado a GitHub, deploy automático en push a `main`
- Start command en `railway.json`, no en el dashboard:
  `uv run uvicorn src.main:app --host 0.0.0.0 --port $PORT`
- Variables requeridas en Railway: `ANTHROPIC_API_KEY`, `APP_SECRET`, `DB_PATH`
- Volume montado en `/data` para persistencia de SQLite (el filesystem
  del contenedor es efímero entre deploys)

## Modelo por defecto

- Sonnet, no Opus, salvo tarea que lo justifique explícitamente
  (ej. evaluar calidad de nivel N2, no generación simple)

## Estilo de código

- Nombres de variables/funciones en inglés, comments en español/inglés
  según convenga
- Sin over-engineering: es una app personal de un solo usuario, no un
  producto para terceros. Preferir simple y funcional sobre "correcto"
  en abstracto.
- Todo texto en inglés (UI, labels, contenido generado cuando `language=en`)
  debe usar inglés británico (ej. "personalised", no "personalized").
- Todo texto en español (UI, labels, contenido generado cuando `language=es`)
  debe usar español mexicano.

## Estado actual (actualizar a medida que avance)

- [x] Dev environment, git, deploy en Railway
- [x] Backend dual funcionando
- [x] Auth básica por secreto
- [x] Generación en JSON estricto
- [x] Frontend mínimo (input palabra → oración, `src/static/index.html`),
      con selector de nivel JLPT e idioma de traducción
- [ ] Modelo de datos (words, cards, reviews) en SQLite
- [ ] Loop FSRS completo
