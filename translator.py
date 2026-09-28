"""메일 번역.

두 갈래를 순서대로 시도한다.
  1) 이 컴퓨터에서 도는 Ollama (localhost:11434)
       - 키가 필요 없고 인터넷 없이 된다. 대신 10초쯤 걸린다.
       - qwen 계열은 한↔영 번역이 좋다(실제 메일로 확인함).
  2) Gemini API 키
       - 1~2초로 빠르다. 대신 키가 있어야 한다.
둘 다 없으면 그렇다고 알려 준다. 조용히 실패하면 왜 안 되는지 알 수 없다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434"
# 무거운 모델을 먼저 잡으면 첫 응답이 너무 늦다. 가벼운 쪽부터 본다.
PREFERRED_MODELS = ("qwen3:8b", "qwen2.5:7b", "gemma3:4b", "llama3.1:8b")

PROMPT = (
    "다음 이메일을 자연스러운 한국어로 번역해라. "
    "번역문만 출력하고 설명이나 머리말은 붙이지 마라.\n\n---\n{text}\n---"
)

# 메일이 길면 번역이 한없이 느려진다. 읽는 데 필요한 앞부분만 옮긴다.
# 로컬 모델은 글자 수가 늘면 시간이 가파르게 는다(직접 잼: 361자 23초, 913자 149초).
# 요지를 파악하는 데는 1500자면 충분하다.
MAX_CHARS_LOCAL = 1500
MAX_CHARS_CLOUD = 6000


def _ollama_models(timeout: int = 3) -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def ollama_available() -> bool:
    return bool(_ollama_models())


def _pick_model(available: list[str]) -> str:
    for want in PREFERRED_MODELS:
        for have in available:
            if have == want or have.startswith(want.split(":")[0] + ":"):
                return have
    return available[0] if available else ""


def _translate_ollama(text: str, timeout: int = 180) -> str:
    models = _ollama_models()
    model = _pick_model(models)
    if not model:
        raise RuntimeError("쓸 수 있는 모델이 없습니다.")

    payload = {
        "model": model,
        "prompt": PROMPT.format(text=text),
        "stream": False,
        # qwen 계열의 '생각 과정'을 끄면 훨씬 빠르다
        "think": False,
        "options": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("response") or "").strip()


def _translate_gemini(text: str) -> str:
    from runtime_config import GEMINI_API_KEY

    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini 키가 없습니다.")
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"):
        try:
            result = client.models.generate_content(
                model=model, contents=PROMPT.format(text=text)
            )
            return (getattr(result, "text", "") or "").strip()
        except Exception:
            continue
    raise RuntimeError("Gemini 가 응답하지 않았습니다.")


def available() -> dict:
    """지금 쓸 수 있는 번역 수단."""
    from runtime_config import GEMINI_API_KEY

    return {
        "ollama": ollama_available(),
        "gemini": bool(GEMINI_API_KEY),
    }


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n…(이하 생략)"


def translate(text: str) -> dict:
    """한국어로 옮긴다. {'text', 'engine'} 을 돌려준다.

    빠른 쪽을 먼저 쓴다. Gemini 는 1~2초, 이 컴퓨터의 모델은 20초~2분이다.
    키가 있으면 굳이 기다릴 이유가 없고, 없으면 느려도 되긴 된다.
    """
    from runtime_config import GEMINI_API_KEY

    body = (text or "").strip()
    if not body:
        raise ValueError("번역할 내용이 없습니다.")

    errors = []

    if GEMINI_API_KEY:
        try:
            out = _translate_gemini(_clip(body, MAX_CHARS_CLOUD))
            if out:
                return {"text": out, "engine": "Gemini"}
        except Exception as exc:
            errors.append(f"Gemini: {exc}")

    if ollama_available():
        try:
            out = _translate_ollama(_clip(body, MAX_CHARS_LOCAL))
            if out:
                return {"text": out, "engine": "이 컴퓨터의 모델"}
        except Exception as exc:
            errors.append(f"로컬 모델: {exc}")

    raise RuntimeError(
        "번역할 방법이 없습니다. 설정에서 Gemini 키를 넣거나 Ollama 를 켜 주세요."
        + (f" ({' / '.join(errors)})" if errors else "")
    )
