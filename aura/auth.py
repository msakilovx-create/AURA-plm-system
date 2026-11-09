"""Аккаунты AURA PLM: вход, хеш пароля, шифрование документов."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime
from pathlib import Path

from .model import uid

ROUNDS = 180_000
MAGIC = "AURAENC1"


def users_path() -> Path:
    root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    folder = root / "AURA_PLM"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "users.json"


def load_users() -> dict:
    path = users_path()
    if not path.exists():
        return {"users": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"users": []}


def save_users(data: dict) -> None:
    data.setdefault("users", [])
    data.setdefault("delete_requests", [])
    if data["users"] and not any(u.get("role") == "admin" for u in data["users"]):
        data["users"][0]["role"] = "admin"
    users_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_admin(user: dict | None) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    rec = find_user(user.get("username") or "")
    return bool(rec and rec.get("role") == "admin")


def admin_name() -> str:
    for u in load_users().get("users") or []:
        if u.get("role") == "admin":
            return str(u.get("username") or "")
    users = load_users().get("users") or []
    return str(users[0].get("username") or "") if users else ""


def _hash_pw(password: str, salt: bytes, rounds: int = ROUNDS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds, dklen=32)


def derive_key(password: str, salt: bytes, rounds: int = ROUNDS) -> bytes:
    return _hash_pw(password, salt, rounds)


def find_user(username: str) -> dict | None:
    name = username.strip().casefold()
    for u in load_users().get("users") or []:
        if str(u.get("username") or "").casefold() == name:
            return u
    return None


def register_user(username: str, password: str, display: str = "") -> dict:
    username = username.strip()
    if len(username) < 2:
        raise ValueError("Логин слишком короткий.")
    if len(password) < 4:
        raise ValueError("Пароль не короче 4 символов.")
    if find_user(username):
        raise ValueError("Такой пользователь уже есть.")
    salt = os.urandom(16)
    data = load_users()
    rec = {
        "id": uid("usr"),
        "username": username,
        "display": (display or username).strip(),
        "salt": salt.hex(),
        "hash": _hash_pw(password, salt).hex(),
        "rounds": ROUNDS,
        "role": "admin" if not (data.get("users") or []) else "user",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data.setdefault("users", []).append(rec)
    save_users(data)
    return rec


def verify_password(record: dict, password: str) -> bool:
    salt = bytes.fromhex(record["salt"])
    rounds = int(record.get("rounds") or ROUNDS)
    expected = bytes.fromhex(record["hash"])
    got = _hash_pw(password, salt, rounds)
    return hmac.compare_digest(expected, got)


def login(username: str, password: str) -> tuple[dict, bytes]:
    rec = find_user(username)
    if not rec or not verify_password(rec, password):
        raise ValueError("Неверный логин или пароль.")
    salt = bytes.fromhex(rec["salt"])
    rounds = int(rec.get("rounds") or ROUNDS)
    return rec, derive_key(password, salt, rounds)


def change_password(username: str, old: str, new: str) -> tuple[dict, bytes]:
    rec, _old_key = login(username, old)
    if len(new) < 4:
        raise ValueError("Новый пароль не короче 4 символов.")
    salt = os.urandom(16)
    rec["salt"] = salt.hex()
    rec["hash"] = _hash_pw(new, salt).hex()
    rec["rounds"] = ROUNDS
    data = load_users()
    users = []
    for u in data.get("users") or []:
        if str(u.get("id")) == rec["id"]:
            users.append(rec)
        else:
            users.append(u)
    data["users"] = users
    save_users(data)
    return rec, derive_key(new, salt, ROUNDS)


def _keystream(key: bytes, iv: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + iv + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_document(plain: str, username: str, key: bytes) -> str:
    data = plain.encode("utf-8")
    iv = os.urandom(16)
    ct = bytes(a ^ b for a, b in zip(data, _keystream(key, iv, len(data))))
    tag = hmac.new(key, iv + ct, hashlib.sha256).digest()
    payload = base64.b64encode(iv + tag + ct).decode("ascii")
    return "\n".join([
        MAGIC,
        f"owner={username}",
        f"payload={payload}",
        "",
    ])


def is_encrypted(text: str) -> bool:
    return (text or "").lstrip().startswith(MAGIC)


def peek_owner(text: str) -> str | None:
    if not is_encrypted(text):
        return None
    for line in text.splitlines()[:8]:
        if line.startswith("owner="):
            return line.split("=", 1)[1].strip()
    return None


def decrypt_document(text: str, username: str, key: bytes) -> str:
    owner = peek_owner(text)
    if owner and owner.casefold() != username.strip().casefold():
        raise PermissionError(f"Файл принадлежит пользователю «{owner}».")
    payload = ""
    for line in text.splitlines():
        if line.startswith("payload="):
            payload = line.split("=", 1)[1].strip()
            break
    if not payload:
        raise ValueError("Повреждённый защищённый файл.")
    blob = base64.b64decode(payload)
    if len(blob) < 48:
        raise ValueError("Повреждённый защищённый файл.")
    iv, tag, ct = blob[:16], blob[16:48], blob[48:]
    expect = hmac.new(key, iv + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expect):
        raise PermissionError("Неверный пароль или файл повреждён.")
    plain = bytes(a ^ b for a, b in zip(ct, _keystream(key, iv, len(ct))))
    return plain.decode("utf-8")


def add_delete_request(username: str, payload: dict) -> dict:
    data = load_users()
    req = {
        "id": uid("del"),
        "username": username,
        "status": "pending",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **payload,
    }
    data.setdefault("delete_requests", []).append(req)
    save_users(data)
    return req


def list_delete_requests(status: str | None = "pending") -> list:
    reqs = load_users().get("delete_requests") or []
    if status:
        return [r for r in reqs if r.get("status") == status]
    return list(reqs)


def set_delete_request(req_id: str, status: str) -> dict | None:
    data = load_users()
    found = None
    for r in data.get("delete_requests") or []:
        if r.get("id") == req_id:
            r["status"] = status
            r["resolved"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            found = r
            break
    save_users(data)
    return found


def user_vault_root(username: str) -> Path:
    from .vault import slug

    return Path.home() / "Documents" / "AURA_Vault" / slug(username, "user")
