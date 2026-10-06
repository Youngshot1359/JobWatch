import argparse
import json
import logging
from pathlib import Path

import yaml

from . import emailer, sources
from .models import Job
from .scoring import Taxonomy, score_job

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("jobwatch")


def _yaml(name):
    return yaml.safe_load((ROOT / "config" / name).read_text())


def run(sample=False, dry_run=False, send_email=True):
    settings, skills, companies = _yaml("settings.yaml"), _yaml("skills.yaml"), _yaml("companies.yaml")
    tax = Taxonomy(skills)

    if sample:
        raw = [Job(**j) for j in json.loads((ROOT / "tests" / "sample_jobs.json").read_text())]
    else:
        raw = sources.fetch_all(settings, companies)

    uniq = {}
    for j in raw:
        uniq.setdefault(j.key, j)          # first source wins (direct ATS sources are fetched first)
    results = [score_job(j, tax, settings) for j in uniq.values()]
    scored = [r for r in results if not r.excluded]
    log.info("%d unique, %d scored (%d excluded)", len(uniq), len(scored), len(results) - len(scored))

    state_path = ROOT / "state" / "seen.json"
    seen = set(json.loads(state_path.read_text())) if state_path.exists() else set()
    new = sorted((r for r in scored if r.job.key not in seen), key=lambda r: -r.score)

    mn, nm, cap = settings["min_score"], settings["near_miss_score"], settings["max_per_section"]
    top = [r for r in new if r.score >= mn][:cap]
    near = [r for r in new if nm <= r.score < mn][:cap]
    fallback = [r for r in new if r.score < nm][: settings["fallback_top_n"]]
    stats = {"fetched": len(raw), "scored": len(scored), "new": len(new)}

    subject, html_body, text_body = emailer.render(top, near, fallback, stats, mn)
    csv_text = emailer.scorecard_csv(scored)
    (ROOT / "output").mkdir(exist_ok=True)
    (ROOT / "output" / "scorecard.csv").write_text(csv_text)
    (ROOT / "output" / "preview.html").write_text(html_body)
    print(subject)

    if dry_run or not send_email:
        print("dry run: wrote output/preview.html and output/scorecard.csv (no email sent, state untouched)")
        return top, near
    emailer.send(subject, html_body, text_body, csv_text)
    state_path.parent.mkdir(exist_ok=True)
    seen |= {r.job.key for r in top + near}
    state_path.write_text(json.dumps(sorted(seen)))
    print("email sent")
    return top, near


def cli():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Daily skill-matched job digest")
    ap.add_argument("--sample", action="store_true", help="use tests/sample_jobs.json instead of the network")
    ap.add_argument("--dry-run", action="store_true", help="write preview.html/scorecard.csv, don't email")
    a = ap.parse_args()
    run(sample=a.sample, dry_run=a.dry_run)
