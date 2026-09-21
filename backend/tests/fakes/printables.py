"""Printables GraphQL boundary with the supported capture/download field contract.

Unlike a canned response, this fake rejects removed selections before returning
metadata or links. It deliberately models only the two operations capture uses.
"""

from __future__ import annotations

import re

import httpx


class PrintablesTransport:
    async def request(
        self, method: str, url: str, *, json: dict, **kwargs
    ) -> httpx.Response:
        query = json["query"]
        variables = json["variables"]
        errors = []
        if re.search(r"\b(title|username|code|fileId)\b", query):
            errors.append({"message": "Cannot query removed field"})
        user = re.search(r"\buser\s*\{([^}]+)\}", query)
        if user and "name" in user.group(1).split():
            errors.append({"message": "Cannot query name on User"})
        if errors:
            payload = {"errors": errors}
        elif "getDownloadLink" in query:
            assert variables["printId"] == "3161"
            assert variables["source"] == "model_detail"
            payload = {
                "data": {
                    "getDownloadLink": {
                        "ok": True,
                        "output": {
                            "link": None,
                            "files": [
                                {
                                    "id": file_id,
                                    "link": f"https://files.printables.test/{file_id}.stl",
                                }
                                for group in variables["files"]
                                for file_id in group["ids"]
                            ],
                        },
                    }
                }
            }
        else:
            assert variables == {"id": "3161"}
            payload = {
                "data": {
                    "print": {
                        "id": "3161",
                        "name": "Widget",
                        "user": {"id": "100", "handle": "designer"},
                        "license": {"id": "1", "name": "CC BY"},
                        "stls": [{"id": "file-1", "name": "part.stl", "fileSize": 100}],
                        "gcodes": [],
                        "slas": [],
                        "otherFiles": [],
                    }
                }
            }
        return httpx.Response(200, json=payload, request=httpx.Request(method, url))
