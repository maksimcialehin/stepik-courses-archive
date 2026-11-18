"""Stepik OAuth client and object fetch helpers."""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_HOST = "https://stepik.org"
BATCH_SIZE = 30
MAX_RETRIES = 5


class StepikAPIError(RuntimeError):
    """Raised when the Stepik API returns an unexpected response."""


class StepikClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        username: str | None = None,
        password: str | None = None,
        api_host: str | None = None,
        grant_type: str | None = None,
    ) -> None:
        self.api_host = (api_host or os.getenv("STEPIK_API_HOST") or DEFAULT_API_HOST).rstrip(
            "/"
        )
        self.client_id = (client_id or os.getenv("STEPIK_CLIENT_ID", "")).strip()
        self.client_secret = (client_secret or os.getenv("STEPIK_CLIENT_SECRET", "")).strip()
        self.username = (
            username if username is not None else os.getenv("STEPIK_USERNAME", "")
        ).strip()
        self.password = (
            password if password is not None else os.getenv("STEPIK_PASSWORD", "")
        ).strip()
        self.grant_type = (
            grant_type or os.getenv("STEPIK_GRANT_TYPE", "")
        ).strip().lower() or None
        self._token: str | None = None
        self._session = requests.Session()

    def _resolve_grant_type(self) -> str:
        if self.grant_type in {"password", "client_credentials"}:
            return self.grant_type
        if self.username and self.password:
            return "password"
        return "client_credentials"

    def authenticate(self) -> str:
        if not self.client_id or not self.client_secret:
            raise StepikAPIError(
                "STEPIK_CLIENT_ID and STEPIK_CLIENT_SECRET are required. "
                "Copy .env.example to .env and fill in OAuth credentials."
            )

        grant_type = self._resolve_grant_type()
        data: dict[str, str]
        if grant_type == "password":
            if not self.username or not self.password:
                raise StepikAPIError(
                    "Password grant requires STEPIK_USERNAME and STEPIK_PASSWORD. "
                    "Or set STEPIK_GRANT_TYPE=client_credentials."
                )
            data = {
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
            }
        else:
            data = {"grant_type": "client_credentials"}

        response = self._session.post(
            f"{self.api_host}/oauth2/token/",
            data=data,
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        if response.status_code != 200:
            hint = ""
            body = response.text[:300]
            if response.status_code == 401 and "unauthorized_client" in body:
                hint = (
                    f"\nGrant type used: {grant_type}. "
                    "It must match the Authorization Grant Type of your app at "
                    "https://stepik.org/oauth2/applications/\n"
                    "- For enrolled/paid courses: create an app with grant type "
                    "`password` (Resource owner password-based), keep "
                    "STEPIK_USERNAME/STEPIK_PASSWORD in .env.\n"
                    "- For public content only: app with `client-credentials`, "
                    "clear username/password or set STEPIK_GRANT_TYPE=client_credentials."
                )
            elif response.status_code == 401 and "invalid_client" in body:
                hint = (
                    "\nStepik rejected CLIENT_ID/CLIENT_SECRET (not the login/password).\n"
                    "Open https://stepik.org/oauth2/applications/, open the app, "
                    "re-copy Client id and Client secret into .env, then save.\n"
                    "Common mistakes: secret from another app, truncated paste, "
                    "extra quotes around values."
                )
            elif response.status_code == 401 and "invalid_grant" in body:
                hint = (
                    "\nLogin/password were rejected. Check STEPIK_USERNAME "
                    "(email used on Stepik) and STEPIK_PASSWORD. "
                    "If the password contains # or \\, wrap it in double quotes in .env."
                )
            raise StepikAPIError(
                f"OAuth failed ({response.status_code}): {body}{hint}"
            )

        token = response.json().get("access_token")
        if not token:
            raise StepikAPIError("OAuth response did not include access_token")

        self._token = token
        return token

    @property
    def token(self) -> str:
        if not self._token:
            self.authenticate()
        assert self._token is not None
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _get_json(
        self,
        url: str,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._session.get(
                    url, headers=self._headers(), params=params, timeout=60
                )
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 2**attempt))
                time.sleep(retry_after)
                continue

            if response.status_code >= 500:
                time.sleep(2**attempt)
                last_error = StepikAPIError(
                    f"Server error {response.status_code} for {url}"
                )
                continue

            if response.status_code != 200:
                raise StepikAPIError(
                    f"GET {url} failed ({response.status_code}): {response.text[:300]}"
                )

            return response.json()

        raise StepikAPIError(f"Failed to GET {url} after retries: {last_error}")

    def fetch_object(self, obj_class: str, obj_id: int | str) -> dict[str, Any]:
        # Stepik pluralizes with a trailing "s": course -> courses, step-source -> step-sources
        plural = f"{obj_class}s"
        url = f"{self.api_host}/api/{plural}/{obj_id}"
        payload = self._get_json(url)
        items = payload.get(plural)
        if not items:
            raise StepikAPIError(f"Empty response for {obj_class} id={obj_id}")
        return items[0]

    def fetch_objects(self, obj_class: str, obj_ids: list[int]) -> list[dict[str, Any]]:
        if not obj_ids:
            return []

        plural = f"{obj_class}s"
        objs: list[dict[str, Any]] = []
        for i in range(0, len(obj_ids), BATCH_SIZE):
            chunk = obj_ids[i : i + BATCH_SIZE]
            params = [("ids[]", obj_id) for obj_id in chunk]
            url = f"{self.api_host}/api/{plural}"
            payload = self._get_json(url, params=params)
            objs.extend(payload.get(plural, []))
        return objs

    def iter_pages(self, endpoint: str, params: dict[str, Any] | None = None):
        """Yield items from a paginated list endpoint like /api/courses."""
        page = 1
        base_params = dict(params or {})
        # Infer collection key from endpoint: /api/courses -> courses
        key = endpoint.rstrip("/").rsplit("/", 1)[-1]

        while True:
            page_params = {**base_params, "page": page}
            payload = self._get_json(f"{self.api_host}/api/{key}", params=page_params)
            items = payload.get(key, [])
            if not items:
                break
            yield from items
            meta = payload.get("meta") or {}
            if not meta.get("has_next"):
                break
            page += 1

    def list_enrolled_courses(self) -> list[dict[str, Any]]:
        """Return courses the authenticated user is enrolled in."""
        courses: list[dict[str, Any]] = []
        try:
            for course in self.iter_pages("courses", params={"enrolled": "true"}):
                courses.append(course)
        except StepikAPIError:
            # Fallback: enrollments -> course ids
            enrollment_ids: list[int] = []
            course_ids: list[int] = []
            for enrollment in self.iter_pages("enrollments"):
                enrollment_ids.append(enrollment["id"])
                course_ids.append(enrollment["course"])
            if course_ids:
                courses = self.fetch_objects("course", course_ids)
        return courses
