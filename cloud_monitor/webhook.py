"""Webhook 推送 - 将监控结果发送到指定 URL（自动分段）"""

import json
import logging
import time
from urllib import request, error

logger = logging.getLogger(__name__)

MAX_TEXT_LEN = 4800


def _send_one(url: str, content: str) -> bool:
    """发送单条消息"""
    payload = json.dumps({
        "msgtype": "text",
        "text": {"content": content},
    }).encode("utf-8")

    req = request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            logger.debug("Webhook response: %s", body)
            return resp.status == 200
    except error.HTTPError as e:
        logger.warning("Webhook HTTP error %s: %s", e.code, e.read().decode())
        return False
    except Exception as e:
        logger.warning("Webhook send failed: %s", e)
        return False


def _split_text(content: str, limit: int = MAX_TEXT_LEN) -> list[str]:
    """按段落边界拆分长文本，每段不超过 limit 字符"""
    if len(content) <= limit:
        return [content]

    chunks: list[str] = []
    current = ""

    for line in content.split("\n"):
        candidate = current + ("\n" if current else "") + line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            if len(line) > limit:
                while len(line) > limit:
                    chunks.append(line[:limit])
                    line = line[limit:]
                current = line
            else:
                current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def send_webhook(url: str, content: str) -> bool:
    """发送文本到 webhook URL，长文本自动分段发送，返回是否全部成功"""
    chunks = _split_text(content)
    total = len(chunks)
    all_ok = True

    for i, chunk in enumerate(chunks):
        if total > 1:
            header = f"[{i + 1}/{total}]\n"
            chunk = header + chunk

        ok = _send_one(url, chunk)
        if not ok:
            all_ok = False
            logger.warning("Webhook chunk %d/%d failed", i + 1, total)

        if i < total - 1:
            time.sleep(0.5)

    return all_ok
