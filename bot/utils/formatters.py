import os
from typing import Optional

_WEBSITE_BASE_URL_DEFAULT = "https://nexos-tecni-express.vercel.app/es"


def _website_base_url() -> str:
    return os.getenv("WEBSITE_BASE_URL", _WEBSITE_BASE_URL_DEFAULT)


def _sales_contact() -> str:
    return os.getenv("SALES_CONTACT", "")


def format_price(price_centavos: int) -> str:
    return f"L. {price_centavos / 100:,.2f}"


def format_stock(quantity: int) -> str:
    if quantity == 0:
        return "❌ Sin stock"
    elif quantity <= 3:
        return f"⚠️ Pocas unidades ({quantity})"
    else:
        return f"✅ En stock ({quantity} unidades)"


def format_product(product: dict) -> str:
    """Formatea un producto individual como bloque HTML de Telegram."""
    name = product.get("name_es", "Repuesto")
    part_number = product.get("part_number", "")
    price = product.get("price_public", 0)
    quantity = product.get("total_quantity") or product.get("stock_quantity", 0)
    brand = product.get("brand_name", "")
    slug = product.get("slug")

    lines = [f"📦 <b>{name}</b>"]

    if brand:
        lines.append(f"🏷️ Marca: {brand}")

    if part_number:
        lines.append(f"🔢 N° Parte: <code>{part_number}</code>")

    if price:
        lines.append(f"💰 Precio al público: <b>{format_price(price)}</b>")

    lines.append(format_stock(int(quantity or 0)))

    base_url = _website_base_url()
    if slug and base_url:
        lines.append(f'🛒 <a href="{base_url}/products/{slug}">Solicitar este producto</a>')

    return "\n".join(lines)


_SOURCE_LABELS: dict[str, str] = {
    "code":          "🗄️ BD/código",
    "word_match":    "🗄️ BD/palabras",
    "brand_only":    "🗄️ BD/marca",
    "brand_product": "🗄️ BD/marca+producto",
    "fts":           "🗄️ BD/texto",
    "ilike":         "🗄️ BD/aproximado",
    "model":         "🗄️ BD/modelo",
    "manual":        "📄 Manuales PDF",
    "gdrive":        "📄 Manuales PDF (Drive)",
    "web":           "🌐 Conocimiento técnico",
}


def format_quote_header(query_context: dict, sources: list[str] | None = None) -> str:
    query_desc = _build_query_description(query_context)
    source_line = ""
    if sources:
        labels = " + ".join(_SOURCE_LABELS.get(s, s) for s in sources)
        source_line = f"\n<i>Fuente: {labels}</i>"
    return f"🔩 <b>Resultados para: {query_desc}</b>{source_line}"


def format_quote_footer() -> str:
    return "💬 Para confirmar disponibilidad o hacer tu pedido, contacta a nuestro equipo de ventas."


def format_quote_response(products: list[dict], query_context: dict, sources: list[str] | None = None) -> str:
    """Fallback para envío sin foto (compatibilidad)."""
    if not products:
        return format_no_results(query_context)

    header = format_quote_header(query_context, sources)
    separator = "\n" + "─" * 22 + "\n"
    product_blocks = separator.join(format_product(p) for p in products[:5])
    footer = "\n\n" + format_quote_footer()

    return header + "\n" + separator + product_blocks + footer


def format_no_results(query_context: dict) -> str:
    query_desc = _build_query_description(query_context)

    msg = f"😔 No encontré resultados para: <b>{query_desc}</b>\n\n"
    msg += "Intenta con:\n"
    msg += "• Otro nombre o sinónimo del repuesto\n"
    msg += "• El SKU o N° de parte exacto (ej: <code>WPW10006355</code>)\n"
    msg += "• Solo la marca (ej: <i>Mabe</i> o <i>Whirlpool</i>)\n\n"
    msg += "¿No lo encuentras? Escribe /ventas y un asesor te ayudará a localizarlo."

    return msg


def format_escalate_sales() -> str:
    contact = _sales_contact()
    if contact:
        return (
            "🛒 <b>Contactar a Ventas</b>\n\n"
            "Un asesor de Tecni Express puede ayudarte a localizar el repuesto.\n\n"
            f"📲 Contáctanos aquí: {contact}"
        )
    return (
        "🛒 <b>Contactar a Ventas</b>\n\n"
        "Un asesor de Tecni Express puede ayudarte a localizar el repuesto.\n"
        "Por favor espera — un asesor se pondrá en contacto contigo pronto."
    )


def format_needs_clarification(missing_fields: list[str], current_context: dict) -> str:
    if "brand" in missing_fields:
        return (
            "🔍 ¿De qué <b>marca</b> es el equipo?\n"
            "LG · Samsung · Mabe · GE · Whirlpool · Frigidaire · Otra"
        )
    if "model" in missing_fields:
        brand = current_context.get("brand", "el equipo")
        return f"🔍 ¿Cuál es el <b>número de modelo</b> de {brand}?"
    if "part" in missing_fields:
        return "🔍 ¿Qué <b>repuesto</b> necesitas? Escribe el nombre, descripción o SKU."

    return "🔍 Por favor proporciona más detalles sobre el repuesto que necesitas."


def format_manual_result(manual_result: dict, _query_context: dict) -> str:
    brand = manual_result.get("brand", "")
    model = manual_result.get("model_prefix", "")
    excerpt = manual_result.get("excerpt", "")
    part_number = manual_result.get("part_number")
    part_name = manual_result.get("part_name")

    header = "📄 <b>Información encontrada en manual técnico</b>"
    if brand or model:
        header += f" ({(' '.join(filter(None, [brand, model]))).strip()})"

    lines = [
        header,
        f"<i>Fuente: 📄 Manuales PDF</i>\n",
        "✅ <b>¡Código encontrado!</b>",
        f"🔢 N° Parte: <code>{part_number or 'No especificado'}</code>",
        f"📦 Repuesto: <b>{part_name or 'No especificado'}</b>",
        f"\n<i>Detalle: {excerpt[:300]}...</i>\n",
        "📞 Contacta a nuestro equipo para confirmar disponibilidad y precio.",
    ]

    return "\n".join(lines)


def format_manufacturer_web(web_text: str, query_context: dict) -> str:
    query_desc = _build_query_description(query_context)
    return (
        f"🤖 <b>Referencia técnica: {query_desc}</b>\n\n"
        f"{web_text}\n\n"
        "⚠️ <i>Este repuesto no está en el inventario actual. "
        "Escribe /ventas y un asesor verificará disponibilidad bajo pedido.</i>"
    )


def format_brief_welcome() -> str:
    """Bienvenida breve para el primer mensaje de un usuario nuevo."""
    return "👋 <b>Tecni Express</b> — ¿Qué repuesto necesitas?"


def format_welcome(user_name: Optional[str] = None) -> str:
    name_part = f", {user_name}" if user_name else ""
    return (
        f"👋 Bienvenido{name_part} a <b>Tecni Express</b>.\n"
        "Repuestos para lavadoras, secadoras y estufas eléctricas.\n\n"
        "<code>Actuador Whirlpool</code> · <code>Banda Mabe</code> · <code>WPW10006355</code>\n\n"
        "/help · /ventas"
    )


def format_help() -> str:
    return (
        "ℹ️ <b>Cómo buscar repuestos</b>\n\n"
        "Envía el nombre, descripción o SKU del repuesto:\n\n"
        "<code>Actuador Whirlpool</code>\n"
        "<code>Banda secadora Mabe</code>\n"
        "<code>Elemento calefactor LG estufa</code>\n"
        "<code>WPW10006355</code>\n\n"
        "<b>Marcas:</b> LG · Samsung · Mabe · GE · Whirlpool · Frigidaire · Acros\n"
        "<b>Equipos:</b> Lavadoras · Secadoras · Estufas eléctricas\n\n"
        "¿No encuentras el repuesto? Escribe /ventas para hablar con un asesor."
    )


def _build_query_description(ctx: dict) -> str:
    parts = []
    if ctx.get("part"):
        parts.append(ctx["part"].title())
    elif ctx.get("search_terms"):
        parts.append(" ".join(ctx["search_terms"]).title())
    if ctx.get("brand"):
        parts.append(ctx["brand"])
    if ctx.get("model"):
        parts.append(ctx["model"])
    return " · ".join(parts) if parts else "tu consulta"
