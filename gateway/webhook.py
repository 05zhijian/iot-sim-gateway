"""飞书 Webhook 推送。"""
from __future__ import annotations

import json
import logging

import requests

logger = logging.getLogger("gateway.webhook")


def send_alert(webhook_url: str, alert: dict, ai_diagnosis: str | None = None) -> bool:
    """推送告警到飞书群/机器人。"""
    if not webhook_url:
        logger.info("No webhook URL configured, skipping push")
        return False

    title = f"🚨 {alert['severity'].upper()} — {alert['message']}"
    content = [
        {"tag": "text", "text": f"设备: {alert['device_id']}\n"},
        {"tag": "text", "text": f"时间: {alert.get('timestamp', '')}\n"},
        {"tag": "text", "text": f"当前值: {alert.get('current_value', 'N/A')}\n"},
        {"tag": "text", "text": f"阈值: {alert.get('threshold', 'N/A')}\n"},
    ]
    if ai_diagnosis:
        content.append({"tag": "text", "text": f"\n🤖 AI 诊断:\n{ai_diagnosis}"})

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "red" if alert["severity"] == "critical" else "yellow",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "".join(
                        c["text"] if isinstance(c, dict) else c for c in content
                    )},
                }
            ],
        },
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Alert pushed to Feishu")
            return True
        else:
            logger.warning(f"Webhook failed: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return False
