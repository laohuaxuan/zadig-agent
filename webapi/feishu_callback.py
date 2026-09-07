"""飞书事件回调解析（卡片按钮）。"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class CardActionEvent:
    open_id: str
    open_message_id: str
    action: str
    token: str
    event_token: str
    app: str = ""
    v1: bool = False


def _any_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_callback_value(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    return None


def _parse_callback_value_from_behaviors(behaviors: Any) -> dict[str, Any] | None:
    if not isinstance(behaviors, list):
        return None
    for item in behaviors:
        if not isinstance(item, dict):
            continue
        if _any_string(item.get("type")) != "callback":
            continue
        parsed = _parse_callback_value(item.get("value"))
        if parsed:
            return parsed
    return None


def _card_action_from_maps(scope: dict[str, Any], action: dict[str, Any]) -> CardActionEvent:
    value_map = _parse_callback_value(action.get("value"))
    if value_map is None:
        value_map = _parse_callback_value_from_behaviors(action.get("behaviors"))
    if value_map is None:
        raise ValueError("missing action value")
    operator = scope.get("operator") if isinstance(scope.get("operator"), dict) else {}
    context = scope.get("context") if isinstance(scope.get("context"), dict) else {}
    open_id = _any_string(operator.get("open_id")) or _any_string(scope.get("open_id"))
    open_message_id = _any_string(context.get("open_message_id")) or _any_string(scope.get("open_message_id"))
    return CardActionEvent(
        open_id=open_id,
        open_message_id=open_message_id,
        action=_any_string(value_map.get("action")),
        token=_any_string(value_map.get("token")),
        event_token=_any_string(scope.get("token")),
        app=_any_string(value_map.get("app")),
    )


def _callback_event_type(payload: dict[str, Any]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    return _any_string(header.get("event_type")) or _any_string(payload.get("type"))


def _is_v1_flat_card_payload(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("event"), dict):
        return False
    return isinstance(payload.get("action"), dict)


def parse_callback_body(encrypt_key: str, raw: bytes) -> tuple[dict[str, Any], bool]:
    if not raw:
        raise ValueError("empty callback body")
    envelope = json.loads(raw.decode("utf-8"))
    if not isinstance(envelope, dict):
        raise ValueError("invalid callback json")
    challenge = _any_string(envelope.get("challenge"))
    if challenge:
        return {"challenge": challenge}, False
    encrypted = _any_string(envelope.get("encrypt"))
    if encrypted:
        key = encrypt_key.strip()
        if not key:
            raise ValueError("encrypt_key required for encrypted callback")
        plain = _decrypt_encrypt(key, encrypted)
        envelope = json.loads(plain.decode("utf-8"))
        if not isinstance(envelope, dict):
            raise ValueError("invalid decrypted callback json")
        challenge = _any_string(envelope.get("challenge"))
        if challenge:
            return {"challenge": challenge}, True
        return envelope, True
    return envelope, False


def parse_card_action_event(payload: dict[str, Any]) -> CardActionEvent:
    if not isinstance(payload, dict):
        raise ValueError("empty callback payload")
    if _any_string(payload.get("challenge")):
        raise ValueError("challenge")
    event_type = _callback_event_type(payload)
    if event_type in {"card.action.trigger_v1", ""} and _is_v1_flat_card_payload(payload):
        action = payload.get("action")
        if not isinstance(action, dict):
            raise ValueError("missing action")
        event = _card_action_from_maps(payload, action)
        event.v1 = True
        return event
    if event_type and event_type not in {"card.action.trigger", "card.action.trigger_v1"}:
        raise ValueError(f"unsupported event_type: {event_type}")
    event_obj = payload.get("event")
    if not isinstance(event_obj, dict):
        raise ValueError("missing event")
    action = event_obj.get("action")
    if not isinstance(action, dict):
        raise ValueError("missing action")
    parsed = _card_action_from_maps(event_obj, action)
    parsed.v1 = event_type == "card.action.trigger_v1"
    return parsed


def callback_verification_token(payload: dict[str, Any]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    token = _any_string(header.get("token"))
    if token:
        return token
    return _any_string(payload.get("token"))


def _decrypt_encrypt(key: str, encrypted: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key_hash = hashlib.sha256(key.encode("utf-8")).digest()
    raw = base64.b64decode(encrypted)
    if len(raw) < 16:
        raise ValueError("invalid encrypted payload")
    iv = raw[:16]
    data = raw[16:]
    cipher = Cipher(algorithms.AES(key_hash), modes.CBC(iv))
    decryptor = cipher.decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    pad = plain[-1]
    if pad <= 0 or pad > 16:
        raise ValueError("invalid padding")
    return plain[:-pad]
