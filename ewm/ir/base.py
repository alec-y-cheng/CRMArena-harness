"""Small serialization helpers for EWM IR objects."""

from typing import Any, Dict, List


class Serializable:
    """Mixin for simple JSON-serializable IR containers."""

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue
            data[key] = to_plain(value)
        return data


def to_plain(value: Any) -> Any:
    if isinstance(value, Serializable):
        return value.to_dict()
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    return value


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

