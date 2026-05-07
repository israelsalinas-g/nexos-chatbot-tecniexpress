from typing import Optional


def format_price(price_centavos: int) -> str:
    """Convierte centavos a Lempiras formateados."""
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
    sku = product.get("sku", "")
    part_number = product.get("part_number", "")
    price = product.get("price_public", 0)
    quantity = product.get("total_quantity") or product.get("stock_quantity", 0)
    brand = product.get("brand_name", "")

    lines = [f"📦 <b>{name}</b>"]

    if brand:
        lines.append(f"🏷️ Marca: {brand}")

    id_line = " | ".join(filter(None, [
        f"SKU: {sku}" if sku else None,
        f"N° Parte: {part_number}" if part_number else None,
    ]))
    if id_line:
        lines.append(f"🔢 {id_line}")

    if price:
        lines.append(f"💰 Precio: <b>{format_price(price)}</b>")

    lines.append(format_stock(int(quantity or 0)))

    return "\n".join(lines)


_SOURCE_LABELS: dict[str, str] = {
    "fts":    "🗄️ BD/texto",
    "model":  "🗄️ BD/modelo",
    "manual": "📄 Manuales PDF",
    "web":    "🌐 Web fabricante",
}


def format_quote_response(products: list[dict], query_context: dict, sources: list[str] | None = None) -> str:
    """Construye el mensaje completo de cotización."""
    query_desc = _build_query_description(query_context)

    if not products:
        return format_no_results(query_context)

    separator = "\n" + "─" * 22 + "\n"
    source_line = ""
    if sources:
        labels = " + ".join(_SOURCE_LABELS.get(s, s) for s in sources)
        source_line = f"\n<i>Fuente: {labels}</i>"

    header = f"🔩 <b>Resultados para: {query_desc}</b>{source_line}\n"
    product_blocks = separator.join(format_product(p) for p in products[:5])
    footer = (
        "\n\n💬 Para confirmar disponibilidad o hacer tu pedido, "
        "contacta a nuestro equipo de ventas."
    )

    return header + separator + product_blocks + footer


def format_no_results(query_context: dict) -> str:
    query_desc = _build_query_description(query_context)
    brand = query_context.get("brand")
    model = query_context.get("model")

    msg = f"😔 No encontré resultados para: <b>{query_desc}</b>\n\n"

    suggestions = []
    if not brand:
        suggestions.append("• Indica la <b>marca</b> del equipo (LG, Samsung, Mabe, GE, Whirlpool...)")
    if not model:
        suggestions.append("• Proporciona el <b>número de modelo</b> del electrodoméstico")
    suggestions.append("• Puedes enviar una <b>foto del repuesto</b> o de la <b>etiqueta del equipo</b>")

    if suggestions:
        msg += "Intenta con más detalles:\n" + "\n".join(suggestions)

    msg += "\n\n📞 También puedes contactarnos directamente para ayudarte."
    return msg


def format_needs_clarification(missing_fields: list[str], current_context: dict) -> str:
    """Pide al usuario información que falta para completar la búsqueda."""
    if "brand" in missing_fields:
        return (
            "🔍 ¿De qué <b>marca</b> es tu electrodoméstico?\n"
            "LG · Samsung · Mabe · GE · Whirlpool · Frigidaire · Otra"
        )
    if "model" in missing_fields:
        brand = current_context.get("brand", "tu equipo")
        return (
            f"🔍 ¿Cuál es el <b>número de modelo</b> de {brand}?\n"
            "Puedes encontrarlo en la etiqueta del equipo o enviarnos una foto de ella."
        )
    if "part" in missing_fields:
        return "🔍 ¿Qué <b>repuesto</b> necesitas? Descríbelo o envía una foto del repuesto dañado."

    return "🔍 Por favor proporciona más detalles sobre el repuesto que necesitas."


def format_image_analysis_result(analysis: dict, image_type: str) -> str:
    """Mensaje de confirmación después de analizar una imagen."""
    if image_type == "label":
        brand = analysis.get("brand", "desconocida")
        model = analysis.get("model", "desconocido")
        confidence = analysis.get("confidence", 0)

        if confidence < 0.5:
            return (
                "⚠️ No pude leer claramente la etiqueta.\n"
                "¿Podrías escribir la <b>marca</b> y <b>modelo</b> del equipo?"
            )
        return f"✅ Equipo identificado: <b>{brand} {model}</b>\n¿Qué repuesto necesitas?"

    else:  # part photo
        part = analysis.get("part_type", "repuesto desconocido")
        confidence = analysis.get("confidence", 0)
        needs_more = analysis.get("needs_more_info", False)

        if confidence < 0.4 or needs_more:
            missing = analysis.get("missing_info", "más información")
            return f"🔍 Identificé un posible repuesto pero necesito {missing}. ¿Puedes añadir detalles?"

        return f"🔍 Identificado: <b>{part}</b>\nBuscando en nuestro inventario..."


def format_manual_result(manual_result: dict, query_context: dict) -> str:
    """Formato para resultados encontrados en manuales PDF."""
    brand = manual_result.get("brand", "")
    model = manual_result.get("model_prefix", "")
    excerpt = manual_result.get("excerpt", "")
    part_number = manual_result.get("part_number")
    part_name = manual_result.get("part_name")

    header = f"📄 <b>Información encontrada en manual técnico</b>"
    if brand or model:
        header += f" ({(' '.join(filter(None, [brand, model]))).strip()})"

    lines = [
        header,
        f"<i>Fuente: 📄 Manuales PDF</i>\n",
        f"✅ <b>¡Código encontrado!</b>",
        f"🔢 N° Parte: <code>{part_number or 'No especificado'}</code>",
        f"📦 Repuesto: <b>{part_name or 'No especificado'}</b>",
        f"\n<i>Detalle: {excerpt[:300]}...</i>\n",
        "⏳ <b>Próximamente se le enviará la cotización.</b>",
        "📞 Para agilizar, puedes contactarnos directamente."
    ]

    return "\n".join(lines)


def format_welcome(user_name: Optional[str] = None) -> str:
    name_part = f", {user_name}" if user_name else ""
    return (
        f"👋 ¡Hola{name_part}! Bienvenido a <b>Tecni Express</b>.\n\n"
        "Somos especialistas en repuestos para lavadoras y secadoras.\n"
        "Puedo ayudarte a cotizar el repuesto que necesitas.\n\n"
        "<b>Puedes:</b>\n"
        "• Escribir qué repuesto necesitas y el modelo del equipo\n"
        "• Enviar una <b>foto del repuesto</b> dañado\n"
        "• Enviar una <b>foto de la etiqueta</b> del equipo\n\n"
        "¿Qué repuesto necesitas hoy?"
    )


def format_help() -> str:
    return (
        "ℹ️ <b>¿Cómo usar este bot?</b>\n\n"
        "<b>Opción 1 — Descripción de texto:</b>\n"
        "Escribe el repuesto, marca y modelo. Ejemplo:\n"
        "<i>\"Necesito la correa de mi lavadora Samsung WA16W3\"</i>\n\n"
        "<b>Opción 2 — Foto del repuesto:</b>\n"
        "Envía una foto del repuesto dañado y lo identificamos.\n\n"
        "<b>Opción 3 — Foto de la etiqueta:</b>\n"
        "Envía una foto de la etiqueta del equipo con el texto "
        "<i>\"etiqueta\"</i> como pie de foto, y dinos qué repuesto necesitas.\n\n"
        "<b>Marcas que manejamos:</b>\n"
        "LG · Samsung · Mabe · GE · Whirlpool · Frigidaire · y más\n\n"
        "📞 Para pedidos y pagos, nuestro equipo te atenderá directamente."
    )


def _build_query_description(ctx: dict) -> str:
    """Construye una descripción legible del query para el encabezado."""
    parts = []
    if ctx.get("part"):
        parts.append(ctx["part"].title())
    if ctx.get("brand"):
        parts.append(ctx["brand"])
    if ctx.get("model"):
        parts.append(ctx["model"])
    return " · ".join(parts) if parts else "tu consulta"
