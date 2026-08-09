from __future__ import annotations

from notifier import load_getenv_file, send_qq_mail


def main() -> None:
    load_getenv_file()

    result = send_qq_mail(
        title="InSAR Agent 测试邮件",
        content="如果你收到这封邮件，说明 QQ 邮箱通知配置成功。",
    )

    print(result)


if __name__ == "__main__":
    main()