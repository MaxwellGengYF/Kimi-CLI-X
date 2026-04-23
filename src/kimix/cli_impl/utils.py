_server_mode = False


def server_mode() -> bool:
    return _server_mode


def _input(text: str, text_arr: list[str]) -> str:
    if text_arr is None or len(text_arr) == 0:
        return input(text)
    v = text_arr.pop(0)
    return v


def _split_text(lines: list[str]) -> list[str]:
    text_arr: list[str] = []
    current_text: list[str] = []
    for line in lines:
        strip_line = line.strip()
        if len(strip_line) == 0:
            continue
        if strip_line.startswith('/'):
            if current_text:
                text_arr.append('\n'.join(current_text))
                current_text = []
            if len(strip_line) > 1:
                text_arr.append(strip_line)
        else:
            current_text.append(line)
    if current_text:
        text_arr.append('\n'.join(current_text))
    return text_arr
