"""
whatsapp_bot.py
Bot de WhatsApp usando Evolution API (ARM64 compatible) + Flask webhook.
"""

import os
import time
import base64
import tempfile
import requests
from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

EVOLUTION_URL = os.getenv("EVOLUTION_URL", "http://evolution:8080")
API_KEY       = os.getenv("EVOLUTION_API_KEY", "")
INSTANCE      = "default"
BOT_URL       = os.getenv("BOT_URL", "http://bot:5000")
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR      = tempfile.gettempdir()

HEADERS = {"apikey": API_KEY, "Content-Type": "application/json"}

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Estado de conversación por chat
# ─────────────────────────────────────────────────────────────────────────────
FIELDS = ["alumno", "maestro", "materia", "tema", "grado_grupo", "fecha"]

FIELD_PROMPTS = {
    "alumno":      "Nombre del alumno:",
    "maestro":     "Nombre del maestro:",
    "materia":     "Nombre de la materia:",
    "tema":        "Tema o titulo del trabajo:",
    "grado_grupo": "Grado y grupo (ej. 3.- M):",
    "fecha":       "Fecha (ej. 25/03/2026):",
}

sessions: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers Evolution API
# ─────────────────────────────────────────────────────────────────────────────
def _number(chat_id: str) -> str:
    """Convierte '521234567890@s.whatsapp.net' → '521234567890'"""
    return chat_id.split("@")[0]


def send_text(chat_id: str, text: str):
    requests.post(
        f"{EVOLUTION_URL}/message/sendText/{INSTANCE}",
        json={"number": _number(chat_id), "text": text},
        headers=HEADERS, timeout=15,
    )


def send_file(chat_id: str, file_path: str, caption: str = ""):
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    requests.post(
        f"{EVOLUTION_URL}/message/sendMedia/{INSTANCE}",
        json={
            "number":    _number(chat_id),
            "mediatype": "document",
            "mimetype":  "application/pdf",
            "fileName":  os.path.basename(file_path),
            "caption":   caption,
            "media":     b64,
        },
        headers=HEADERS, timeout=30,
    )


def download_media(message: dict) -> bytes | None:
    """Descarga el archivo adjunto de un mensaje."""
    r = requests.post(
        f"{EVOLUTION_URL}/chat/getBase64FromMediaMessage/{INSTANCE}",
        json={"message": message, "convertToMp4": False},
        headers=HEADERS, timeout=30,
    )
    if r.status_code == 200:
        b64 = r.json().get("base64", "")
        if b64:
            return base64.b64decode(b64.split(",")[-1])
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


def handle(chat_id: str, text: str, msg_type: str, raw_message: dict):
    from cover_generator import generate_cover, prepend_cover_to_pdf

    session = sessions.get(chat_id, {})
    text = text.strip()

    has_media = msg_type in ("documentMessage", "audioMessage",
                             "imageMessage", "videoMessage")
    mime_type = ""
    if has_media:
        inner = raw_message.get("message", {}).get(msg_type, {})
        mime_type = inner.get("mimetype", "")

    # ── /portada ──────────────────────────────────────────────────────────
    if text.lower() in ("/portada", "portada", "/start"):
        sessions[chat_id] = {"step": FIELDS[0], "data": {}}
        send_text(chat_id,
            "Hola! Voy a ayudarte a crear tu hoja de presentacion.\n\n"
            + FIELD_PROMPTS[FIELDS[0]])
        return

    # ── Sin sesion ────────────────────────────────────────────────────────
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
                "Ahora sube tu documento PDF.")
        return

    # ── Recibiendo PDF ────────────────────────────────────────────────────
    if step == "waiting_pdf" and has_media and "pdf" in mime_type.lower():
        send_text(chat_id, "Recibido, generando tu portada...")

        media = download_media(raw_message)
        if not media:
            send_text(chat_id, "No pude descargar el archivo. Intentalo de nuevo.")
            return

        data       = session["data"]
        cover_path = os.path.join(TEMP_DIR, f"cover_{chat_id}.pdf")
        orig_path  = os.path.join(TEMP_DIR, f"orig_{chat_id}.pdf")
        final_path = os.path.join(TEMP_DIR, f"final_{chat_id}.pdf")

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
    event = data.get("event", "")

    if event != "messages.upsert":
        return jsonify({"ok": True})

    payload = data.get("data", {})

    # Ignorar mensajes propios
    key = payload.get("key", {})
    if key.get("fromMe"):
        return jsonify({"ok": True})

    chat_id  = key.get("remoteJid", "")
    msg_type = payload.get("messageType", "")
    message  = payload.get("message", {})

    # Texto del mensaje
    text = (message.get("conversation")
            or message.get("extendedTextMessage", {}).get("text", "")
            or "")

    if not chat_id:
        return jsonify({"ok": True})

    print(f"[MSG] from={chat_id} type={msg_type} text={text[:30]}")

    try:
        handle(chat_id, text, msg_type, payload)
    except Exception as e:
        print(f"[Error] {e}")

    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
# Rutas de administración
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/start-session")
def start_session():
    """Crea la instancia de WhatsApp y configura el webhook."""
    # 1. Crear instancia (ignorar si ya existe)
    r = requests.post(
        f"{EVOLUTION_URL}/instance/create",
        json={"instanceName": INSTANCE, "integration": "WHATSAPP-BAILEYS"},
        headers=HEADERS, timeout=15,
    )
    create_data = r.json() if r.content else {}

    # 2. Configurar webhook
    webhook_url = f"{BOT_URL}/webhook"
    r2 = requests.post(
        f"{EVOLUTION_URL}/webhook/set/{INSTANCE}",
        json={
            "webhook": {
                "enabled": True,
                "url": webhook_url,
                "by_events": True,
                "base64": False,
                "events": ["MESSAGES_UPSERT"],
            }
        },
        headers=HEADERS, timeout=15,
    )
    webhook_data = r2.json() if r2.content else {}

    return jsonify({
        "instance": create_data,
        "webhook": webhook_data,
        "webhook_url": webhook_url,
    })


@app.route("/qr")
def get_qr():
    """Devuelve el QR para vincular WhatsApp."""
    r = requests.get(
        f"{EVOLUTION_URL}/instance/connect/{INSTANCE}",
        headers=HEADERS, timeout=15,
    )
    if r.status_code != 200:
        return jsonify({"error": r.text}), r.status_code

    data = r.json()
    b64 = data.get("base64", "")
    if b64:
        img = base64.b64decode(b64.split(",")[-1])
        return Response(img, mimetype="image/png")

    return jsonify(data)


# ─────────────────────────────────────────────────────────────────────────────
def wait_for_evolution():
    print("Esperando que Evolution API este lista...")
    for _ in range(30):
        try:
            r = requests.get(f"{EVOLUTION_URL}/", timeout=3)
            if r.status_code < 500:
                print("Evolution API lista.")
                return
        except Exception:
            pass
        time.sleep(2)
    print("Evolution API no respondio, continuando de todas formas...")


if __name__ == "__main__":
    import threading
    threading.Thread(target=wait_for_evolution, daemon=True).start()
    print("Bot iniciado en puerto 5000")
    app.run(host="0.0.0.0", port=5000)
