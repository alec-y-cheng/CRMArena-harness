"""Small serialization helpers for EWM IR objects."""

import json
from typing import Any, Dict, List, Mapping


class Serializable:
    """Mixin for simple JSON-serializable IR containers."""

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue
            data[key] = to_plain(value)
        return data

    def to_json(self, **kwargs: Any) -> str:
        """Serialize this IR object to JSON for logs and replay artifacts."""

        return json.dumps(self.to_dict(), **kwargs)


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


def ensure_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Serializable):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": value}


def string_list(value: Any) -> List[str]:
    out = []
    for item in ensure_list(value):
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def object_list(value: Any) -> List[Dict[str, Any]]:
    out = []
    for item in ensure_list(value):
        if isinstance(item, Serializable):
            out.append(item.to_dict())
        elif isinstance(item, Mapping):
            out.append(dict(item))
        elif item is not None:
            out.append({"value": item})
    return out
