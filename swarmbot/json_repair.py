import json
from typing import Any


def loads(text: str, *args: Any, **kwargs: Any) -> Any:
    try:
        return json.loads(text, *args, **kwargs)
    except Exception:
        stripped = text.strip()
        for closing in ("}", "]"):
            idx = stripped.rfind(closing)
            if idx != -1:
                candidate = stripped[: idx + 1]
                try:
                    return json.loads(candidate, *args, **kwargs)
                except Exception:
                    continue
        return {}
