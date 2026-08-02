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

## Integración WaniKani

- `/wanikani` sirve `src/static/wanikani.html`, una segunda página con
  todo el vocabulario de WaniKani (todos los niveles, no solo los
  desbloqueados), agrupado por sección de nivel JLPT (N5 a N1) y con
  cada botón coloreado según el SRS stage en WaniKani (escala de azules,
  de "sin asignar" hasta "burned"). Click en una palabra te manda a
  `/app?word=...&level=...&lang=...&autorun=1`, que precarga la palabra,
  selecciona el nivel JLPT correspondiente, y genera la oración
  automáticamente.
- `/wanikani/words` (protegido por `X-App-Secret`, igual que `/sentence`)
  usa `WANIKANI_API_KEY` para pegarle a la API v2 de WaniKani: `GET
  /subjects?types=vocabulary` para las palabras + nivel WK, y `GET
  /assignments?subject_types=vocabulary` para el SRS stage actual de
  cada una. Si la env var no está seteada, devuelve 404 y el frontend
  muestra "No hay API key" en el idioma seleccionado.
- `wanikani_level_to_jlpt()` mapea nivel WaniKani (1-60) a nivel JLPT
  (N5-N1) con una heurística aproximada (no oficial, WaniKani no expone
  JLPT directamente): 1-10→N5, 11-20→N4, 21-33→N3, 34-44→N2, 45-60→N1.
- Los subjects (palabras + nivel WK) se cachean en memoria
  (`_wanikani_subjects_cache`) porque cambian muy poco. Los assignments
  (SRS stage) se piden frescos en cada request porque cambian con cada
  review — así los colores en `/wanikani` reflejan tu progreso real.
- El idioma seleccionado se persiste en `localStorage` (`appLanguage`)
  además del query param `?lang=`, para que se mantenga al navegar
  entre `/app` y `/wanikani`.

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
- Variable opcional: `WANIKANI_API_KEY` (habilita `/wanikani/words`; sin
  ella, la página de WaniKani muestra "no hay API key")
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
- [x] Página de vocabulario WaniKani (`src/static/wanikani.html`,
      `/wanikani/words`), navegación cargando la palabra en `/app`
- [ ] Modelo de datos (words, cards, reviews) en SQLite
- [ ] Loop FSRS completo
