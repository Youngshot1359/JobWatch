# JobWatch - daily skill-matched job digest

Pulls fresh postings straight from company job boards (Greenhouse, Lever, Ashby), optionally
JSearch / Adzuna, scores each one by **skill overlap with your resume**, and emails you the
new ones every morning with a scorecard.

## Setup (about 10 minutes)
1. Create a **private** GitHub repo and push this folder to it.
2. Make a Gmail **App Password** (Google Account -> Security -> 2-Step Verification -> App passwords).
3. Repo -> Settings -> Secrets and variables -> Actions -> add:
   `EMAIL_USER` (your gmail), `EMAIL_APP_PASSWORD`, `EMAIL_TO` (where to receive it).
   Optional: `JSEARCH_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`.
4. Actions tab -> *daily-jobwatch* -> **Run workflow** to test. After that it runs daily at 12:00 UTC.

## Run locally
```
pip install -r requirements.txt
python -m jobwatch --sample --dry-run   # offline demo, writes output/preview.html
python -m jobwatch --dry-run            # real fetch, no email
EMAIL_USER=.. EMAIL_APP_PASSWORD=.. python -m jobwatch   # real fetch + email
```

## How scoring works
For each posting, find every skill from `config/skills.yaml` it mentions.
`score = sum(weight x credit) / sum(weight)` over those skills, where credit is
**have = 1, adjacent = 0.5, gap = 0**. Skills in the title count double. Then:
small title bonus (+5), penalties for staff/senior titles, years of experience above 3,
and security-clearance requirements. Needs >= 3 full-credit skills to score above 79.

## Tuning (all in `config/`)
- `skills.yaml` - promote `adjacent` skills to `have` as they become true (SQL, Spark, React...). This is the biggest lever.
- `settings.yaml` - `min_score`, `near_miss_score`, location filter, penalties, negative title words.
- `companies.yaml` - board slugs to watch. Bad slugs are skipped and logged. Companies on Workday (e.g. Akamai) aren't covered.
