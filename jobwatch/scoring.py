"""Skill-first scoring.

score = weighted share of the skills a posting asks for that you actually have,
        (have = 1.0, adjacent = 0.5, gap = 0.0), then bonuses/penalties.
Job titles matter very little on purpose - the skills mentioned drive the score.
"""
import re
import statistics

from .models import Job, Result

CREDIT = {"have": 1.0, "adjacent": 0.5, "gap": 0.0}


def _pat(alias: str) -> re.Pattern:
    return re.compile(r"(?<![\w+#])" + re.escape(alias.lower()) + r"(?![\w+#])", re.I)


class Taxonomy:
    def __init__(self, cfg: dict):
        self.skills = {}
        for name, s in cfg["skills"].items():
            self.skills[name] = {
                "tier": s["tier"], "w": s.get("w", 1), "pats": [_pat(a) for a in s["aliases"]],
                "label": name.replace("_", " "),
            }
        self.families = cfg.get("families", {})


YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*\d{0,2}\s*\+?\s*(?:years|yrs)\b", re.I)
STAFF_RE = re.compile(r"\b(staff|principal|distinguished|director|vp|vice president|head of|manager|architect)\b", re.I)
SENIOR_RE = re.compile(r"\b(senior|sr\.?|lead)\b", re.I)
CLEAR_RE = re.compile(r"(ts/sci|top secret|secret clearance|active (?:secret|clearance)|polygraph|security clearance (?:is )?required|must (?:have|hold) .{0,20}clearance)", re.I)
NON_US = re.compile(r"\b(canada|united kingdom|\buk\b|india|germany|france|ireland|netherlands|spain|poland|brazil|mexico|australia|singapore|japan|israel|emea|apac|europe|latam|london|toronto|berlin|dublin|bangalore|bengaluru)\b", re.I)
US_HINT = re.compile(r"\b(united states|usa|u\.s\.|us-remote|remote - us|remote, us|remote us)\b|,\s*[A-Z]{2}\b", re.I)


def location_ok(job: Job, loc_cfg: dict) -> bool:
    loc = f"{job.location} {job.title}".lower()
    remote = job.remote or "remote" in loc
    if loc_cfg.get("exclude_non_us", True) and NON_US.search(loc) and not US_HINT.search(job.location or ""):
        return False
    if remote and loc_cfg.get("allow_remote", True):
        return True
    need = [t.lower() for t in loc_cfg.get("require_any", [])]
    return True if not need else any(t in f" {loc}" for t in need)


def score_job(job: Job, tax: Taxonomy, settings: dict) -> Result:
    sc = settings["scoring"]
    res = Result(job=job, score=0.0)

    tl = job.title.lower()
    for bad in settings.get("negative_title_keywords", []):
        if re.search(r"\b" + re.escape(bad) + r"\b", tl):
            res.excluded = f"title contains '{bad}'"
            return res
    if not location_ok(job, settings.get("locations", {})):
        res.excluded = "location"
        return res

    text = f"{job.title}\n{job.description}"
    detected = {}
    for name, s in tax.skills.items():
        n = sum(len(p.findall(text)) for p in s["pats"])
        if n:
            title_hit = any(p.search(job.title) for p in s["pats"])
            eff = s["w"] * (2 if title_hit else 1) * (1.25 if n >= 3 else 1)
            detected[name] = eff

    num = den = 0.0
    for name, eff in detected.items():
        s = tax.skills[name]
        den += eff
        num += eff * CREDIT[s["tier"]]
        {"have": res.matched, "adjacent": res.adjacent, "gap": res.missing}[s["tier"]].append(s["label"])

    base = 100 * num / den if den else 0.0
    if len(detected) < sc["min_distinct_skills"]:
        base *= sc["low_evidence_factor"]
        res.notes.append("few recognisable skills in posting (low confidence)")
    if job.truncated:
        res.notes.append("description is a snippet - score is approximate")
    if len(res.matched) < sc["min_have_matches"]:
        base = min(base, 79.0)

    # family label
    best, best_w = "Other", 0.0
    for fam in tax.families.values():
        w = sum(detected.get(s, 0) for s in fam["skills"])
        w += 4 * sum(k in tl for k in fam.get("title_keywords", []))   # title nudges the label only
        if w > best_w:
            best, best_w = fam["label"], w
    res.family = best

    bonus = 0.0
    if any(k in tl for fam in tax.families.values() for k in fam.get("title_keywords", [])):
        bonus = sc["title_bonus"]

    pen = 0.0
    if STAFF_RE.search(job.title):
        pen += sc["penalty_staff"]; res.notes.append("staff/principal/manager-level title")
    elif SENIOR_RE.search(job.title):
        pen += sc["penalty_senior"]; res.notes.append("senior-level title")

    yrs = [int(m.group(1)) for m in YEARS_RE.finditer(job.description) if 0 < int(m.group(1)) <= 15]
    if yrs:
        res.years_required = int(statistics.median(yrs))
        over = max(0, res.years_required - sc["years_ok"])
        if over:
            pen += min(40, over * sc["years_penalty"]); res.notes.append(f"asks ~{res.years_required}+ yrs experience")

    if CLEAR_RE.search(job.description):
        pen += sc["penalty_clearance"]; res.notes.append("security clearance mentioned")

    res.score = round(max(0.0, min(100.0, base + bonus - pen)), 1)
    return res
