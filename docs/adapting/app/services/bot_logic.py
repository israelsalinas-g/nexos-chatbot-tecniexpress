"""
bot_logic.py — Lógica principal del chatbot

Flujo real (como trabajan manualmente):
  Cliente envía: foto | texto | código
       ↓
  Claude extrae: marca, modelo, tipo de pieza, código
       ↓
  Capa 1: Supabase (catálogo propio 227 productos)
       ↓ (no encontrado)
  Capa 2: PDF manual en Google Drive (por modelo)
       ↓ (no encontrado en PDF)
  Capa 3: Sitio web del fabricante (referencia de precio)
       ↓ (nada)
  Escalar a asesor humano
"""
import logging
from app.services import supabase_service as db
from app.services import claude_service as ai
from app.services import telegram_service as tg
from app.services import gdrive_service as gdrive

logger = logging.getLogger(__name__)


async def handle_message(message: dict):
    """Punto de entrada para cada mensaje de Telegram."""
    chat_id   = str(message["chat"]["id"])
    from_user = message.get("from", {})
    user_name = from_user.get("first_name", "Cliente")
    text      = message.get("text", "").strip()
    photos    = message.get("photo")
    caption   = message.get("caption", "")

    conv = await db.get_conversation(chat_id)

    # ── /start ────────────────────────────────────────────────────────────────
    if text == "/start":
        conv = {"chat_id": chat_id, "messages": [], "state": "idle",
                "last_query": None, "last_query_info": {}}
        await db.save_conversation(conv)
        await tg.send_main_menu(chat_id, user_name)
        return

    # ── Foto ──────────────────────────────────────────────────────────────────
    if photos:
        await tg.send_typing(chat_id)
        await tg.send_message(chat_id, "📷 Analizando la imagen...")
        best = max(photos, key=lambda p: p.get("file_size", 0))
        photo_url = await tg.get_file_url(best["file_id"])
        query_info = await ai.analyze_image(photo_url, caption=caption or None)
        await _search_and_respond(chat_id, user_name, conv, query_info)
        return

    # ── Texto ─────────────────────────────────────────────────────────────────
    if text:
        if conv.get("state") == "awaiting_code":
            query_info = {
                "codigo_parte": text.upper(),
                "descripcion_busqueda": text,
                "marca": None, "modelo": None, "tipo_pieza": None, "confianza": "alta"
            }
        else:
            await tg.send_typing(chat_id)
            query_info = await ai.analyze_text(text)

        await _search_and_respond(chat_id, user_name, conv, query_info)
        return

    # ── Fallback ──────────────────────────────────────────────────────────────
    await tg.send_main_menu(chat_id, user_name)


async def handle_callback(callback: dict):
    """Maneja botones inline."""
    chat_id   = str(callback["message"]["chat"]["id"])
    data      = callback.get("data", "")
    user_name = callback.get("from", {}).get("first_name", "Cliente")
    conv      = await db.get_conversation(chat_id)

    if data == "search:photo":
        conv["state"] = "awaiting_photo"
        await db.save_conversation(conv)
        await tg.send_message(chat_id, "📷 Envíame la foto del repuesto (puedes agregar descripción como pie de foto).")

    elif data == "search:code":
        conv["state"] = "awaiting_code"
        await db.save_conversation(conv)
        await tg.send_message(chat_id, "🔢 Escribe el SKU o código de parte:")

    elif data == "search:text":
        conv["state"] = "awaiting_text"
        await db.save_conversation(conv)
        await tg.send_message(chat_id,
            '💬 Describe el repuesto que necesitas.\n'
            '<i>Ejemplo: "perilla de temperatura lavadora LG WM3500"</i>')

    elif data == "search:brand":
        await tg.send_brand_menu(chat_id)

    elif data.startswith("brand:"):
        marca = data.split(":")[1]
        conv["state"] = "awaiting_text"
        conv["last_query_info"] = {"marca": marca}
        await db.save_conversation(conv)
        await tg.send_message(chat_id,
            f"🏷️ Marca: <b>{marca}</b>\n¿Qué tipo de repuesto necesitas? (puedes incluir el modelo)")

    elif data.startswith("order:"):
        codigo = data.split(":", 1)[1]
        await tg.send_message(chat_id,
            f"✅ Pedido registrado para <code>{codigo}</code>.\n"
            "Un asesor confirmará disponibilidad y envío pronto. 📦")
        await tg.notify_advisor(chat_id, user_name, f"PEDIDO: {codigo}", "")

    elif data.startswith("advisor:"):
        info = data.split(":", 1)[1]
        await tg.send_message(chat_id, "📞 Conectando con un asesor...")
        last_info = conv.get("last_query_info", {})
        await tg.notify_advisor(chat_id, user_name,
            conv.get("last_query", info),
            f"Marca: {last_info.get('marca')} | Modelo: {last_info.get('modelo')} | Pieza: {last_info.get('tipo_pieza')}")

    elif data.startswith("manual:"):
        # Usuario quiere que busquemos en manual PDF
        await tg.send_message(chat_id, "📋 Buscando en manuales del fabricante...")
        last_info = conv.get("last_query_info", {})
        await _search_manual_and_respond(chat_id, user_name, conv, last_info)


# ── Flujo principal de búsqueda ───────────────────────────────────────────────
async def _search_and_respond(chat_id: str, user_name: str, conv: dict, query_info: dict):
    """
    Orquesta la búsqueda en 3 capas y envía la respuesta al cliente.
    """
    await tg.send_typing(chat_id)

    # Guardar contexto en conversación
    conv["last_query"] = query_info.get("descripcion_busqueda", "")
    conv["last_query_info"] = query_info
    conv["messages"].append({"role": "user", "content": conv["last_query"]})
    conv["state"] = "searching"

    # ── CAPA 1: Supabase ──────────────────────────────────────────────────────
    products, method = await db.smart_search(
        query_text = query_info.get("descripcion_busqueda"),
        brand_name = query_info.get("marca"),
        model      = query_info.get("modelo"),
        code       = query_info.get("codigo_parte"),
    )
    await db.log_search(chat_id, conv["last_query"], f"supabase_{method}", len(products))

    if products:
        response = await ai.generate_response(
            products, query_info,
            conv.get("messages", []),
            source="nuestro catálogo",
        )
        await tg.send_message(chat_id, response)
        for p in products[:3]:
            await tg.send_product_card(chat_id, p)
        conv["state"] = "idle"
        await db.save_conversation(conv)
        return

    # ── CAPA 2: Manual PDF en Google Drive ────────────────────────────────────
    marca  = query_info.get("marca", "") or ""
    modelo = query_info.get("modelo", "") or ""

    if modelo:
        await tg.send_message(chat_id,
            f"🔍 No está en nuestro catálogo. Buscando en manual de <b>{marca} {modelo}</b>...")
        await _search_manual_and_respond(chat_id, user_name, conv, query_info)
    else:
        # Sin modelo no podemos buscar el manual correcto — pedir más info
        await tg.send_message(chat_id,
            f"🔍 No encontré ese repuesto en nuestro catálogo.\n\n"
            f"Para buscar en los manuales del fabricante necesito el <b>modelo de tu electrodoméstico</b>.\n"
            f"¿Puedes indicarme el número de modelo? (está en la etiqueta del equipo)")
        conv["state"] = "awaiting_model"
        await db.save_conversation(conv)


async def _search_manual_and_respond(chat_id: str, user_name: str, conv: dict, query_info: dict):
    """Capa 2+3: busca en PDF de Drive y luego en web del fabricante."""
    marca  = query_info.get("marca", "") or ""
    modelo = query_info.get("modelo", "") or ""
    pieza  = query_info.get("tipo_pieza", "") or ""

    # 2a. Buscar PDF en Drive
    manual_result = await gdrive.search_in_manual(
        brand=marca,
        model=modelo,
        part_description=query_info.get("descripcion_busqueda", ""),
        part_type=pieza,
    )

    if manual_result.get("found") and manual_result.get("relevant_text"):
        await db.log_search(chat_id, conv.get("last_query", ""), "manual_pdf", 1)
        extracted = await ai.extract_from_manual(manual_result["relevant_text"], query_info)
        await tg.send_message(chat_id,
            f"📋 <b>Encontré en el manual técnico de {marca} {modelo}:</b>\n\n"
            f"{extracted}\n\n"
            f"⚠️ <i>Este repuesto no está en nuestro inventario actual. Podemos cotizarlo.</i>"
        )
        keyboard = {"inline_keyboard": [[
            {"text": "💬 Solicitar cotización", "callback_data": "order:COTIZAR"},
            {"text": "📞 Hablar con asesor",    "callback_data": "advisor:manual"},
        ]]}
        await tg.send_message(chat_id, "¿Qué deseas hacer?", reply_markup=keyboard)
        conv["state"] = "idle"
        await db.save_conversation(conv)
        return

    # 2b. No había PDF en Drive → buscar en web del fabricante
    await tg.send_message(chat_id,
        f"📖 No tengo el manual de <b>{modelo}</b> en nuestros archivos.\n"
        f"Consultando información del fabricante...")
    await tg.send_typing(chat_id)

    web_result = await ai.search_manufacturer_web(query_info)
    await db.log_search(chat_id, conv.get("last_query", ""), "web_fabricante", 1)

    await tg.send_message(chat_id,
        f"🌐 <b>Información del fabricante:</b>\n\n{web_result}\n\n"
        f"<i>Podemos conseguir este repuesto bajo pedido.</i>"
    )
    keyboard = {"inline_keyboard": [[
        {"text": "💬 Solicitar cotización", "callback_data": "order:COTIZAR"},
        {"text": "📞 Hablar con asesor",    "callback_data": "advisor:web"},
    ]]}
    await tg.send_message(chat_id, "¿Quieres que te cotizamos?", reply_markup=keyboard)
    await tg.notify_advisor(chat_id, user_name, conv.get("last_query", ""),
        f"Marca: {marca} | Modelo: {modelo} | Pieza: {pieza} | Fuente: web_fabricante")
    conv["state"] = "escalated"
    await db.save_conversation(conv)
