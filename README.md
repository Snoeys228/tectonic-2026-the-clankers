# Payslip Assistant: Trustworthy Payslip Q&A with Gemini RAG

An enterprise payslip Q&A assistant, built as a hackathon prototype. Employees ask questions about their own
payslips in plain language, for example *"Why is my net pay lower this month compared to last month?"* or
*"How many vacation days do I have left?"*. The assistant answers **only from the payslip text**. Every answer
includes a **Trust & Transparency Box** that shows the exact payslip snippets the answer is based on, so anyone
(including the judges) can check it.

- **Backend:** FastAPI, Pydantic v2, and the official `google-genai` SDK (`from google import genai`)
- **Frontend:** a single-page app built with HTML, Tailwind CSS and vanilla JS, served by FastAPI
- **Data:** detailed mock payslips in a Belgian, SD Worx-style format: gross salary, employee social security
  (RSZ/ONSS 13.07%), withholding tax, special social security contribution, net pay, meal vouchers, allowances,
  benefit in kind and legal vacation balance
- **Deployment:** a multi-stage Dockerfile, ready for Google Cloud Run (binds to `$PORT`)

---

## How it works

```
Question + employee id
        |
        v
1. Retrieval (backend/services/retrieval.py)
   - resolves the pay periods: "this month", "last month", "in August", comparisons, year-to-date
   - scores the sections of the employee's OWN payslips (earnings, tax, net pay, leave, ...)
        |
        v
2. Generation (backend/services/ai_service.py)
   - sends the exact section texts as <source id="..."> blocks to Gemini
   - strict system instruction: "You are a trustworthy payroll assistant. Answer strictly based on
     the provided payslip text. If the answer cannot be found, state so clearly."
   - structured JSON output: answer, answer_found, source_ids, confidence
        |
        v
3. Verification
   - discards any source id the model invents
   - checks that every amount in the answer appears in the sources (or is a sum or difference of two
     source amounts); if not, it adds a warning and lowers the confidence
   - confidence = 0.6 x model confidence + 0.4 x retrieval relevance
        |
        v
Answer summary + source snippets + confidence score  ->  UI Trust & Transparency Box
```

If no `GEMINI_API_KEY` is configured, or Gemini is unavailable while `AI_MODE=auto`, a deterministic
**offline extractive engine** (`backend/services/offline_answerer.py`) answers from the structured payslip
data. The demo keeps working without internet access and never invents figures. The UI always shows which
engine produced an answer.

---

## Project structure

```
.
├── backend/
│   ├── main.py                     # FastAPI app: CORS, routes, error handlers, static frontend
│   ├── models.py                   # Pydantic request/response models
│   ├── database.py                 # Mock SD Worx-style payslip records + text rendering
│   ├── config.py                   # Environment/.env configuration
│   ├── services/
│   │   ├── ai_service.py           # Gemini RAG orchestration (google-genai SDK)
│   │   ├── retrieval.py            # Period resolution + section retrieval
│   │   └── offline_answerer.py     # Deterministic fallback answerer
│   └── tests/test_api.py           # API, retrieval and Gemini-path tests (Gemini is mocked)
├── frontend/
│   ├── index.html                  # Single-page app (Tailwind CSS)
│   ├── app.js                      # UI logic, Trust & Transparency Box
│   └── styles.css
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
└── .env.example
```

---

## Local setup

Requirements: Python 3.11 or newer (3.12 recommended).

```bash
# 1. Create a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt  # or requirements.txt for runtime only

# 2. Configure environment variables
cp .env.example .env
# edit .env and set GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)

# 3. Start the server (from the backend directory)
cd backend
uvicorn main:app --reload --port 8080
```

Open <http://localhost:8080> for the app and <http://localhost:8080/docs> for the interactive API
documentation.

Without a `GEMINI_API_KEY`, the app starts in offline extractive mode. The badge in the top bar shows which
mode is active.

### Environment variables

| Variable                 | Default              | Description                                                                 |
|--------------------------|----------------------|-----------------------------------------------------------------------------|
| `GEMINI_API_KEY`         | *(empty)*            | Gemini API key. `GOOGLE_API_KEY` is also accepted.                          |
| `GEMINI_MODEL`           | `gemini-2.5-flash`   | Gemini model used for answers.                                              |
| `AI_MODE`                | `auto`               | `auto`: Gemini with offline fallback. `gemini`: Gemini only, errors return HTTP 502/503/504. `offline`: never call Gemini. |
| `GEMINI_TIMEOUT_SECONDS` | `30`                 | Timeout for one Gemini call.                                                |
| `CORS_ORIGINS`           | `*`                  | Comma-separated allowed origins, e.g. `https://app.example.com`.            |
| `FRONTEND_DIR`           | `../frontend`        | Directory with the static frontend.                                         |
| `LOG_LEVEL`              | `INFO`               | Python log level.                                                           |
| `PORT`                   | `8080`               | Port used by the container (set automatically by Cloud Run).               |

The `.env` file is loaded from the project root or from `backend/`. Real environment variables always take
precedence.

### Run the tests

```bash
cd backend
python -m pytest -q
```

The tests run fully offline. The Gemini path is exercised with a fake client, which covers grounding,
rejection of invented source ids, flagging of unverifiable figures, fallback on rate limits and strict-mode
errors.

---

## API

| Method | Path                                               | Description                                  |
|--------|----------------------------------------------------|----------------------------------------------|
| GET    | `/api/health`                                      | Status, AI mode, whether Gemini is configured |
| GET    | `/api/employees`                                   | Demo employee picker                         |
| GET    | `/api/employees/{employee_id}/payslips`            | Key figures per payslip                      |
| GET    | `/api/employees/{employee_id}/payslips/{YYYY-MM}/text` | Full rendered payslip document           |
| POST   | `/api/ask`                                         | Ask a question (RAG)                         |

Example:

```bash
curl -s -X POST http://localhost:8080/api/ask \
  -H "Content-Type: application/json" \
  -d '{"employee_id": "EMP-100234", "question": "Why is my net pay lower this month compared to last month?"}'
```

Response (shortened):

```json
{
  "answer_summary": "Your net pay for September 2026 is EUR 2,836.60, EUR 211.84 lower than August 2026 ...",
  "answer_found": true,
  "confidence_score": 0.9,
  "source_snippets": [
    {
      "source_id": "PS-202609-EMP100234#net_pay",
      "document_id": "PS-202609-EMP100234",
      "period": "2026-09",
      "period_label": "September 2026",
      "section": "net_pay",
      "section_title": "Net pay",
      "text": "NET PAY CALCULATION - September 2026\nGross salary: EUR 4,001.55 ...",
      "relevance": 1.0,
      "cited": true
    }
  ],
  "employee_id": "EMP-100234",
  "periods_considered": ["2026-08", "2026-09"],
  "mode": "gemini",
  "model": "gemini-2.5-flash",
  "warnings": [],
  "latency_ms": 1432
}
```

Errors always use the same shape: `{"error": "...", "detail": ..., "request_id": "..."}`. The request id is
also returned in the `X-Request-ID` header and written to the logs.

### Demo employees

| Employee id  | Name             | Good demo questions                                                             |
|--------------|------------------|---------------------------------------------------------------------------------|
| `EMP-100234` | Sophie Janssens  | *"Why is my net pay lower this month compared to last month?"* (unpaid leave day, new bike lease, no overtime) |
| `EMP-100587` | Lucas Peeters    | *"How many meal vouchers did I get in August?"*, night shift premiums, bicycle allowance |
| `EMP-100912` | Amira El Idrissi | *"Why is my net pay higher this month?"* (referral bonus), company car benefit in kind |

Also try questions that cannot be answered from a payslip, such as *"What is my manager's salary?"* or
*"What was my net pay in March 2026?"*. The assistant says clearly that it cannot find the information.

---

## Container deployment

### Build and run locally

```bash
docker build -t payslip-assistant .
docker run --rm -p 8080:8080 -e GEMINI_API_KEY=your-key payslip-assistant
# Cloud Run sets PORT dynamically; you can simulate it:
docker run --rm -e PORT=9090 -p 9090:9090 -e GEMINI_API_KEY=your-key payslip-assistant
```

The image is built in two stages: dependencies are installed into a virtualenv in a builder stage, and only
that virtualenv plus the app code are copied into a slim runtime image. The app runs as a non-root user,
starts with `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}`, and includes a container health check on
`/api/health`.

### Deploy to Google Cloud Run

```bash
PROJECT_ID=your-gcp-project
REGION=europe-west1
SERVICE=payslip-assistant

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

# Store the Gemini key in Secret Manager (recommended over plain env vars)
printf "%s" "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Create an Artifact Registry repository, then build and push the image with Cloud Build
gcloud artifacts repositories create containers --repository-format=docker --location=$REGION
IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/containers/$SERVICE:latest
gcloud builds submit --tag $IMAGE

# Deploy
gcloud run deploy $SERVICE \
  --image $IMAGE \
  --region $REGION \
  --allow-unauthenticated \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars AI_MODE=auto,GEMINI_MODEL=gemini-2.5-flash \
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 3
```

For a quick hackathon deployment you can also run `gcloud run deploy $SERVICE --source . --region $REGION`,
which builds the Dockerfile for you.

---

## Moving from prototype to production

- **Authentication:** the employee picker is for the demo only. In production, take the employee id from the
  verified SSO/OIDC token (for example with Identity-Aware Proxy in front of Cloud Run), never from the
  request body.
- **Data source:** replace `PayslipRepository` in `backend/database.py` with the payroll provider's API or
  document export. The retrieval layer only needs the rendered section texts.
- **Tax logic:** the withholding tax and special social security formulas in the mock data are simplified and
  only illustrate the format. They are not official Belgian scales.
- **Frontend:** Tailwind is loaded from its CDN for speed of iteration. For production, compile the CSS with
  the Tailwind CLI.
- **Privacy:** payslip data is personal data. Use a Gemini offering with data-processing terms that match your
  GDPR requirements (for example Gemini on Vertex AI in an EU region), and avoid logging question contents.

All people, companies and account numbers in this repository are fictional.
