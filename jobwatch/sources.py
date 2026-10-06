"""Job fetchers. Every fetcher returns list[Job] and never raises (errors are logged)."""
import html
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from .models import Job

log = logging.getLogger("jobwatch")
HEADERS = {"User-Agent": "jobwatch-personal/1.0 (personal job search)"}
TIMEOUT = 25


def clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<(script|style).*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _get(url, **kw):
    r = requests.get(url, headers={**HEADERS, **kw.pop("headers", {})}, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- Greenhouse
def greenhouse(slug: str) -> list[Job]:
    try:
        data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    except Exception as e:
        log.warning("greenhouse/%s skipped: %s", slug, e)
        return []
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        out.append(Job("greenhouse", str(j["id"]), j.get("title", ""), slug.title(), loc,
                       j.get("absolute_url", ""), clean(j.get("content", "")),
                       remote="remote" in loc.lower(), posted=(j.get("updated_at") or "")[:10]))
    return out


# --------------------------------------------------------------------- Lever
def lever(slug: str) -> list[Job]:
    try:
        data = _get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    except Exception as e:
        log.warning("lever/%s skipped: %s", slug, e)
        return []
    out = []
    for j in data:
        cat = j.get("categories") or {}
        loc = cat.get("location") or ""
        parts = [j.get("descriptionPlain", "")]
        parts += [f"{l.get('text', '')} {clean(l.get('content', ''))}" for l in j.get("lists", [])]
        parts.append(j.get("additionalPlain", ""))
        out.append(Job("lever", j["id"], j.get("text", ""), slug.title(), loc, j.get("hostedUrl", ""),
                       " ".join(parts), remote=(j.get("workplaceType") == "remote" or "remote" in loc.lower())))
    return out


# --------------------------------------------------------------------- Ashby
def ashby(slug: str) -> list[Job]:
    try:
        data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"})
    except Exception as e:
        log.warning("ashby/%s skipped: %s", slug, e)
        return []
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        loc = j.get("location") or ""
        comp = ((j.get("compensation") or {}).get("compensationTierSummary")) or ""
        out.append(Job("ashby", j.get("id", ""), j.get("title", ""), slug.title(), loc, j.get("jobUrl", ""),
                       j.get("descriptionPlain") or clean(j.get("descriptionHtml", "")),
                       remote=bool(j.get("isRemote")), posted=(j.get("publishedAt") or "")[:10], salary=comp))
    return out


# -------------------------------------------------------------------- JSearch
def jsearch(cfg: dict) -> list[Job]:
    key = os.getenv("JSEARCH_API_KEY")
    if not key:
        log.warning("jsearch enabled but JSEARCH_API_KEY not set")
        return []
    out = []
    for q in cfg.get("queries", []):
        try:
            data = _get("https://api.openwebninja.com/jsearch/search-v2", headers={"x-api-key": key},
                        params={"query": q, "country": "us", "date_posted": cfg.get("date_posted", "3days")})
        except Exception as e:
            log.warning("jsearch '%s' failed: %s", q, e)
            continue
        # Response envelope isn't documented on the marketing page - accept the common shapes.
        rows = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(rows, dict):
            rows = rows.get("jobs") or rows.get("data") or rows.get("results") or []
        for j in rows or []:
            lo, hi = j.get("job_min_salary"), j.get("job_max_salary")
            out.append(Job("jsearch", j.get("job_id", ""), j.get("job_title", ""), j.get("employer_name", ""),
                           j.get("job_location") or ", ".join(filter(None, [j.get("job_city"), j.get("job_state")])),
                           j.get("job_apply_link", ""),
                           (j.get("job_description") or "") + " " + " ".join(j.get("required_technologies") or []),
                           remote=bool(j.get("job_is_remote")), posted=(j.get("job_posted_at_datetime_utc") or "")[:10],
                           salary=f"${lo:,.0f}-${hi:,.0f}" if lo and hi else ""))
    return out


# --------------------------------------------------------------------- Adzuna
def adzuna(cfg: dict) -> list[Job]:
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        log.warning("adzuna enabled but ADZUNA_APP_ID/ADZUNA_APP_KEY not set")
        return []
    out = []
    for q in cfg.get("queries", []):
        try:
            data = _get("https://api.adzuna.com/v1/api/jobs/us/search/1",
                        params={"app_id": app_id, "app_key": app_key, "what": q, "results_per_page": 50,
                                "max_days_old": cfg.get("max_days_old", 3), "content-type": "application/json"})
        except Exception as e:
            log.warning("adzuna '%s' failed: %s", q, e)
            continue
        for j in data.get("results", []):
            loc = (j.get("location") or {}).get("display_name", "")
            out.append(Job("adzuna", str(j.get("id")), j.get("title", ""), (j.get("company") or {}).get("display_name", ""),
                           loc, j.get("redirect_url", ""), clean(j.get("description", "")),
                           remote="remote" in (j.get("title", "") + loc).lower(), posted=(j.get("created") or "")[:10],
                           truncated=True))
    return out


# ------------------------------------------------------------------ orchestrate
def fetch_all(settings: dict, companies: dict) -> list[Job]:
    src = settings.get("sources", {})
    tasks = []
    if src.get("greenhouse"):
        tasks += [(greenhouse, s) for s in companies.get("greenhouse", [])]
    if src.get("lever"):
        tasks += [(lever, s) for s in companies.get("lever", [])]
    if src.get("ashby"):
        tasks += [(ashby, s) for s in companies.get("ashby", [])]
    jobs: list[Job] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(lambda t: t[0](t[1]), tasks):
            jobs += res
    if (src.get("jsearch") or {}).get("enabled"):
        jobs += jsearch(src["jsearch"])
    if (src.get("adzuna") or {}).get("enabled"):
        jobs += adzuna(src["adzuna"])
    log.info("fetched %d raw postings from %d board calls", len(jobs), len(tasks))
    return jobs
