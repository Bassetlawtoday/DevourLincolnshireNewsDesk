"""Production entry point for the reusable Jobs Desk web service."""

from __future__ import annotations

import os

from waitress import serve

from newsdesk.jobs.web import application


def main():
    if not os.environ.get("JOBS_ADMIN_TOKEN", "").strip():
        raise SystemExit("JOBS_ADMIN_TOKEN must be set to a long random secret.")
    host = os.environ.get("JOBS_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    serve(application, host=host, port=port, threads=8, url_scheme="https")


if __name__ == "__main__":
    main()
