"""
whatsapp_bot.py
Bot de WhatsApp usando WAHA (self-hosted) + Flask webhook.

Flujo:
  1. WAHA recibe mensajes de WhatsApp y los manda a /webhook
  2. El bot procesa el mensaje y responde via la API de WAHA
"""

import os
import tempfile
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

WAHA_URL = os.getenv("WAHA_URL", "http://waha:3000")
WAHA_KEY = os.getenv("WAHA_API_KEY", "")
SESSION  = "default"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = tempfile.gettempdir()

HEADERS = {"X-Api-Key": WAHA_KEY} if WAHA_KEY else {}

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Estado de conversación por chat
# ─────────────────────────────────────────────────────────────────────────────
FIELDS = ["alumno", "maestro", "materia", "tema", "grado_grupo", "fecha"]

FIELD_PROMPTS = {
    "alumno":      "Nombre del *alumno*:",
    "maestro":     "Nombre del *maestro*:",
    "materia":     "Nombre de la *materia*:",
    "tema":        "Nombre del *tema* o título del trabajo:",
    "grado_grupo": "*Grado y grupo* (ej. 3.- M):",
    "fecha":       "*Fecha* (ej. 25/03/2026):",
}

sessions: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers WAHA
# ─────────────────────────────────────────────────────────────────────────────
def send_text(chat_id: str, text: str):
    requests.post(f"{WAHA_URL}/api/sendText", json={
        "chatId":  chat_id,
        "text":    text,
        "session": SESSION,
    }, headers=HEADERS, timeout=10)


def send_file(chat_id: str, file_path: str, caption: str = ""):
    with open(file_path, "rb") as f:
        requests.post(f"{WAHA_URL}/api/sendFile",
            data={"chatId": chat_id, "session": SESSION, "caption": caption},
            files={"file": (os.path.basename(file_path), f, "application/pdf")},
            headers=HEADERS,
            timeout=30,
        )


def download_media(message_id: str) -> bytes | None:
    """Descarga el archivo de un mensaje con media desde WAHA."""
    r = requests.post(
        f"{WAHA_URL}/api/{SESSION}/messages/{message_id}/download-media",
        headers=HEADERS,
        timeout=30,
    )
    if r.status_code == 200:
        return r.content
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Lógica de conversación
# ─────────────────────────────────────────────────────────────────────────────
def next_field(step: str) -> str | None:
    try:
        idx = FIELDS.index(step)
        return FIELDS[idx + 1] if idx + 1 < len(FIELDS) else None
    except ValueError:
        return FIELDS[0]


def handle(chat_id: str, text: str, has_media: bool,
           mime_type: str, message_id: str):
    from cover_generator import generate_cover, prepend_cover_to_pdf

    session = sessions.get(chat_id, {})
    text = text.strip()

    # ── /portada ─────────────────────────────────────────────────────────
    if text.lower() in ("/portada", "portada", "/start"):
        sessions[chat_id] = {"step": FIELDS[0], "data": {}}
        send_text(chat_id,
            "Hola! Voy a ayudarte a crear tu hoja de presentacion.\n\n"
            + FIELD_PROMPTS[FIELDS[0]])
        return

    # ── Sin sesión ────────────────────────────────────────────────────────
    if not session:
        send_text(chat_id, "Escribe /portada para crear una hoja de presentacion.")
        return

    step = session.get("step")

    # ── Recibiendo campos de texto ────────────────────────────────────────
    if step in FIELDS and text:
        session["data"][step] = text
        nxt = next_field(step)
        if nxt:
            session["step"] = nxt
            send_text(chat_id, FIELD_PROMPTS[nxt])
        else:
            session["step"] = "waiting_pdf"
            summary = "\n".join(
                f"- {k.replace('_',' ').title()}: {v}"
                for k, v in session["data"].items()
            )
            send_text(chat_id,
                f"Datos registrados:\n\n{summary}\n\n"
                "Ahora sube tu documento PDF y le agrego la portada al inicio.")
        return

    # ── Recibiendo PDF ────────────────────────────────────────────────────
    if step == "waiting_pdf" and has_media and "pdf" in mime_type.lower():
        send_text(chat_id, "Recibido, generando tu portada...")

        media = download_media(message_id)
        if not media:
            send_text(chat_id, "No pude descargar el archivo. Intentalo de nuevo.")
            return

        data         = session["data"]
        cover_path   = os.path.join(TEMP_DIR, f"cover_{chat_id}.pdf")
        orig_path    = os.path.join(TEMP_DIR, f"orig_{chat_id}.pdf")
        final_path   = os.path.join(TEMP_DIR, f"final_{chat_id}.pdf")

        with open(orig_path, "wb") as f:
            f.write(media)

        generate_cover(
            alumno=data.get("alumno", ""),
            maestro=data.get("maestro", ""),
            materia=data.get("materia", ""),
            tema=data.get("tema", ""),
            grado_grupo=data.get("grado_grupo", ""),
            fecha=data.get("fecha", ""),
            output_path=cover_path,
        )

        prepend_cover_to_pdf(cover_path, orig_path, final_path)

        send_file(chat_id, final_path,
            f"Aqui esta tu documento con la portada, {data.get('alumno','')}")

        del sessions[chat_id]
        for p in [cover_path, orig_path, final_path]:
            try: os.remove(p)
            except OSError: pass
        return

    if step == "waiting_pdf" and has_media and "pdf" not in mime_type.lower():
        send_text(chat_id, "Ese archivo no es un PDF. Por favor sube un archivo .pdf")
        return

    if step in FIELDS:
        send_text(chat_id, FIELD_PROMPTS[step])


# ─────────────────────────────────────────────────────────────────────────────
# Webhook
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}

    if data.get("event") != "message":
        return jsonify({"ok": True})

    payload = data.get("payload", {})

    if payload.get("fromMe"):
        return jsonify({"ok": True})

    chat_id    = payload.get("from", "")
    text       = payload.get("body", "") or ""
    has_media  = payload.get("hasMedia", False)
    mime_type  = (payload.get("mimetype")
                  or payload.get("_data", {}).get("mimetype", ""))
    message_id = payload.get("id", "")

    if not chat_id:
        return jsonify({"ok": True})

    try:
        handle(chat_id, text, has_media, mime_type, message_id)
    except Exception as e:
        print(f"[Error] {e}")

    return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Bot iniciado en puerto 5000")
    app.run(host="0.0.0.0", port=5000)
