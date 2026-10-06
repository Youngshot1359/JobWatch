import json, sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobwatch.models import Job
from jobwatch.scoring import Taxonomy, score_job

ROOT = Path(__file__).resolve().parent.parent
settings = yaml.safe_load((ROOT / "config/settings.yaml").read_text())
tax = Taxonomy(yaml.safe_load((ROOT / "config/skills.yaml").read_text()))
R = {j["id"]: score_job(Job(**j), tax, settings) for j in json.loads((ROOT / "tests/sample_jobs.json").read_text())}


def test_perfect_security_fit_clears_90():
    assert R["1"].score >= 90, R["1"]
    assert R["8"].score >= 90, R["8"]

def test_data_eng_is_strong_but_honest_about_adjacent_skills():
    assert 75 <= R["2"].score < 95

def test_java_staff_role_is_low():
    assert R["3"].score < 40

def test_sales_title_excluded():
    assert R["4"].excluded

def test_non_us_excluded():
    assert R["7"].excluded == "location"

def test_clearance_and_seniority_penalised():
    assert R["6"].score < R["1"].score - 25
    assert any("clearance" in n for n in R["6"].notes)

def test_family_labels():
    assert R["1"].family.startswith("Security")
    assert R["2"].family.startswith("Data")

if __name__ == "__main__":
    for k, r in R.items():
        print(k, r.job.title[:38].ljust(38), "EXCL:"+r.excluded if r.excluded else f"{r.score:5.1f}  {r.family:20} notes={r.notes}")
