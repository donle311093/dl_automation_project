import re


_TOKEN = re.compile(r'<([^<>\s]+)>')


def resolve(command: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(context.get(key, match.group(0)))
    return _TOKEN.sub(replace, command)


def find_unresolved(command: str) -> list[str]:
    """Return all <token> names that appear in command."""
    return _TOKEN.findall(command)
