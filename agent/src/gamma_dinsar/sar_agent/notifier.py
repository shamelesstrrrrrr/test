from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any


def load_getenv_file(getenv_path: str | None = None) -> None:
    path = Path(getenv_path) if getenv_path else Path(__file__).parent / ".getenv"

    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and value:
            os.environ.setdefault(key, value)


def send_qq_mail(
    title: str,
    content: str,
    user_env: str = "QQ_MAIL_USER",
    auth_code_env: str = "QQ_MAIL_AUTH_CODE",
    to_env: str = "QQ_MAIL_TO",
) -> str:
    mail_user = os.environ.get(user_env)
    auth_code = os.environ.get(auth_code_env)
    mail_to = os.environ.get(to_env)

    if not mail_user:
        return f"QQ 邮件通知失败：未找到环境变量 {user_env}"

    if not auth_code:
        return f"QQ 邮件通知失败：未找到环境变量 {auth_code_env}"

    if not mail_to:
        return f"QQ 邮件通知失败：未找到环境变量 {to_env}"

    message = MIMEText(content, "plain", "utf-8")
    message["From"] = mail_user
    message["To"] = mail_to
    message["Subject"] = title

    try:
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=20) as smtp:
            smtp.login(mail_user, auth_code)
            smtp.sendmail(mail_user, [mail_to], message.as_string())
    except Exception as exc:
        return f"QQ 邮件通知失败：{exc}"

    return f"QQ 邮件通知发送成功：{mail_to}"


def notify_from_inputs(
    inputs: dict[str, Any],
    title: str,
    content: str,
) -> str:
    if not bool(inputs.get("notify_enabled", False)):
        return "通知未启用"

    channel = str(inputs.get("notify_channel", "qq_mail")).lower()

    if channel == "qq_mail":
        return send_qq_mail(
            title=title,
            content=content,
            user_env=str(inputs.get("qq_mail_user_env", "QQ_MAIL_USER")),
            auth_code_env=str(inputs.get("qq_mail_auth_code_env", "QQ_MAIL_AUTH_CODE")),
            to_env=str(inputs.get("qq_mail_to_env", "QQ_MAIL_TO")),
        )

    return f"通知发送失败：未知通知方式 {channel}"