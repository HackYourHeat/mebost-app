# --------------------------------------------------
# LLM Adapter — MEBOST Hải Đăng V1.5
# --------------------------------------------------
# Cải tiến:
#   - Exponential backoff retry (1s, 2s, 4s)
#   - 429 Too Many Requests → wait + retry
#   - Stream → non-stream graceful fallback
#   - Timeout protection
#   - Safe fallback message
# --------------------------------------------------

from __future__ import annotations
import json
import logging
import os
import re
import time

import requests

API_URL          = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME       = os.getenv("MODEL_NAME", "deepseek/deepseek-chat")

_RETRY_DELAYS    = [1, 2, 4]       # exponential backoff (seconds)
_TIMEOUT         = 60              # non-stream request timeout
_STREAM_TIMEOUT  = 90              # stream connection timeout
_EMOTION_TIMEOUT = 20

logger = logging.getLogger("mebost")


def _headers() -> dict:
    """Rebuild headers mỗi lần — đảm bảo đọc API key từ env runtime."""
    return {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}",
        "HTTP-Referer":  "https://mebost.vn",
        "X-Title":       "Mebost",
    }


# --------------------------------------------------
# Non-streaming — retry với exponential backoff
# --------------------------------------------------

def generate_reply(messages: list) -> str:
    """
    Gọi LLM, trả về full text.
    Retry 3 lần với exponential backoff.
    429 → wait theo Retry-After header hoặc delay cố định.
    """
    last_err = None

    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        try:
            return _call_openrouter(messages)

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0

            if status == 429:
                wait = _parse_retry_after(e.response) or delay * 2
                logger.warning("LLM 429 rate limit — wait %.1fs (attempt %d)", wait, attempt)
                time.sleep(wait)
                last_err = e
                continue

            if status in (401, 403):
                logger.error("LLM auth error %d — không retry", status)
                break

            if status >= 500:
                logger.warning("LLM %d server error — retry in %ds (attempt %d)", status, delay, attempt)
                last_err = e
                if attempt < len(_RETRY_DELAYS):
                    time.sleep(delay)
                continue

            # 4xx khác → không retry
            logger.error("LLM HTTP %d: %s", status, e)
            break

        except requests.exceptions.Timeout:
            logger.warning("LLM timeout — retry in %ds (attempt %d)", delay, attempt)
            last_err = Exception("timeout")
            if attempt < len(_RETRY_DELAYS):
                time.sleep(delay)

        except requests.exceptions.RequestException as e:
            logger.warning("LLM network error — retry in %ds (attempt %d): %s", delay, attempt, e)
            last_err = e
            if attempt < len(_RETRY_DELAYS):
                time.sleep(delay)

    logger.error("LLM generate_reply failed after %d attempts: %s", len(_RETRY_DELAYS), last_err)
    return fallback_message()


def _call_openrouter(messages: list) -> str:
    resp = requests.post(
        API_URL,
        headers=_headers(),
        json={"model": MODEL_NAME, "messages": messages, "stream": False},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# --------------------------------------------------
# Streaming — với graceful fallback → non-stream
# --------------------------------------------------

def generate_reply_stream(messages: list):
    """
    Gọi LLM với stream=True, yield từng text chunk.

    Nếu stream thất bại (timeout / 429 / network):
      → fallback sang generate_reply() (non-stream)
      → yield toàn bộ reply một lần

    Caller không cần biết fallback đã xảy ra.
    """
    try:
        yield from _stream_openrouter(messages)

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        logger.warning("stream HTTP %d — fallback to non-stream", status)
        yield from _non_stream_fallback(messages)

    except requests.exceptions.Timeout:
        logger.warning("stream timeout — fallback to non-stream")
        yield from _non_stream_fallback(messages)

    except requests.exceptions.RequestException as e:
        logger.warning("stream network error — fallback to non-stream: %s", e)
        yield from _non_stream_fallback(messages)


def _stream_openrouter(messages: list):
    """Raw SSE stream — raises on error."""
    resp = requests.post(
        API_URL,
        headers=_headers(),
        json={"model": MODEL_NAME, "messages": messages, "stream": True},
        timeout=_STREAM_TIMEOUT,
        stream=True,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8", errors="replace")
        if not decoded.startswith("data: "):
            continue
        payload = decoded[6:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
            text  = chunk["choices"][0].get("delta", {}).get("content", "")
            if text:
                yield text
        except (KeyError, ValueError):
            continue


def _non_stream_fallback(messages: list):
    """Fallback: gọi non-stream rồi yield 1 lần."""
    reply = generate_reply(messages)
    yield reply


# --------------------------------------------------
# Emotion classifier
# --------------------------------------------------

def classify_emotion_llm(text: str) -> dict | None:
    """
    Gọi LLM để detect emotion khi keyword không đủ rõ.
    Trả về {"emotion": ..., "intensity": ...} hoặc None nếu lỗi.
    """
    prompt = (
        "You are an emotion classifier. "
        "Reply ONLY with a JSON object, no explanation, no markdown.\n"
        'Format: {"emotion": "sad|anxious|tired|angry|happy|neutral", "intensity": 1-10}\n\n'
        f"Text: {text[:300]}"
    )
    try:
        resp = requests.post(
            API_URL,
            headers=_headers(),
            json={
                "model":      MODEL_NAME,
                "messages":   [{"role": "user", "content": prompt}],
                "stream":     False,
                "max_tokens": 60,
            },
            timeout=_EMOTION_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        raw = re.sub(r"```[a-z]*", "", raw).strip().strip("`")
        data      = json.loads(raw)
        emotion   = str(data.get("emotion", "neutral")).lower()
        intensity = int(data.get("intensity", 5))
        return {"emotion": emotion, "intensity": max(1, min(10, intensity))}
    except Exception as e:
        logger.warning("classify_emotion_llm failed: %s", e)
        return None


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def fallback_message() -> str:
    return "Đường kết nối đang gián đoạn… Nhưng Hải Đăng vẫn ở đây."


def _parse_retry_after(response) -> float | None:
    """Đọc Retry-After header từ 429 response."""
    try:
        val = response.headers.get("Retry-After")
        if val:
            return float(val)
    except Exception:
        pass
    return None
