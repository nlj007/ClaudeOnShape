"""Decoder for BTFSValue envelopes returned by /featurescript.

Every FeatureScript value a `eval_featurescript` call returns is wrapped in a
JSON object of the form:

    {
      "btType": "BTFSValue<Map|Array|String|Number|Boolean|...>",
      "typeTag": "<optional FS type hint, e.g. 'Id', 'EntityType'>",
      "value": <raw payload>
    }

Maps look like:

    {btType: "...BTFSValueMap", value: [
        {btType: "BTFSValueMapEntry-2077",
         key:   {btType: "...BTFSValueString", value: "foo"},
         value: {btType: "...BTFSValueNumber", value: 3.14, typeTag: "meter"}},
        ...
    ]}

This module recursively unwraps the envelope into plain Python. It loses the
`typeTag` — if you ever need units or enum names, grab those upstream before
calling `decode()`. For our current use-case (find_faces returns faces with
origin/normal arrays) the tags aren't needed.
"""
from typing import Any


def decode(v: Any) -> Any:
    """Recursively strip BTFSValue envelopes. Returns plain dict/list/scalars."""
    if isinstance(v, dict):
        bt = v.get("btType", "")
        # Map: value is a list of {key, value} BTFSValueMapEntry items.
        if "BTFSValueMap" in bt and "Entry" not in bt:
            out = {}
            for entry in v.get("value", []):
                k = decode(entry.get("key"))
                out[k] = decode(entry.get("value"))
            return out
        # Array: value is a list of BTFSValue* items.
        if "BTFSValueArray" in bt:
            return [decode(x) for x in v.get("value", [])]
        # Scalar wrappers (String, Number, Boolean, etc.) — just unwrap value.
        if "BTFSValue" in bt and "value" in v:
            return v["value"]
        # Top-level eval response {result: <FSValue>, ...} — unwrap result.
        if "result" in v:
            return decode(v["result"])
        # Fallback: plain dict, decode children.
        return {k: decode(vv) for k, vv in v.items()}
    if isinstance(v, list):
        return [decode(x) for x in v]
    return v
