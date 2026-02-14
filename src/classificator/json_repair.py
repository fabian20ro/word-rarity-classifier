from __future__ import annotations


def repair(raw: str) -> str:
    s1 = _remove_line_comments(raw)
    s2 = _fix_trailing_decimal_points(s1)
    s3 = _close_unclosed_structures(s2)
    return _remove_trailing_commas(s3)


def _remove_line_comments(input_text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(input_text):
        ch = input_text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == "/" and i + 1 < len(input_text) and input_text[i + 1] == "/":
            while out and out[-1] == " ":
                out.pop()
            j = input_text.find("\n", i)
            if j == -1:
                break
            i = j
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _fix_trailing_decimal_points(input_text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    for i, ch in enumerate(input_text):
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            continue

        if ch == "." and i > 0 and input_text[i - 1].isdigit():
            nxt = input_text[i + 1] if i + 1 < len(input_text) else None
            if nxt is None or not nxt.isdigit():
                out.append(".0")
                continue
        out.append(ch)
    return "".join(out)


def _close_unclosed_structures(input_text: str) -> str:
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in input_text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                if stack and stack[-1] == '"':
                    stack.pop()
            continue

        if ch == '"':
            in_string = True
            stack.append('"')
        elif ch == "{":
            stack.append("{")
        elif ch == "[":
            stack.append("[")
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()

    closers = {"{": "}", "[": "]", '"': '"'}
    suffix = "".join(closers[s] for s in reversed(stack))
    return input_text + suffix


def _remove_trailing_commas(input_text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    pending_comma = False

    for ch in input_text:
        if in_string:
            if pending_comma:
                out.append(",")
                pending_comma = False
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            if pending_comma:
                out.append(",")
                pending_comma = False
            in_string = True
            out.append(ch)
            continue

        if ch == ",":
            pending_comma = True
            continue

        if ch in "]}":
            pending_comma = False
            out.append(ch)
            continue

        if ch.isspace() and pending_comma:
            continue

        if pending_comma:
            out.append(",")
            pending_comma = False
        out.append(ch)

    if pending_comma:
        out.append(",")
    return "".join(out)
