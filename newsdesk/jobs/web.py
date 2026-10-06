"""Small dependency-free web application for public vacancy intake and apply redirects.

Deploy this behind HTTPS. Set JOBS_ADMIN_TOKEN to a long random value; newsroom
clients use it only for the private editorial API. No applicant details are accepted.
"""

from __future__ import annotations

from dataclasses import fields
from html import escape
import json
import os
import hmac
from urllib.parse import parse_qs

from .config import load_publications
from .models import Vacancy
from .repository import JobsRepository
from .service import JobsService


MAX_BODY = 96_000


def _html_page(title: str, body: str, *, status: str = "200 OK"):
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
:root{{--ink:#10213a;--muted:#53657c;--blue:#1769e0;--pale:#edf5ff;--line:#ccdaec;--red:#d92d2d}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(145deg,#eaf4ff,#f8fbff);font:16px/1.45 Arial,sans-serif;color:var(--ink)}}
.hero{{background:#10213a;color:white;padding:26px 20px;border-top:7px solid #ed3b35}} .wrap{{max-width:920px;margin:auto}} h1{{margin:0 0 7px;font-size:clamp(28px,5vw,44px)}}
.card{{background:white;margin:24px auto;padding:clamp(20px,4vw,38px);border:1px solid var(--line);border-radius:18px;box-shadow:0 14px 34px #173b6818}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}} .wide{{grid-column:1/-1}} label{{display:block;font-weight:700;margin-bottom:6px}}
input,select,textarea{{width:100%;padding:12px 13px;border:1px solid #9db0c8;border-radius:9px;font:inherit;background:white}} textarea{{min-height:120px;resize:vertical}}
.check{{display:flex;gap:10px;align-items:flex-start;font-weight:400}} .check input{{width:auto;margin-top:5px}} .note{{color:var(--muted)}} .error{{background:#fff0f0;border-left:5px solid var(--red);padding:14px;margin-bottom:18px}}
button{{border:0;border-radius:10px;background:var(--blue);color:white;font-weight:700;font-size:17px;padding:14px 22px;cursor:pointer}} .privacy{{font-size:14px;color:var(--muted)}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}}}
</style></head><body>{body}</body></html>"""
    return status, [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(page.encode())))], page.encode()


def _field(label, name, value="", *, kind="text", required=True, wide=False, options=(), maxlength=0, hint=""):
    req = " required" if required else ""
    cls = "wide" if wide else ""
    if options:
        control = "<select name='%s'%s><option value=''>Select…</option>%s</select>" % (
            name, req, "".join(f"<option{' selected' if item == value else ''}>{escape(item)}</option>" for item in options))
    elif kind == "textarea":
        control = f"<textarea name='{name}'{req}{f' maxlength={maxlength}' if maxlength else ''}>{escape(value)}</textarea>"
    else:
        control = f"<input type='{kind}' name='{name}' value='{escape(value)}'{req}{f' maxlength={maxlength}' if maxlength else ''}>"
    help_text = f"<div class='privacy'>{escape(hint)}</div>" if hint else ""
    return f"<div class='{cls}'><label>{escape(label)}</label>{control}{help_text}</div>"


def form_page(publication, values=None, errors=()):
    values = values or {}
    areas = publication.core_areas + (("Outside the core area",) if publication.allow_outside_area else ())
    error_html = "" if not errors else "<div class='error'><strong>Please check the form:</strong><ul>" + "".join(f"<li>{escape(x)}</li>" for x in errors) + "</ul></div>"
    form = [
        _field("Job title", "job_title", values.get("job_title", ""), wide=True, maxlength=100, hint="2–14 words"),
        _field("Area", "area", values.get("area", ""), options=areas),
        _field("Town, village or work location", "location_detail", values.get("location_detail", ""), maxlength=120),
        _field("Employer display name", "employer_name", values.get("employer_name", ""), maxlength=100),
        _field("Employer legal name", "employer_legal_name", values.get("employer_legal_name", ""), required=False),
        _field("Companies House number", "company_number", values.get("company_number", ""), required=False),
        _field("Employer website", "employer_website", values.get("employer_website", ""), kind="url", required=False),
        _field("Salary or pay range", "salary_text", values.get("salary_text", ""), maxlength=100, hint="For example: £25,000–£28,000 per year"),
        _field("Hours", "hours_text", values.get("hours_text", ""), maxlength=100, hint="For example: 37 hours per week"),
        _field("Contract type", "contract_type", values.get("contract_type", ""), options=["Permanent", "Fixed term", "Temporary", "Apprenticeship", "Contract", "Casual", "Volunteer"]),
        _field("Workplace type", "workplace_type", values.get("workplace_type", ""), options=["On site", "Hybrid", "Remote"]),
        _field("Number of positions", "positions", values.get("positions", "1"), kind="number"),
        _field("Closing date", "closing_date", values.get("closing_date", ""), kind="date"),
        _field("Vacancy description", "description", values.get("description", ""), kind="textarea", wide=True, maxlength=1400, hint="40–180 words. Describe the duties factually."),
        _field("Requirements", "requirements", values.get("requirements", ""), kind="textarea", required=False, wide=True, maxlength=700, hint="Optional; 5–80 words when completed."),
        _field("Benefits", "benefits", values.get("benefits", ""), kind="textarea", required=False, wide=True, maxlength=500, hint="Optional; 3–60 words when completed."),
        _field("Apply URL", "application_url", values.get("application_url", ""), kind="url", required=False),
        _field("Or application email", "application_email", values.get("application_email", ""), kind="email", required=False),
        _field("Your name", "submitter_name", values.get("submitter_name", "")),
        _field("Your work email", "submitter_email", values.get("submitter_email", ""), kind="email"),
        _field("Your phone", "submitter_phone", values.get("submitter_phone", ""), kind="tel", required=False),
        "<input name='website_address' tabindex='-1' autocomplete='off' style='position:absolute;left:-9999px'>",
    ]
    for name, text in (
        ("submitter_authorised", "I am authorised by the employer to submit this vacancy."),
        ("genuine_vacancy_confirmed", "I confirm this is a genuine vacancy with no fee to apply."),
        ("equality_confirmed", "I confirm the wording complies with equality law."),
        ("terms_accepted", "I accept the advertising and privacy terms."),
    ):
        form.append(f"<label class='check wide'><input type='checkbox' name='{name}' value='yes' required><span>{escape(text)}</span></label>")
    body = f"""<header class='hero'><div class='wrap'><h1>{escape(publication.page_name)}</h1><div>Advertise a vacancy for editorial review</div></div></header>
<main class='wrap card'>{error_html}<p class='note'>Area appears near the top of every advert. Applications go directly to the employer; we do not accept or retain applicant information.</p>
<form method='post' class='grid'>{''.join(form)}<div class='wide privacy'>We retain advertiser contact details for verification and administration. Apply-button reporting is aggregate clicks only.</div><div class='wide'><button type='submit'>Submit vacancy for review</button></div></form></main>"""
    return _html_page(f"Advertise | {publication.page_name}", body)


class JobsWebApp:
    def __init__(self, repository=None, publications=None, admin_token=None):
        self.publications = publications or load_publications()
        self.service = JobsService(repository=repository or JobsRepository(), publications=self.publications)
        self.admin_token = admin_token if admin_token is not None else os.environ.get("JOBS_ADMIN_TOKEN", "")

    def __call__(self, environ, start_response):
        try:
            status, headers, body = self._dispatch(environ)
        except Exception:
            status, headers, body = _html_page("Unavailable", "<main class='wrap card'><h1>Service unavailable</h1><p>Please try again later.</p></main>", status="500 Internal Server Error")
        start_response(status, headers)
        return [body]

    def _dispatch(self, env):
        method, path = env.get("REQUEST_METHOD", "GET"), env.get("PATH_INFO", "/").rstrip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) == 3 and parts[:2] == ["jobs", "advertise"]:
            key = parts[2]; publication = self.publications.get(key)
            if not publication: return _html_page("Not found", "<main class='wrap card'>Publication not found.</main>", status="404 Not Found")
            if method == "GET": return form_page(publication)
            if method == "POST": return self._submit(env, publication)
        if len(parts) == 2 and parts[0] == "apply" and method == "GET":
            try: destination = self.service.apply_destination(parts[1])
            except LookupError: return _html_page("Vacancy unavailable", "<main class='wrap card'><h1>This vacancy is not currently open.</h1></main>", status="404 Not Found")
            return "302 Found", [("Location", destination), ("Cache-Control", "no-store")], b""
        if parts[:3] == ["api", "v1", "vacancies"] and method == "GET":
            if not self._authorised(env): return self._json({"error": "unauthorised"}, "401 Unauthorized")
            query = parse_qs(env.get("QUERY_STRING", "")); key = query.get("publication", [""])[0]
            statuses = tuple(filter(None, query.get("status", [""])[0].split(",")))
            return self._json({"vacancies": [v.to_dict() for v in self.service.repository.list(key, statuses=statuses)], "clicks": self.service.repository.click_totals(key)})
        if len(parts) == 6 and parts[:3] == ["api", "v1", "vacancies"] and method == "POST":
            if not self._authorised(env): return self._json({"error": "unauthorised"}, "401 Unauthorized")
            vacancy_id, action = parts[3], parts[5]
            if parts[4] != "actions": return self._json({"error": "not_found"}, "404 Not Found")
            length = min(int(env.get("CONTENT_LENGTH") or 0), 16_385)
            if length > 16_384: return self._json({"error": "too_large"}, "413 Payload Too Large")
            try: payload = json.loads(env["wsgi.input"].read(length) or b"{}")
            except (ValueError, TypeError): return self._json({"error": "invalid_json"}, "400 Bad Request")
            try:
                if action == "approve": vacancy = self.service.approve(vacancy_id, editor=str(payload.get("editor") or "NewsDesk editor"))
                elif action == "reject": vacancy = self.service.reject(vacancy_id, editor=str(payload.get("editor") or "NewsDesk editor"), reason=str(payload.get("reason") or ""))
                elif action == "request_changes": vacancy = self.service.request_changes(vacancy_id, editor=str(payload.get("editor") or "NewsDesk editor"), reason=str(payload.get("reason") or ""))
                elif action == "update":
                    vacancy, issues = self.service.update(vacancy_id, editor=str(payload.get("editor") or "NewsDesk editor"), changes=dict(payload.get("changes") or {}))
                    return self._json({"vacancy": vacancy.to_dict(), "issues": [issue.message for issue in issues]})
                elif action == "metricool": vacancy = self.service.mark_metricool(vacancy_id, metricool_id=str(payload.get("metricool_id") or ""), editor=str(payload.get("editor") or "NewsDesk editor"))
                else: return self._json({"error": "unknown_action"}, "404 Not Found")
            except (ValueError, LookupError) as exc:
                return self._json({"error": str(exc)}, "409 Conflict")
            return self._json({"vacancy": vacancy.to_dict()})
        return _html_page("Not found", "<main class='wrap card'>Page not found.</main>", status="404 Not Found")

    def _submit(self, env, publication):
        length = min(int(env.get("CONTENT_LENGTH") or 0), MAX_BODY + 1)
        if length > MAX_BODY: return _html_page("Too large", "<main class='wrap card'>Submission too large.</main>", status="413 Payload Too Large")
        values = {k: v[0].strip() for k, v in parse_qs(env["wsgi.input"].read(length).decode("utf-8"), keep_blank_values=True).items()}
        if values.get("website_address"): return _html_page("Thank you", "<main class='wrap card'><h1>Thank you</h1></main>")
        data = {field.name: values[field.name] for field in fields(Vacancy) if field.name in values}
        data.update(publication_key=publication.key, positions=int(values.get("positions") or 1), outside_core_area=values.get("area") == "Outside the core area")
        for name in ("submitter_authorised", "genuine_vacancy_confirmed", "equality_confirmed", "terms_accepted"):
            data[name] = values.get(name) == "yes"
        vacancy, issues = self.service.submit(Vacancy.from_dict(data))
        blocking = [issue.message for issue in issues if issue.blocking]
        if blocking: return form_page(publication, values, blocking)
        return _html_page("Vacancy submitted", f"<header class='hero'><div class='wrap'><h1>Vacancy submitted</h1></div></header><main class='wrap card'><h2>Thank you</h2><p>Your reference is <strong>{escape(vacancy.vacancy_id[:10].upper())}</strong>.</p><p>The advert will be checked by an editor before it can appear.</p></main>")

    def _authorised(self, env):
        supplied = env.get("HTTP_AUTHORIZATION", "").removeprefix("Bearer ").strip()
        return bool(self.admin_token) and hmac.compare_digest(supplied, self.admin_token)

    @staticmethod
    def _json(payload, status="200 OK"):
        body = json.dumps(payload, ensure_ascii=False).encode()
        return status, [("Content-Type", "application/json"), ("Content-Length", str(len(body)))], body


application = JobsWebApp()
