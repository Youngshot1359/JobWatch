from dataclasses import dataclass, field
import re


@dataclass
class Job:
    source: str
    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    remote: bool = False
    posted: str = ""
    salary: str = ""
    truncated: bool = False  # description is only a snippet (e.g. Adzuna)

    @property
    def key(self) -> str:
        """Cross-source dedupe key."""
        norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
        return f"{norm(self.company)}|{norm(self.title)}|{norm(self.location)}"


@dataclass
class Result:
    job: Job
    score: float
    family: str = "Other"
    matched: list = field(default_factory=list)     # full-credit skills the job asks for
    adjacent: list = field(default_factory=list)    # half-credit skills
    missing: list = field(default_factory=list)     # gap skills the job asks for
    notes: list = field(default_factory=list)       # penalties / warnings
    years_required: int | None = None
    excluded: str = ""
