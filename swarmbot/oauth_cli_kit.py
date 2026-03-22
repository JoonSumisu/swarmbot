from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class _Token:
    account_id: str = ""
    access: str = ""


def get_token() -> _Token:
    return _Token()


def login_oauth_interactive(
    print_fn: Callable[[str], None] | None = None,
    prompt_fn: Callable[[str], str] | None = None,
) -> _Token:
    if print_fn:
        print_fn("oauth_cli_kit stub: OAuth login is not available in swarmbot gateway.")
    return _Token()

