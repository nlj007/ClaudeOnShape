"""HTTP client for the Onshape REST API — HMAC-SHA256 signed requests.

Works with the non-versioned /api/ prefix; server returns v1 flat (`btType`)
format when Accept is application/vnd.onshape.v2+json. Writes require
`sourceMicroversion` for optimistic concurrency.
"""
import hashlib
import hmac
import random
import string
import base64
from datetime import datetime, timezone
from urllib.parse import urlencode
import requests
import os
from dotenv import load_dotenv

load_dotenv()


class OnshapeClient:
    def __init__(self):
        self.access_key = os.environ["ONSHAPE_ACCESS_KEY"]
        self.secret_key = os.environ["ONSHAPE_SECRET_KEY"]
        self.base_url = os.getenv("ONSHAPE_BASE_URL", "https://cad.onshape.com")

    def _nonce(self) -> str:
        chars = string.digits + string.ascii_letters
        return "".join(random.choice(chars) for _ in range(25))

    def _auth_headers(self, method: str, path: str, query: str) -> dict:
        nonce = self._nonce()
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        content_type = "application/json"

        to_sign = "\n".join([
            method.lower(),
            nonce.lower(),
            date.lower(),
            content_type,
            path.lower(),
            query.lower(),
            "",
        ])

        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        return {
            "Content-Type": content_type,
            "Date": date,
            "On-Nonce": nonce,
            "Authorization": f"On {self.access_key}:HmacSHA256:{signature}",
            "Accept": "application/vnd.onshape.v2+json",
        }

    def request(self, method: str, path: str, query: dict = None, body: dict = None) -> dict:
        query = query or {}
        query_string = urlencode(query)
        api_path = f"/api{path}"
        url = f"{self.base_url}{api_path}"
        if query_string:
            url += f"?{query_string}"

        headers = self._auth_headers(method, api_path, query_string)

        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body is not None else None,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # --- Part Studio: features ---

    def get_features(self, did: str, wid: str, eid: str) -> dict:
        return self.request("GET", f"/partstudios/d/{did}/w/{wid}/e/{eid}/features")

    def add_feature(self, did: str, wid: str, eid: str, feature: dict) -> dict:
        """Create a new feature. Returns the created feature with its assigned featureId."""
        return self.request(
            "POST",
            f"/partstudios/d/{did}/w/{wid}/e/{eid}/features",
            body={"feature": feature},
        )

    def update_features(self, did: str, wid: str, eid: str,
                        features: list, source_microversion: str) -> dict:
        body = {"features": features, "sourceMicroversion": source_microversion}
        return self.request(
            "POST",
            f"/partstudios/d/{did}/w/{wid}/e/{eid}/features/updates",
            body=body,
        )

    def delete_feature(self, did: str, wid: str, eid: str, fid: str) -> dict:
        return self.request(
            "DELETE",
            f"/partstudios/d/{did}/w/{wid}/e/{eid}/features/featureid/{fid}",
        )

    def eval_featurescript(self, did: str, wid: str, eid: str, script: str,
                           queries: list = None) -> dict:
        """Evaluate a FeatureScript expression against a part studio.

        The script must be a FeatureScript function body returning a value; the
        API wraps it in evaluator boilerplate. `queries` are external references
        addressable via `queries` variable inside the script.
        """
        # Onshape expects `queries` as a map<string, list<string>>, not an array.
        # Pass {} when empty — an array triggers a Jackson deserialization 400.
        body = {"script": script, "queries": queries or {}}
        return self.request(
            "POST",
            f"/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript",
            body=body,
        )

    # --- Part Studio: sketches ---

    def get_sketches(self, did: str, wid: str, eid: str) -> dict:
        return self.request("GET", f"/partstudios/d/{did}/w/{wid}/e/{eid}/sketches")

    # --- Parts & metadata ---

    def get_parts(self, did: str, wid: str, eid: str) -> list:
        return self.request("GET", f"/parts/d/{did}/w/{wid}/e/{eid}")

    def get_part_metadata(self, did: str, wid: str, eid: str, part_id: str) -> dict:
        return self.request(
            "GET", f"/parts/d/{did}/w/{wid}/e/{eid}/partid/{part_id}/metadata"
        )

    def update_part_metadata(self, did: str, wid: str, eid: str, part_id: str,
                             updates: dict) -> dict:
        """Update part metadata (name, appearance, etc.). Only changed fields needed."""
        return self.request(
            "POST",
            f"/parts/d/{did}/w/{wid}/e/{eid}/partid/{part_id}/metadata",
            body=updates,
        )
