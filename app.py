"""
EduBot — Flask: UI educativa + API de chat.

- EDUBOT_USE_LLM=1: usa SmolLM2 (u otro) vía Transformers; requiere modelo descargado/accesible.
- Por defecto (sin EDUBOT_USE_LLM): modo demostración sin cargar el modelo (útil en redes con firewall).

Variables de modelo: SMOLLM2_MODEL, SMOLLM2_LOCAL_PATH, SMOLLM2_DISABLE_SSL_VERIFY, etc.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from flask import Flask, jsonify, render_template, request, session

os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")


def _maybe_disable_hf_ssl_verify() -> None:
    flag = os.environ.get("HF_HUB_DISABLE_SSL_VERIFY", "").strip().lower()
    alt = os.environ.get("SMOLLM2_DISABLE_SSL_VERIFY", "").strip().lower()
    if flag in ("1", "true", "yes") or alt in ("1", "true", "yes"):
        os.environ["HF_HUB_DISABLE_SSL_VERIFY"] = "1"


_maybe_disable_hf_ssl_verify()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-cambiar-en-produccion")


@app.errorhandler(Exception)
def handle_exception(e):
    """Siempre devuelve JSON, nunca HTML, para errores no controlados."""
    log.exception("Error no controlado")
    import traceback
    return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "Ruta no encontrada"}), 404

USE_LLM = os.environ.get("EDUBOT_USE_LLM", "0").strip().lower() in ("1", "true", "yes")


def _resolve_model_source() -> str:
    local = os.environ.get("SMOLLM2_LOCAL_PATH", "").strip()
    if local:
        abs_local = os.path.abspath(local)
        if os.path.isdir(abs_local):
            return abs_local
    return os.environ.get("SMOLLM2_MODEL", "HuggingFaceTB/SmolLM2-360M-Instruct")


MODEL_SOURCE = _resolve_model_source()
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "256"))
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "20"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.7"))
TOP_P = float(os.environ.get("TOP_P", "0.9"))
MAX_KB_CHARS = int(os.environ.get("EDUBOT_MAX_KB_CHARS", "12000"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATERIAS_DIR = os.path.join(BASE_DIR, "data", "materias")

# Nombre mostrado en la UI → archivo en data/materias/
SUBJECT_TO_FILE = {
    "Matemáticas": "matematicas.txt",
    "Física": "fisica.txt",
    "Química": "quimica.txt",
    "Lengua": "lengua.txt",
    "Ciencias Naturales": "ciencias_naturales.txt",
    "Ciencias Sociales": "ciencias_sociales.txt",
    "Inglés": "ingles.txt",
}

KB_BLOCK_HEADER = (
    "\n\n--- Base de consulta del área (léela antes de responder; úsala para vocabulario, "
    "enfoque y ejemplos. Si algo no aparece aquí, no inventes lineamientos oficiales: "
    "orienta el razonamiento y sugiere consultar al docente o el material del colegio) ---\n"
)

_load_lock = threading.Lock()
_model = None
_tokenizer = None

log = logging.getLogger(__name__)

EDUBOT_SYSTEM_PROMPT = """Eres EduBot, asistente educativo para estudiantes de 7 a 16 años en Colombia (p. ej. Antioquia).
Tu propósito es guiar el aprendizaje: explicar ideas paso a paso, hacer preguntas cortas para comprobar comprensión,
y sugerir recursos o formas de estudiar. No des soluciones completas de tareas o ejercicios listas para copiar.
Si piden la respuesta directa, orienta el razonamiento. Si no sabes, dilo con honestidad.
Materia de contexto: {subject}. Responde en español, con tono claro, respetuoso y motivador."""


def load_subject_kb(subject: str | None) -> tuple[str, str | None]:
    """Lee el .txt de la materia (o general.txt si no hay materia). Devuelve (texto, nombre de archivo)."""
    if subject and subject in SUBJECT_TO_FILE:
        fn = SUBJECT_TO_FILE[subject]
        path = os.path.join(MATERIAS_DIR, fn)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read(), fn
        log.warning("Falta el archivo de materia: %s", path)
        return "", None
    path_general = os.path.join(MATERIAS_DIR, "general.txt")
    if os.path.isfile(path_general):
        with open(path_general, encoding="utf-8") as f:
            return f.read(), "general.txt"
    return "", None


def build_system_prompt(subject: str | None) -> str:
    """Prompt de sistema + base .txt truncada para el modelo."""
    subj_label = subject or "general (sin materia elegida en la app)"
    base = EDUBOT_SYSTEM_PROMPT.format(subject=subj_label)
    kb, _fname = load_subject_kb(subject)
    if not kb.strip():
        return base
    text = kb
    if len(text) > MAX_KB_CHARS:
        text = (
            text[:MAX_KB_CHARS]
            + "\n... [texto truncado por EDUBOT_MAX_KB_CHARS="
            + str(MAX_KB_CHARS)
            + "]\n"
        )
    return base + KB_BLOCK_HEADER + text


def _trim_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(messages) <= MAX_HISTORY_MESSAGES:
        return messages
    return messages[-MAX_HISTORY_MESSAGES:]


def get_model_and_tokenizer():
    global _model, _tokenizer
    with _load_lock:
        if _model is not None and _tokenizer is not None:
            return _model, _tokenizer
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        log.info("Cargando modelo %s (primera vez puede descargar pesos)...", MODEL_SOURCE)
        tok = AutoTokenizer.from_pretrained(MODEL_SOURCE, trust_remote_code=True)
        dtype = torch.float32
        if torch.cuda.is_available():
            dtype = torch.float16
        m = AutoModelForCausalLM.from_pretrained(
            MODEL_SOURCE,
            trust_remote_code=True,
            dtype=dtype,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        if not torch.cuda.is_available():
            m = m.to("cpu")
        m.eval()
        _tokenizer = tok
        _model = m
        log.info("Modelo listo.")
        return _model, _tokenizer


def _mock_edubot_reply(user_text: str, subject: str | None) -> str:
    """Respuesta pedagógica cuando no hay LLM; invita al razonamiento sin resolver la tarea."""
    subj = subject or "tus materias"
    kb, kb_name = load_subject_kb(subject)
    kb_excerpt = ""
    if kb_name and kb.strip():
        n = 900
        kb_excerpt = (
            f"\n\n--- Extracto de la base cargada ({kb_name}, {len(kb)} caracteres) ---\n"
            f"{kb[:n]}{'…' if len(kb) > n else ''}\n"
            "(Con EDUBOT_USE_LLM=1 el modelo recibe el texto completo en el prompt de sistema.)\n"
        )
    return (
        "En este equipo EduBot está en modo demostración (sin modelo de IA cargado). "
        "Cuando tengas el modelo en otro PC, define la variable de entorno EDUBOT_USE_LLM=1.\n\n"
        f"Para ayudarte en {subj} sin darte la respuesta lista para copiar: "
        "¿qué parte del concepto ya entiendes y en qué punto te atoras? "
        "Si me dices qué intentaste (aunque no te haya salido), te guío con el siguiente paso "
        "y preguntas para que lo descubras tú."
        f"{kb_excerpt}\n"
        f"Tu mensaje fue: «{user_text[:400]}{'…' if len(user_text) > 400 else ''}»"
    )


@app.route("/")
def index():
    return render_template(
        "edubot.html",
        use_llm=USE_LLM,
        model_id=MODEL_SOURCE,
    )


@app.route("/api/status", methods=["GET"])
def api_status():
    sub = session.get("subject")
    kb, kb_file = load_subject_kb(sub)
    return jsonify(
        {
            "use_llm": USE_LLM,
            "model": MODEL_SOURCE if USE_LLM else None,
            "subject": sub,
            "kb_file": kb_file,
            "kb_chars": len(kb),
        }
    )


@app.route("/api/session/subject", methods=["POST"])
def api_session_subject():
    data = request.get_json(silent=True) or {}
    subj = (data.get("subject") or "").strip() or None
    session["subject"] = subj
    return jsonify({"ok": True, "subject": subj})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_text = (data.get("message") or "").strip()
    if not user_text:
        return jsonify({"error": "Mensaje vacío."}), 400

    if "subject" in data and data.get("subject") is not None:
        s = (data.get("subject") or "").strip() or None
        session["subject"] = s

    subject = session.get("subject")
    kb_text, kb_file = load_subject_kb(subject)

    messages = list(session.get("messages", []))
    messages.append({"role": "user", "content": user_text})
    messages = _trim_history(messages)
    session["messages"] = messages

    if not USE_LLM:
        reply = _mock_edubot_reply(user_text, subject)
        messages.append({"role": "assistant", "content": reply})
        session["messages"] = _trim_history(messages)
        return jsonify(
            {
                "reply": reply,
                "mode": "mock",
                "subject": subject,
                "kb_file": kb_file,
                "kb_chars": len(kb_text),
            }
        )

    try:
        model, tokenizer = get_model_and_tokenizer()
    except Exception as e:
        log.exception("Fallo al cargar el modelo")
        return jsonify({"error": f"No se pudo cargar el modelo: {e!s}"}), 500

    import torch

    messages_for_model: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(subject),
        },
        *list(session.get("messages", [])),
    ]

    try:
        prompt_str = tokenizer.apply_chat_template(
            messages_for_model,
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception as e:
        return jsonify({"error": f"Chat template: {e!s}"}), 500

    try:
        encoded = tokenizer(prompt_str, return_tensors="pt")
    except Exception as e:
        return jsonify({"error": f"Tokenización: {e!s}"}), 500

    # Obtener device de forma segura (compatible con transformers 5.x)
    device = getattr(model, "device", None) or torch.device("cpu")
    input_ids = encoded["input_ids"].to(device)
    attention_mask = encoded["attention_mask"].to(device)

    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id else tokenizer.eos_token_id

    try:
        with torch.no_grad():
            out = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=True,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                pad_token_id=pad_id,
                eos_token_id=tokenizer.eos_token_id,
            )
    except Exception as e:
        log.exception("Error en model.generate")
        return jsonify({"error": f"Error generando respuesta: {e!s}"}), 500

    generated = out[0][input_ids.shape[-1]:]
    reply = tokenizer.decode(generated, skip_special_tokens=True).strip()

    messages.append({"role": "assistant", "content": reply})
    session["messages"] = _trim_history(messages)

    return jsonify(
        {
            "reply": reply,
            "mode": "llm",
            "model": MODEL_SOURCE,
            "max_new_tokens": MAX_NEW_TOKENS,
            "subject": subject,
            "kb_file": kb_file,
            "kb_chars": len(kb_text),
        }
    )


@app.route("/api/reset", methods=["POST"])
def reset():
    session.pop("messages", None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)
