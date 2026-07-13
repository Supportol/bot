MESSAGE_LIMIT = 4000


def split_message_blocks(
    blocks: list[str],
    header: str,
    *,
    continuation_header: str,
    footer: str = "",
    limit: int = MESSAGE_LIMIT,
) -> list[str]:
    """Разбивает длинный текст на части для Telegram, сохраняя целые блоки."""
    messages: list[str] = []
    current = header

    for block in blocks:
        if not block:
            continue
        part = block if block.endswith("\n\n") else f"{block}\n\n"
        if len(current) + len(part) > limit and current.strip():
            messages.append(current.rstrip())
            current = continuation_header + part
        else:
            current += part

    if footer:
        if len(current) + len(footer) > limit and current.strip():
            messages.append(current.rstrip())
            current = continuation_header + footer
        else:
            current += footer

    if current.strip():
        messages.append(current.rstrip())

    return messages or [header.rstrip()]


async def answer_long_blocks(
    message,
    blocks: list[str],
    header: str,
    *,
    continuation_header: str,
    footer: str = "",
    **kwargs,
) -> None:
    for part in split_message_blocks(
        blocks,
        header,
        continuation_header=continuation_header,
        footer=footer,
    ):
        await message.answer(part, **kwargs)
