<p align="center">
  <img src="assets/favicon.png" alt="FitnessMe logo" width="240" />
</p>

# FitnessMe

A personal fitness assistant for LINE: log a workout in your own words, send
an InBody report, and ask about your progress in the same conversation.
Training history and goals persist as structured records that later replies
can look up.

## Why I built it

My workout notes and InBody measurements were scattered across phone notes
and spreadsheets. Before a session, I had to find the last working weight,
reconcile different exercise names, and compare old records by hand. Recording
each workout in a form added friction to a habit I wanted to keep simple.

FitnessMe keeps the input familiar—mixed Chinese and English, shorthand,
multiple set groups, or a report photo—and makes it useful later. An initial
import brought 60 training days of existing notes into the same database.
I built and operate it as a personal production project, refining it through
ongoing use. It is a training companion, not a medical or certified coaching
service.

## In use

One chat workflow: capture → understand → recall.
The screenshots below are cropped conversation excerpts with names and raw
InBody measurements redacted. Click an image to enlarge it.

### Capture workouts

Log a self-directed workout or a coach-led session using the notation you
already use. The reply makes the recorded exercises, weights, reps, and sets
visible for review, including different weights within one exercise.

| Self-directed workout logging | Coach-led workout logging |
| --- | --- |
| [<img src="assets/linebot/sample-2.jpg" alt="A self-directed workout message converted into a structured record" width="280" />](assets/linebot/sample-2.jpg) | [<img src="assets/linebot/sample-3.jpg" alt="A coach-led workout message converted into a structured record" width="280" />](assets/linebot/sample-3.jpg) |

### Understand and plan

A scheduled check-in asks about today's plan using recent training and active
conditions as context. Report photos can become body-composition records;
goals agreed in the conversation are stored for future interactions.

| Daily check-in |
| --- |
| [<img src="assets/linebot/sample-1.jpg" alt="A LINE daily check-in and exercise-plan reply" width="280" />](assets/linebot/sample-1.jpg) |

| InBody extraction | Calorie goals |
| --- | --- |
| [<img src="assets/linebot/sample-6.jpg" alt="An InBody report extraction reply with metrics redacted" width="280" />](assets/linebot/sample-6.jpg) | [<img src="assets/linebot/sample-7.jpg" alt="A calorie recommendation and a recorded daily intake goal" width="280" />](assets/linebot/sample-7.jpg) |

### Recall progress

Ask for a previous best or an exercise family such as deadlifts. The bot can
retrieve related variants, their record dates, and next targets, then record
a new result in the same conversation.

| PR history query | Deadlift history and goals |
| --- | --- |
| [<img src="assets/linebot/sample-4.jpg" alt="A personal-record query and update in LINE" width="280" />](assets/linebot/sample-4.jpg) | [<img src="assets/linebot/sample-5.jpg" alt="Deadlift history and next targets in LINE" width="280" />](assets/linebot/sample-5.jpg) |

## Architecture

```mermaid
flowchart LR
    line[LINE text or image] --> auth[Signature + fail-closed allowlist]
    auth --> input{Message type}
    input -->|Text| context[Context builder<br/>profile · date · recent history]
    input -->|Image| vision[Vision extraction]
    vision --> context
    context --> llm[Gemini via LiteLLM<br/>multi-round tool calling]
    llm <--> tools[Application tools]
    tools <--> db[(Postgres)]
    llm --> reply[Sanitised LINE reply]
    reply --> line
```

The model interprets text and images, selects tools, and produces summaries
and suggestions. Tools read and write the user's structured records; code
calculates PRs and next weight targets, scopes data access, skips existing
training dates during historical imports, and applies retention policies.
Relative dates are interpreted by the model using an explicit current-date
and timezone context, then parsed by the application. Advice and extracted
values remain model outputs that the user needs to review.

## Engineering notes

- **Stack:** Python 3.12, FastAPI, SQLAlchemy async, LiteLLM, Gemini, LINE Messaging API, Supabase Postgres/Storage, Docker, and GitHub Actions.
- **Fitness-specific data rules:** [workout services](src/services/workout.py) retain set groups, weight units, per-side loads, and session types. PR comparisons normalise weights and treat lower assistance as progress on assisted exercises; next weight targets follow a fixed increment rule.
- **Queries across turns and tools:** [the message handler](src/line/handler.py) supplies recent conversation history and runs a bounded tool-calling loop. Exercise-name and alias searches let the model look up related variants before querying their records.
- **Context from stored state:** [prompt assembly](src/llm/prompts.py) includes the current date, profile, active goals, and pending daily interaction. Image-specific instructions are included when an image is being processed.
- **Reliability from real failures:** missed records, date confusion, and empty replies led to broader search, explicit date context, retry tiers, and rule-based fallbacks. [Regression tests](tests/) cover assisted PRs, historical dates, multi-round tool calls, empty responses, and tool-syntax leakage into chat.
- **Access and data lifecycle:** the LINE allowlist is fail-closed, and data tools receive the authenticated `user_id`. Chat history is retained for 7 days; raw inputs and daily interactions for 90 days. Photos live behind a storage interface, with metadata and storage keys in Postgres.
- **Delivery and operation:** [GitHub Actions](.github/workflows/deploy.yml) runs tests before building and deploying the Docker image. The appendix documents the schema, Admin API, VM setup, and routine operations.

## Quick start

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A LINE Messaging API channel and an LLM provider key for a working bot

### Run locally

```bash
uv sync
cp .env.example .env
# Fill in only the values needed for your local setup.
uv run uvicorn src.main:app --reload
```

The default development database is SQLite. The app creates tables and seeds
the exercise catalogue at startup. See [`.env.example`](.env.example) for all
configuration variables.

### Run tests

```bash
uv run pytest
```

### Useful commands

```bash
# Seed the exercise catalogue manually (normally done at startup).
uv run python -m scripts.seed

# Import a local history file after configuring an authorised LINE user.
uv run python -m scripts.import_history <LINE_USER_ID>
```

Historical-import input must follow
[`docs/import-template.txt`](docs/import-template.txt). Private source records,
unredacted photos, databases, and environment files are excluded from version
control; the reviewed README screenshots live in `assets/linebot/`.

## Repository layout

```text
src/
  auth/       LINE identity and allowlist checks
  db/         SQLAlchemy models and database setup
  line/       webhook and push-message integration
  llm/        prompts, model client, tools, and output sanitisation
  services/   workout, profile, image, scheduling, and admin workflows
  storage/    local and Supabase storage adapters
tests/        unit and integration-style tests
deploy/       Docker Compose and Caddy configuration
assets/       README visual assets
  favicon.png FitnessMe logo
  linebot/    redacted LINE workflow screenshots
docs/         import-file template
```

## Deployment

The production setup uses Docker Compose with Caddy, Supabase, and GitHub
Actions. The workflow runs tests, builds an image, deploys it to a configured
host, and injects runtime configuration from GitHub Actions secrets. Do not
commit `.env`, databases, private exported records, or unredacted images.

## Appendix

<details>
<summary><strong>Data model</strong></summary>

The source of truth is [`src/db/models.py`](src/db/models.py). The database has
20 tables across identity, user state, training, body composition, interaction
logs, and the seeded exercise dictionary.

```mermaid
erDiagram
    users ||--o{ training_sessions : performs
    users ||--o{ personal_records : holds
    users ||--o{ body_compositions : measures
    users ||--o{ meal_logs : records
    users ||--o{ user_images : owns
    users ||--o{ user_conditions : has
    users ||--o{ user_goals : sets
    users ||--o{ raw_records : creates
    users ||--o{ chat_messages : sends
    users ||--o{ daily_interactions : receives

    training_sessions ||--o{ session_exercises : contains
    training_sessions ||--o{ cardio_records : contains
    training_sessions ||--o{ user_conditions : source
    training_sessions ||--o{ raw_records : links
    session_exercises ||--o{ exercise_sets : contains
    exercises ||--o{ session_exercises : matches
    exercises ||--o{ exercise_aliases : has
    exercises ||--o{ personal_records : tracks
    exercises ||--o{ exercise_muscles : maps
    muscle_groups ||--o{ exercise_muscles : maps
    muscle_groups ||--o{ muscle_group_aliases : has
    exercises ||--o{ user_conditions : relates_to
    body_compositions ||--o{ body_segments : contains
    user_images o|--o| meal_logs : source
```

- `training_sessions` → `session_exercises` → `exercise_sets` captures a
  workout without flattening weight progressions.
- `personal_records` caches normalised best weights so PR replies do not need
  to recompute every historical set.
- `exercise_muscles` is the explicit many-to-many junction between exercises
  and muscle groups; `muscle_group_aliases` supports fuzzy muscle queries.
- Image bytes are stored outside Postgres; `user_images` retains only metadata
  and a storage key.
- Event dates represent the actual training or measurement day, rather than
  upload time.
- `raw_records`, `chat_messages`, and `daily_interactions` use different
  retention periods.

</details>

<details>
<summary><strong>Admin API</strong></summary>

Both endpoints require `X-API-Key` using `ADMIN_API_KEY`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/admin/import-history` | Import dated free-form records for one authorised LINE user. Returns `202` and processes in the background. |
| `POST` | `/admin/delete-records` | Delete training, cardio, body-composition, meal, and PR data in an inclusive date range. |

The history importer is idempotent per user and training date. Its file format
is documented in [`docs/import-template.txt`](docs/import-template.txt).

```bash
curl -X POST https://your-server.com/admin/import-history \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -F "line_user_id=U..." \
  -F "file=@records.txt"

curl -X POST https://your-server.com/admin/delete-records \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"line_user_id":"U...","start_date":"2025-05-12","end_date":"2025-05-14"}'
```

</details>

<details>
<summary><strong>Deployment and operations</strong></summary>

**Target stack:** GCP e2-micro, Docker Compose, Caddy, Supabase Postgres and
Storage, plus GitHub Actions. A push to `main` runs tests, builds and pushes an
image to GHCR, transfers Compose/Caddy configuration, writes runtime settings
from GitHub Actions secrets, then runs `docker compose pull && docker compose up -d`.

### One-time host bootstrap

On a new Ubuntu VM, install Docker Compose, add a 2 GB swap file (the e2-micro
has 1 GB RAM), and create the deployment directory:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Install Docker Engine from Docker's official apt repository.
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER  # Log out and back in before using Docker without sudo.
mkdir -p ~/fitness-me
```

Create a dedicated SSH key for GitHub Actions and add its public half to
`~/.ssh/authorized_keys`. Store the private half only in the `VM_SSH_KEY`
repository secret.

### Required GitHub Actions secrets

`VM_HOST`, `VM_USER`, `VM_SSH_KEY`, `LINE_CHANNEL_SECRET`,
`LINE_CHANNEL_ACCESS_TOKEN`, `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`,
`DATABASE_URL`, `STORAGE_PROVIDER`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
`SUPABASE_BUCKET`, `ALLOWED_USER_IDS`, `ADMIN_API_KEY`, `ADMIN_LINE_USER_ID`,
`BASE_URL`, `TIMEZONE`, and `DOMAIN`.

`ALLOWED_USER_IDS` is intentionally fail-closed: an empty value allows no one
to invoke the bot. Use a stable hostname and point the LINE webhook at
`https://<your-domain>/webhook` after the first successful deployment.

### Day-2 operations

| Task | Command or action |
| --- | --- |
| Ship a change | Push to `main`. |
| Rotate a secret | Update the GitHub Action secret, then re-run the workflow. |
| Tail application logs | `ssh <vm> 'docker compose -f ~/fitness-me/docker-compose.yml logs -f app'` |
| Tail proxy logs | Use the same command with `caddy` in place of `app`. |
| Rebuild a VM | Repeat host bootstrap, update `VM_HOST` if needed, then re-run the workflow. |

</details>

## License

Source is available for viewing and evaluation only. See [LICENSE](LICENSE).
