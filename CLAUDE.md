# jp-srs

App personal de vocabulario JLPT con oraciones generadas por LLM y
repetición espaciada (FSRS). Vocabulario de propósito general, sin
sesgo temático. Nivel JLPT (N1-N5) e idioma de traducción
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
- BUG CONOCIDO (detectado por el eval, ítem `a01`): si el modelo antepone
  prosa antes del JSON, `parse_response()` truena y `/sentence` devuelve
  502. Pasa cuando el input tiene restricciones en conflicto (palabra N1
  pedida en nivel N5): el modelo explica la contradicción antes de
  responder. Sin arreglar todavía a propósito — se arregla y se vuelve a
  correr el eval con tag nuevo, para tener la comparación baseline vs fix.
- Todo output se cachea en SQLite antes de mostrarse; nunca regenerar
  una palabra ya generada.
- `/sentence` acepta `level` (N1-N5, default N5) y `language` (es/en/it/fr,
  default es) como query params. `build_system(level)` restringe el
  vocabulario/gramática al nivel pedido (o más fácil); `build_prompt(word,
  language)` pide la traducción en el idioma pedido. Valores inválidos
  devuelven 400, nunca se le pasan al modelo sin validar.
- `/sentence` también acepta `is_kanji` (bool, default False). Con
  `is_kanji=True`, `build_prompt()` pide "genera una oración usando una
  palabra que contenga este kanji" en vez de "usa esta palabra" — muchos
  kanji sueltos no funcionan como palabra independiente (ej. 語 necesita
  日本語, 語る, etc.), pedirle al modelo que los use como si fueran
  vocabulario produce resultados forzados. Decisión: un flag explícito
  que cambia el *framing* del prompt, en vez de meter instrucciones
  como texto libre dentro del campo `word` — mantiene `word` limpio
  (importa para cuando se cachee en SQLite) y es más fácil de mantener.

## Integración WaniKani

- Dos páginas gemelas, misma funcionalidad, distinto tipo de subject:
  - `/wanikani` sirve `src/static/wanikani.html` (vocabulario)
  - `/wanikani-kanji` sirve `src/static/wanikani-kanji.html` (kanji)
  - Ambas: todo el contenido de WaniKani (todos los niveles, no solo
    los desbloqueados), agrupado en secciones colapsables por nivel
    JLPT (N5 a N1, colapsadas por default), cada botón coloreado según
    el SRS stage en WaniKani (escala de azules, de "sin asignar" hasta
    "burned"), con filtro de búsqueda. Click en un item te manda a
    `/app?word=...&level=...&lang=...&autorun=1` (la página de kanji
    además manda `&is_kanji=1`), que precarga la palabra/kanji,
    selecciona el nivel JLPT correspondiente, y genera la oración
    automáticamente.
- `/wanikani/words` y `/wanikani/kanji` (ambos protegidos por
  `X-App-Secret`, igual que `/sentence`) usan `WANIKANI_API_KEY` para
  pegarle a la API v2 de WaniKani: `GET /subjects?types=...` para el
  contenido + nivel WK (`vocabulary,kana_vocabulary` para uno,
  `kanji` para el otro — ver `WANIKANI_VOCAB_TYPES`/`WANIKANI_KANJI_TYPES`),
  y `GET /assignments?subject_types=...` para el SRS stage actual de
  cada item. Si la env var no está seteada, ambos devuelven 404 y el
  frontend correspondiente muestra "No hay API key" en el idioma
  seleccionado.
- `wanikani_level_to_jlpt()` mapea nivel WaniKani (1-60) a nivel JLPT
  (N5-N1) con una heurística aproximada (no oficial, WaniKani no expone
  JLPT directamente): 1-10→N5, 11-20→N4, 21-33→N3, 34-44→N2, 45-60→N1.
- Los subjects (contenido + nivel WK) se cachean en memoria
  (`_wanikani_subjects_cache`, por tipo). Los assignments (SRS stage)
  se piden frescos en cada request porque cambian con cada review —
  así los colores reflejan tu progreso real.
- El idioma seleccionado se persiste en `localStorage` (`appLanguage`)
  además del query param `?lang=`, para que se mantenga al navegar
  entre `/app`, `/wanikani` y `/wanikani-kanji`.

## Evals

Suite en `evals/` para evaluar la generación de oraciones. Ver
`evals/README.md` para el spec completo y los criterios de ship.

- Tres capas de grading, de barata a cara: checks determinísticos
  (`rubric.automatic_checks`), etiquetado humano (`label.py`), y
  LLM-as-judge (`judge.py`, pendiente). REGLA: nada que se pueda
  decidir con código va a un juez LLM, y el juez no se usa hasta
  haber medido su acuerdo (Cohen's kappa) contra etiquetas humanas.
- `run.py` importa `build_system`/`build_prompt`/`parse_response`/
  `generate` de `src/main.py`. NUNCA duplicar esa lógica en `evals/`:
  si divergen, el eval mide un sistema que no existe. `src/main.py`
  expone `MODEL` solo para que las corridas registren procedencia.
- `dataset.py` es un golden set CONGELADO (n=20, `DATASET_VERSION`).
  No se jala de la API de WaniKani en tiempo de corrida — si el
  dataset cambia entre corridas, los números dejan de ser comparables.
  Si le agregas ítems, sube `DATASET_VERSION`.
- Las corridas son artefactos inmutables: `run.py` se niega a
  sobrescribir un tag existente. Todo va a `evals/results/`, versionado
  en git, más un `.meta.json` con modelo, fingerprint del prompt y
  versión del dataset.
- Criterios binarios, nunca escalas 1-5 (no calibran ni en humanos ni
  en modelos). Cuatro respuestas posibles: sí, no, `u` (entendí y aun
  así no me decido → el criterio está mal escrito), `x` (arriba de mi
  nivel de japonés → límite de cobertura). `u` y `x` nunca entran a una
  tasa ni al kappa y se reportan por separado: significan cosas
  distintas y confundirlas manda a reescribir una rúbrica que estaba bien.
- El anotador no es nivel N1. Adivinar en vez de marcar `x` no produce
  ruido, produce sesgo sistemático — y un juez validado contra esas
  etiquetas reproduce los errores y reporta acuerdo alto.
- `label.py` NO le muestra los checks automáticos al anotador: ver el
  veredicto de la máquina lo ancla, y contamina el acuerdo que se mide
  después.
- `report.py` siempre reporta intervalos de Wilson. Con n=20 el margen
  es de ~±20pp: casi cualquier "mejora" a este tamaño de muestra es
  ruido. Las métricas por slice (4-5 ítems) son cualitativas, nunca se
  citan como porcentaje.

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
- Variable opcional: `WANIKANI_API_KEY` (habilita `/wanikani/words` y
  `/wanikani/kanji`; sin ella, ambas páginas de WaniKani muestran "no
  hay API key")
- Volume montado en `/data` para persistencia de SQLite (el filesystem
  del contenedor es efímero entre deploys)

## Modelo por defecto

- Sonnet, no Opus, salvo tarea que lo justifique explícitamente
  (ej. evaluar calidad de nivel N2, no generación simple)

## Estilo de código

- Nombres de variables/funciones en inglés. TODO comentario, docstring
  y documentación de código va en inglés (británico), sin excepción.
  El español se reserva para texto de cara al usuario (UI, labels,
  contenido generado cuando `language=es`) y para este CLAUDE.md.
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
- [x] Páginas de vocabulario y kanji de WaniKani (`src/static/wanikani.html`
      + `wanikani-kanji.html`, `/wanikani/words` + `/wanikani/kanji`),
      navegación cargando la palabra/kanji en `/app`
- [x] Suite de evals, capas 1 y 2 (`evals/`): golden set congelado,
      harness con procedencia, checks automáticos, CLI de etiquetado,
      reporte con intervalos de Wilson. Corrida `baseline` hecha.
- [ ] Etiquetado humano de la corrida `baseline` (20 ítems)
- [ ] Arreglar `parse_response()` ante prosa antes del JSON + correr
      eval con tag nuevo para comparar contra `baseline`
- [ ] Capa 3: `judge.py` (LLM-as-judge) + `agreement.py` (Cohen's kappa
      contra las etiquetas humanas)
- [ ] Modelo de datos (words, cards, reviews) en SQLite
- [ ] Loop FSRS completo
