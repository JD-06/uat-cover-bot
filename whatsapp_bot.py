"""
whatsapp_bot.py
Bot de WhatsApp usando Green API (https://green-api.com) — plan gratuito disponible.

FLUJO:
  1. Usuario escribe /portada
  2. Bot pregunta los datos uno por uno
  3. Usuario sube su PDF
  4. Bot genera la portada, la pega al frente y envía el PDF final

CONFIGURACIÓN:
  Crea un archivo .env (o edita las constantes de abajo) con:
    INSTANCE_ID   → ID de instancia de Green API
    API_TOKEN     → Token de la instancia
"""

import os
import tempfile
import urllib.request
from dotenv import load_dotenv
from whatsapp_api_client_python import API

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN  (también puedes poner estas variables en un .env)
# ─────────────────────────────────────────────────────────────────────────────
INSTANCE_ID = os.getenv("INSTANCE_ID", "TU_INSTANCE_ID_AQUI")
API_TOKEN   = os.getenv("API_TOKEN",   "TU_API_TOKEN_AQUI")

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR    = tempfile.gettempdir()

# ─────────────────────────────────────────────────────────────────────────────
# Estado de conversación por chat
# ─────────────────────────────────────────────────────────────────────────────
# Campos que pedimos en orden
FIELDS = ["alumno", "maestro", "materia", "tema", "grado_grupo", "fecha"]

FIELD_PROMPTS = {
    "alumno":      "Nombre del *alumno*:",
    "maestro":     "Nombre del *maestro*:",
    "materia":     "Nombre de la *materia*:",
    "tema":        "Nombre del *tema* o título del trabajo:",
    "grado_grupo": "*Grado y grupo* (ej. 3.- M):",
    "fecha":       "*Fecha* (ej. 25/03/2026):",
}

# chat_id → {"step": str, "data": dict}
sessions: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def send_text(api: API, chat_id: str, text: str):
    api.sending.sendMessage(chat_id, text)


def send_file(api: API, chat_id: str, file_path: str, caption: str = ""):
    api.sending.sendFileByUpload(chat_id, file_path, os.path.basename(file_path), caption)


def download_file(url: str, dest: str):
    urllib.request.urlretrieve(url, dest)


def next_field(step: str) -> str | None:
    """Devuelve el siguiente campo después de `step`, o None si ya terminaron."""
    try:
        idx = FIELDS.index(step)
        return FIELDS[idx + 1] if idx + 1 < len(FIELDS) else None
    except ValueError:
        return FIELDS[0] if FIELDS else None


# ─────────────────────────────────────────────────────────────────────────────
# Lógica principal de mensajes
# ─────────────────────────────────────────────────────────────────────────────
def handle_message(api: API, notification: dict):
    """Procesa cada mensaje entrante."""
    from cover_generator import generate_cover, prepend_cover_to_pdf

    body     = notification.get("body", {})
    msg_data = body.get("messageData", {})
    chat_id  = body.get("senderData", {}).get("chatId", "")

    if not chat_id:
        return

    # ── Texto plano ───────────────────────────────────────────────────────
    text_msg = msg_data.get("textMessageData", {}).get("textMessage", "").strip()

    # ── Documento / PDF ───────────────────────────────────────────────────
    file_msg  = msg_data.get("fileMessageData", {})
    file_url  = file_msg.get("downloadUrl", "")
    mime_type = file_msg.get("mimeType", "")

    session = sessions.get(chat_id, {})

    # ── Comando /portada ──────────────────────────────────────────────────
    if text_msg.lower() in ("/portada", "portada", "/start"):
        sessions[chat_id] = {"step": None, "data": {}}
        send_text(api, chat_id,
                  "¡Hola! Voy a ayudarte a crear tu *hoja de presentación* 📄\n\n"
                  + FIELD_PROMPTS[FIELDS[0]])
        sessions[chat_id]["step"] = FIELDS[0]
        return

    # ── Sin sesión activa ─────────────────────────────────────────────────
    if not session:
        send_text(api, chat_id,
                  "Escribe */portada* para crear una hoja de presentación.")
        return

    step = session.get("step")

    # ── Recibiendo campos de texto ────────────────────────────────────────
    if step in FIELDS and text_msg:
        session["data"][step] = text_msg
        nxt = next_field(step)

        if nxt:
            session["step"] = nxt
            send_text(api, chat_id, FIELD_PROMPTS[nxt])
        else:
            # Todos los campos completos → pedir PDF
            session["step"] = "waiting_pdf"
            summary = "\n".join(
                f"• *{k.replace('_', ' ').title()}*: {v}"
                for k, v in session["data"].items()
            )
            send_text(api, chat_id,
                      f"✅ Datos registrados:\n\n{summary}\n\n"
                      "Ahora *sube tu documento PDF* y le agregaré la portada al inicio.")
        return

    # ── Recibiendo el PDF ─────────────────────────────────────────────────
    if step == "waiting_pdf" and file_url and "pdf" in mime_type.lower():
        send_text(api, chat_id, "⏳ Recibido, generando tu portada...")

        data = session["data"]

        # Rutas temporales
        cover_path    = os.path.join(TEMP_DIR, f"cover_{chat_id}.pdf")
        original_path = os.path.join(TEMP_DIR, f"original_{chat_id}.pdf")
        final_path    = os.path.join(TEMP_DIR, f"final_{chat_id}.pdf")

        # Descargar el PDF del usuario
        download_file(file_url, original_path)

        # Generar portada
        generate_cover(
            alumno=data.get("alumno", ""),
            maestro=data.get("maestro", ""),
            materia=data.get("materia", ""),
            tema=data.get("tema", ""),
            grado_grupo=data.get("grado_grupo", ""),
            fecha=data.get("fecha", ""),
            output_path=cover_path,
        )

        # Unir portada + documento
        prepend_cover_to_pdf(cover_path, original_path, final_path)

        # Enviar resultado
        send_file(api, chat_id, final_path,
                  f"📎 Aquí está tu documento con la hoja de presentación, {data.get('alumno', '')} 🎓")

        # Limpiar sesión y archivos temporales
        del sessions[chat_id]
        for p in [cover_path, original_path, final_path]:
            try:
                os.remove(p)
            except OSError:
                pass
        return

    # ── PDF inesperado o tipo incorrecto ──────────────────────────────────
    if step == "waiting_pdf" and file_url and "pdf" not in mime_type.lower():
        send_text(api, chat_id,
                  "⚠️ Ese archivo no es un PDF. Por favor sube un archivo con extensión *.pdf*.")
        return

    # ── Mensaje inesperado ────────────────────────────────────────────────
    if step in FIELDS:
        send_text(api, chat_id, f"Por favor escribe el valor para: {FIELD_PROMPTS[step]}")


# ─────────────────────────────────────────────────────────────────────────────
# Bucle principal (polling)
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Bot de Hojas de Presentación — UAT")
    print("=" * 60)

    if INSTANCE_ID == "TU_INSTANCE_ID_AQUI":
        print("\nDEBES configurar INSTANCE_ID y API_TOKEN en el archivo .env")
        print("Obtén los tuyos gratis en https://green-api.com\n")
        return

    api = API.GreenAPI(INSTANCE_ID, API_TOKEN)
    print(f"OK - Conectado a instancia {INSTANCE_ID}")
    print("Escanea el QR en el panel de Green API con WhatsApp.")
    print("Esperando mensajes... (Ctrl+C para detener)\n")

    while True:
        try:
            response = api.receiving.receiveNotification()
            if response and response.get("body"):
                notification = response["body"]
                msg_type = notification.get("messageData", {}).get("typeMessage", "")

                if msg_type in ("textMessage", "extendedTextMessage",
                                "documentMessage", "imageMessage"):
                    # Envolvemos en el formato que espera handle_message
                    handle_message(api, {"body": {
                        "senderData": notification.get("senderData", {}),
                        "messageData": notification.get("messageData", {}),
                    }})

                # Eliminar la notificación de la cola
                receipt_id = response.get("receiptId")
                if receipt_id:
                    api.receiving.deleteNotification(receipt_id)

        except KeyboardInterrupt:
            print("\nBot detenido.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            import time
            time.sleep(3)


if __name__ == "__main__":
    main()
