# secure_pipeline

A minimal FastAPI application used as a vehicle for demonstrating a security-focused CI/CD pipeline with GitHub Actions and AWS ECR. The app itself is intentionally simple — the pipeline is the point.

---

## What the application does

The API exposes two endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check — returns status, version, and environment |
| `POST` | `/echo` | Echoes a submitted message back to the caller |

The application is a controlled surface so that every security tool in the pipeline has something real to analyze, without obscuring the pipeline in application complexity.

---

## Pipeline overview

Two workflows run in this repository, visible in the **Actions** tab.

### CI — Test & Security Scan (`ci.yml`)

Triggers on every push to `main` or `dev`, and on pull requests targeting `main`.

```
push / pull_request
        │
        ├── test          → pytest + coverage (≥80% required)
        ├── sast-bandit   → Bandit static analysis (medium+ severity/confidence)
        ├── sast-codeql   → CodeQL deep analysis (SARIF uploaded to Security tab)
        ├── sca-pip-audit → pip-audit checks deps against OSV/PyPA advisories
        └── secret-scan   → Gitleaks scans full commit history
```

All five jobs run in parallel. The pipeline fails fast if any job fails — code does not proceed toward a build if tests, security checks, or secret scanning fail.

### CD — Build & Deploy to AWS ECR (`cd.yml`)

Triggers on push to `main` and supports manual dispatch.

```
push to main
        │
        ├── Configure AWS via OIDC (no stored credentials)
        ├── Log in to Amazon ECR
        ├── Build Docker image (multi-stage, non-root user)
        ├── Trivy container scan (CRITICAL/HIGH CVEs block push)
        └── Push image to ECR  ← only reached if scan is clean
```

The deploy step is only reached if the container image scan passes. Trivy SARIF results are uploaded to the GitHub Security tab alongside CodeQL findings.

---

## Security choices and reasoning

### OIDC for AWS authentication — no stored credentials

The CD workflow authenticates to AWS using GitHub's OIDC provider, exchanging a short-lived identity token for temporary AWS credentials at runtime. No `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` is stored anywhere. The IAM role trust policy is scoped specifically to this repository and branch:

```
repo:Thegitfiddler/Secure_Pipeline:ref:refs/heads/main
```

This means the credentials cannot be used outside that exact context, eliminating the most common CI/CD credential leak vector.

### Multi-stage Docker build with a non-root runtime user

The Dockerfile uses a two-stage build: a `builder` stage installs dependencies, and a minimal `runtime` stage copies only the installed packages — no pip, no build tools, no unnecessary attack surface. The container runs as a non-root system user (`appuser`), so a container escape does not immediately grant root on the host.

### Bandit — SAST for Python

Bandit performs static analysis for Python-specific security anti-patterns: hardcoded credentials, dangerous function calls, insecure randomness, and similar issues. Configured at medium+ severity and confidence to reduce noise. A `.bandit` config file scopes the scan to the `app/` directory and excludes tests.

### CodeQL — semantic SAST

CodeQL builds a semantic model of the codebase and traces data flows to find vulnerabilities that pattern-matching tools can miss — such as user input reaching a dangerous sink. Results are uploaded to the repository's Security → Code Scanning tab.

### pip-audit — Software Composition Analysis (SCA)

pip-audit checks production dependencies against the OSV and PyPA advisory databases for known CVEs. This covers vulnerabilities in third-party packages that SAST tools don't see. During development, pip-audit flagged active CVEs in a transitive starlette dependency pulled in by an older FastAPI version — the dependency was updated to resolve them before any code was merged.

### Gitleaks — secret scanning

Gitleaks scans the full commit history for accidentally committed secrets: API keys, tokens, connection strings, and private keys. The full-history scan (`fetch-depth: 0`) catches historical leaks, not just new commits.

### Trivy — container image scanning

Trivy scans the final Docker image layer-by-layer for known CVEs in OS packages and Python dependencies. The scan runs before the push step — a vulnerable image never reaches the registry. CRITICAL and HIGH findings block the pipeline. A `.trivyignore` file documents base OS CVEs in the Debian layer that have no upstream fix available yet; these are explicitly acknowledged rather than silently ignored.

---

## Repository secrets required

| Secret | Purpose |
|--------|---------|
| `AWS_ROLE_ARN` | ARN of the IAM role to assume via OIDC |

No AWS access keys are stored. The role requires `AmazonEC2ContainerRegistryPowerUser` permissions and a trust policy scoped to this repository.

---

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run the API
uvicorn app.main:app --reload

# API docs available at http://localhost:8000/docs

# Run tests
pytest app/tests/ --cov=app --cov-report=term-missing

# Run Bandit manually
bandit -r app/ -ll -ii

# Run pip-audit manually
pip-audit -r requirements.txt

# Build and run the container
docker build -t secure_pipeline .
docker run -p 8000:8000 secure_pipeline

```

---

## Repository structure

```
.
├── .github/
│   └── workflows/
│       ├── ci.yml          # Test + security scans
│       └── cd.yml          # Build + container scan + ECR push
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI application
│   └── tests/
│       ├── __init__.py
│       └── test_main.py    # Unit tests
├── .bandit                 # Bandit scan configuration
├── .gitignore
├── .trivyignore            # Documented base OS CVE exceptions
├── Dockerfile              # Multi-stage, non-root runtime
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Test and security tooling
└── README.md
```
