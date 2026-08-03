"""AI 故障诊断 — 调用 DeepSeek API 分析告警数据。"""
from __future__ import annotations

import json
import logging
import os

import requests

logger = logging.getLogger("gateway.diagnoser")

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"


def diagnose(alert_message: str, recent_data: list[dict], api_key: str | None = None) -> str | None:
    """将告警信息 + 近期数据发给 DeepSeek，返回故障诊断结论。"""
    key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not key or key.startswith("${"):
        logger.warning("DEEPSEEK_API_KEY not set, skipping AI diagnosis")
        return None

    # 精简近期数据，控制 token
    samples = recent_data[-20:] if len(recent_data) > 20 else recent_data
    data_preview = json.dumps(
        [{"t": d.get("timestamp"), "temp": d.get("temperature"), "hum": d.get("humidity"), "st": d.get("state")}
         for d in samples],
        ensure_ascii=False,
    )

    prompt = (
        "你是一个物联网故障诊断专家。收到以下告警，请分析可能原因并给出排查建议。100 字以内。\n\n"
        f"告警信息: {alert_message}\n\n"
        f"最近传感器数据:\n{data_preview}\n\n"
        "输出格式（纯文本，不需要 markdown）:\n"
        "可能原因: ...\n排查建议: ..."
    )

    try:
        resp = requests.post(
            DEEPSEEK_URL,
            json={
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": "你是一个物联网故障诊断专家。回答简洁专业。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 300,
            },
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            body = resp.json()
            return body["choices"][0]["message"]["content"].strip()
        else:
            logger.warning(f"DeepSeek API error {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Diagnosis request failed: {e}")
        return None
