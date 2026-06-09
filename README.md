# secure_pipeline

A minimal FastAPI application used as a vehicle for demonstrating a security-focused CI/CD pipeline with GitHub Actions and AWS ECR. The app itself is intentionally simple — the pipeline is the point.

---

## What the application does

The API exposes two endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check — returns status, version, and environment |
| `POST` | `/echo` | Echoes a submitted message back to the caller |

The application is a controlled surface so that every security tool in the pipeline has something real to analyze, without obscuring the pipeline itself in application complexity.

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

The deploy step is only reached if the container image scan passes. The SARIF output from Trivy is uploaded to GitHub's Security tab alongside CodeQL results.

---

## Security choices and reasoning

### OIDC for AWS authentication — no stored credentials

The CD workflow uses GitHub's OIDC provider to obtain short-lived AWS credentials at runtime rather than storing an `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in repository secrets. The IAM role is scoped to this specific repository and branch (`repo:thegitfiddler/secure_pipeline:ref:refs/heads/main`), so the credentials cannot be used outside that context even if intercepted.

This eliminates the most common CI/CD credential leak vector and follows AWS's recommended pattern for GitHub Actions.

### Multi-stage Docker build with a non-root runtime user

The Dockerfile uses a two-stage build: a `builder` stage installs dependencies, and a minimal `runtime` stage copies only the installed packages — no pip, no build tools, no unnecessary attack surface. The runtime container runs as a non-root system user (`appuser`), so a container escape does not immediately grant root on the host.

### Bandit — SAST for Python

Bandit performs static analysis specifically for Python security anti-patterns: hardcoded credentials, use of dangerous functions (`eval`, `subprocess` with shell=True), insecure random number generation, and similar issues. Configured at medium+ severity and confidence to reduce noise while catching real findings. A `.bandit` config file excludes the test directory from scanning.

### CodeQL — semantic SAST

CodeQL goes deeper than pattern matching — it builds a semantic model of the code and traces data flows to find vulnerabilities like injection sinks that Bandit can miss. Results appear in the repository's Security → Code Scanning tab.

### pip-audit — Software Composition Analysis (SCA)

pip-audit queries `requirements.txt` against the OSV (Open Source Vulnerability) database and the Python Packaging Advisory Database. It catches known CVEs in third-party dependencies — a category that SAST tools don't cover. Only production dependencies are audited, matching what actually runs in the container.

### Gitleaks — secret scanning

Gitleaks scans the full commit history (not just the current diff) for accidentally committed secrets: API keys, tokens, connection strings, private keys. The full-history scan (`fetch-depth: 0`) catches historical leaks, not just new ones.

### Trivy — container image scanning

Trivy scans the final Docker image layer-by-layer for known CVEs in OS packages and Python dependencies. It runs against the built image before the push step, so a vulnerable image never reaches the registry. Only `CRITICAL` and `HIGH` findings fail the build; `ignore-unfixed: true` avoids blocking on vulnerabilities that have no patch available yet.

---

## Repository secrets required

| Secret | Purpose |
|--------|---------|
| `AWS_ROLE_ARN` | ARN of the IAM role to assume via OIDC |

No AWS access keys are stored. The IAM role's trust policy is scoped to this repository:

```json
{
  "Condition": {
    "StringLike": {
      "token.actions.githubusercontent.com:sub": "repo:thegitfiddler/secure_pipeline:ref:refs/heads/main"
    }
  }
}
```

The role requires `AmazonEC2ContainerRegistryPowerUser` permissions on the target ECR repository.

---

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run the API
uvicorn app.main:app --reload

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

API docs are available at `http://localhost:8000/docs` when running locally.

---

## Repository structure

```
.
├── .github/
│   └── workflows/
│       ├── ci.yml          # Test + security scans
│       └── cd.yml          # Build + container scan + ECR push
├── app/
│   ├── main.py             # FastAPI application
│   └── tests/
│       └── test_main.py    # Unit tests
├── .bandit                 # Bandit configuration
├── .gitignore
├── Dockerfile              # Multi-stage, non-root runtime
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Test and security tooling
└── README.md
```
