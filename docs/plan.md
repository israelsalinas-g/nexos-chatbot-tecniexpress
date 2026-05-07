# Plan: Tecni Express Telegram Chatbot

## Context

Tecni Express es una empresa que vende repuestos para lavadoras y secadoras. Actualmente los clientes hacen cotizaciones por Telegram de forma manual (el agente busca en Supabase, PDFs y sitios web). Este proyecto automatiza ese proceso con un chatbot que:

1. Recibe solicitudes en 3 formatos: texto descriptivo, foto del repuesto, foto de etiqueta del equipo
2. Analiza imágenes con Claude Vision para identificar el repuesto o leer la etiqueta
3. Busca en la base de datos de productos en Supabase (proyecto existente `nexos-tecni-express`)
4. Busca en manuales PDF indexados desde Google Drive como fallback
5. Responde con cotización (precio en Lempiras + disponibilidad) — **solo cotiza, no crea pedidos**

---

## Architecture

**Stack**: Python 3.12 + FastAPI + supabase-py + anthropic SDK  
**Deployment**: Railway (recomendado, sin timeout) o Vercel Pro (60s limit)  
**Model**: `claude-sonnet-4-6` para vision + parsing de texto  
**Telegram**: Webhooks (POST por cada mensaje)  
**Supabase**: Misma instancia de `nexos-tecni-express`, service role key

### Request Flow
```
Cliente → Telegram → POST /webhook (Railway/Vercel)
    ↓
FastAPI BackgroundTasks (responde 200 inmediatamente)
    ↓
1. Valida secret header
2. Detecta tipo de mensaje (texto / foto)
3. Si foto → descarga → Claude Vision → extrae {brand, model, part}
   Si texto → Claude parse → extrae {brand, model, part}
4. Busca en Supabase (RPC FTS + compatibility matrix)
5. Si sin resultados → busca en manual_index (PDFs indexados)
6. Formatea respuesta HTML → envía mensaje Telegram
```

---

## File Structure

```
nexos-chatbot-tecniexpress/
├── app/
│   └── main.py                  # FastAPI app, /webhook endpoint
├── bot/
│   ├── config.py                # Env vars (falla en import si faltan)
│   ├── handlers/
│   │   ├── text_handler.py      # Mensajes de texto
│   │   ├── photo_handler.py     # Imágenes (repuesto o etiqueta)
│   │   └── command_handler.py   # /start, /help
│   ├── services/
│   │   ├── claude_service.py    # Vision + query parsing
│   │   ├── supabase_service.py  # Búsquedas en BD
│   │   ├── pdf_service.py       # Búsqueda en manual_index
│   │   └── telegram_service.py  # Envío de msgs, descarga de fotos
│   └── utils/
│       ├── formatters.py        # Formato de cotización (HTML Telegram)
│       └── prompts.py           # System prompts para Claude
├── scripts/
│   └── index_pdfs.py            # Indexar PDFs de Drive → Supabase
├── requirements.txt
├── railway.toml                 # Config Railway deployment
├── vercel.json                  # Config Vercel (fallback)
└── .env.example
```

---

## New Supabase Tables

### `telegram_sessions`
```sql
CREATE TABLE public.telegram_sessions (
  chat_id    bigint PRIMARY KEY,
  state      text NOT NULL DEFAULT 'idle'
             CHECK (state IN ('idle','awaiting_brand','awaiting_model','awaiting_part')),
  context    jsonb NOT NULL DEFAULT '{}',
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- context example: {"last_query":"perilla","brand":"Samsung","model":null}
```

### `manual_index`
```sql
CREATE TABLE public.manual_index (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_name   text NOT NULL,
  brand           text,
  model_prefix    text,
  text_content    text NOT NULL,
  chunk_index     integer DEFAULT 0,
  source_drive_id text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_drive_id, chunk_index)
);
CREATE INDEX manual_index_fts_idx ON public.manual_index
  USING gin(to_tsvector('spanish', text_content));
```

---

## New Supabase Stored Procedures (RPCs)

### `search_products_fts(p_query, p_brand, p_limit)`
Busca por nombre/SKU/part_number usando el índice FTS existente. Devuelve precio, stock, imagen.

### `search_products_by_model(p_model, p_brand, p_part_filter, p_limit)`
Busca via `product_compatibility` + `appliance_models` JOIN, con fallback al array `compatible_models[]`.

### `search_manual_index(p_query, p_brand, p_model)`
FTS sobre `text_content` de los manuales indexados.

*(Ver SQL completo en el output del agente de planificación)*

---

## Key Implementation Details

### Claude Prompts (`bot/utils/prompts.py`)

**Parse texto** → extrae `{part, brand, model, appliance_type, search_terms[], confidence}`  
**Identify part** → `{part_type, possible_brands[], description_es, part_number_visible, needs_more_info}`  
**Read label** → `{brand, model, serial_number, appliance_type, confidence}`

Todos responden **solo JSON válido** para evitar parsing errors.

### Image Handling (`bot/handlers/photo_handler.py`)
```python
# 1. Enviar "🔍 Analizando imagen..." inmediatamente
# 2. Descargar foto de Telegram (file_id → getFile → download bytes)
# 3. Detectar tipo: "etiqueta" en caption → read_label(); else → identify_part()
# 4. Buscar en Supabase con info extraída
# 5. Si confidence < 0.5 → pedir más info
```

### Search Strategy (`bot/services/supabase_service.py`)
```python
async def search_products(parsed: dict) -> list:
    results = []
    
    # Stage 1: FTS si hay términos de búsqueda
    if parsed.get("search_terms"):
        r1 = supabase.rpc("search_products_fts", {...}).execute()
        results.extend(r1.data)
    
    # Stage 2: Compatibility si hay modelo
    if parsed.get("model"):
        r2 = supabase.rpc("search_products_by_model", {...}).execute()
        results.extend(r2.data)
    
    # Deduplicar por id, priorizar los que aparecen en ambos stages
    # Retornar top 5
    
    # Stage 3: PDF fallback si results vacío
    if not results and parsed.get("search_terms"):
        results = supabase.rpc("search_manual_index", {...}).execute().data
    
    return results[:5]
```

### Response Format (`bot/utils/formatters.py`)
```
🔩 Resultados para: Perilla Samsung WA16W3

──────────────────────
📦 <b>Perilla Selector Temperatura LG/Samsung</b>
🏷️ SKU: REP-001 | N° Parte: WD-1234
💰 Precio: <b>L. 85.00</b>
✅ En stock (12 unidades)
──────────────────────

Para hacer tu pedido, contacta a nuestro equipo.
```

**Importante**: precios en `price_public / 100` (centavos → Lempiras).

### Session State TTL
Sesiones expiran a los 30 min de inactividad → estado `idle` automático.

---

## Environment Variables

```bash
# .env.example
TELEGRAM_BOT_TOKEN=           # De @BotFather
TELEGRAM_WEBHOOK_SECRET=      # secrets.token_hex(32)
SUPABASE_URL=                 # Mismo que nexos-tecni-express
SUPABASE_SERVICE_ROLE_KEY=    # Mismo que nexos-tecni-express
ANTHROPIC_API_KEY=            # Console Anthropic
GOOGLE_SERVICE_ACCOUNT_JSON=  # JSON string del service account
GOOGLE_DRIVE_FOLDER_ID=       # ID carpeta compartida con service account
APP_URL=                      # URL del deployment
```

---

## Dependencies (`requirements.txt`)

```
anthropic>=0.40.0
supabase>=2.10.0
fastapi>=0.115.0
uvicorn>=0.34.0
httpx>=0.27.0
google-auth>=2.35.0
google-api-python-client>=2.150.0
PyMuPDF>=1.24.0
python-dotenv>=1.0.0
```

---

## Setup & Deployment Checklist

### Fase 1 — Supabase (Día 1)
- [ ] Ejecutar SQL: crear `telegram_sessions`, `manual_index`
- [ ] Ejecutar SQL: crear las 3 stored procedures (RPCs)
- [ ] Agregar índice FTS en `description_es` de products
- [ ] Verificar que `product_stock_total` view existe

### Fase 2 — Google Drive (Día 1)
- [ ] Crear Google Cloud project, habilitar Drive API
- [ ] Crear service account, descargar JSON key
- [ ] Compartir carpeta de PDFs con el email del service account
- [ ] Configurar env vars `GOOGLE_SERVICE_ACCOUNT_JSON` y `GOOGLE_DRIVE_FOLDER_ID`
- [ ] Ejecutar `python scripts/index_pdfs.py` y verificar en Supabase

### Fase 3 — Bot Development (Días 2–4)
- [ ] `bot/config.py` → validación de env vars
- [ ] `bot/services/telegram_service.py` → test con sendMessage manual
- [ ] `bot/services/supabase_service.py` → test cada RPC por separado
- [ ] `bot/services/claude_service.py` → test con imágenes de muestra
- [ ] `bot/handlers/` → command, text, photo handlers
- [ ] `app/main.py` → FastAPI webhook endpoint

### Fase 4 — Testing Local (Día 4)
```bash
# Terminal 1
uvicorn app.main:app --reload --port 8000
# Terminal 2
ngrok http 8000
# Terminal 3 — registrar webhook
curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
  -d '{"url":"https://xxx.ngrok.io/webhook","secret_token":"xxx"}'
```
Probar los 3 flujos manualmente en Telegram.

### Fase 5 — Deploy Railway (Día 5)
```bash
railway login && railway init
railway up
# Set env vars en Railway dashboard
# Registrar webhook con URL de Railway
```

### Verificación Final
- Enviar texto: "necesito la perilla de mi lavadora Samsung WA16W3"
- Enviar foto de repuesto → debe identificar y cotizar
- Enviar foto de etiqueta + "necesito la correa" → debe leer modelo y buscar
- Caso sin resultados → mensaje informativo apropiado
- `/start` → resetea sesión y muestra bienvenida
