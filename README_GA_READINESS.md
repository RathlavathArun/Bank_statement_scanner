# 🚀 Production & GA Readiness Verification Guide

This document details the tasks, verification status, and run commands for the GA readiness checklist across **Phase 3** (LLM Pipeline & Bank Coverage), **Phase 4** (Frontend Completeness), and **Phase 5** (Security & Validation Audit).

---

## 📋 Task Status Dashboard

| Phase | Task ID & Title | Status | Verification Files / Evidence |
|---|---|---|---|
| **Phase 3** | **Task 14**: Anthropic Zero Data Retention (ZDR) configuration | 🟢 COMPLETE | `apps/api/core/config.py`, `apps/api/statements/llm_enrichment.py`, `apps/api/tests/test_phase6_part_d_regression.py` |
| **Phase 3** | **Task 16**: LLM Retry & Exponential Backoff handling | 🟢 COMPLETE | `apps/api/statements/llm_enrichment.py` (`backoff` module integration) |
| **Phase 3** | **Task 17**: Hallucinated Ledger Detection | 🟢 COMPLETE | `apps/api/statements/llm_enrichment.py`, `apps/api/core/eval_categorization.py` |
| **Phase 3** | **Task 18**: Fallback Chain Structured Exception handling | 🟢 COMPLETE | `apps/api/statements/llm_enrichment.py` |
| **Phase 3** | **Task 19**: Date Cycle & Similarity Recurring Txn Detection | 🟢 COMPLETE | `apps/api/core/eval_categorization.py` |
| **Phase 3** | **Task 21**: Bank Template Coverage Report Generator | 🟢 COMPLETE | `apps/api/core/generate_coverage_report.py`, `apps/api/coverage_report.json` |
| **Phase 3** | **Task 22**: Expected JSON Fixture Regression Tests | 🟢 COMPLETE | `apps/api/core/bank_regression.py`, `apps/api/tests/test_phase6_part_d_regression.py` |
| **Phase 3** | **Task 23**: Failure Rate Prometheus alert rules | 🟢 COMPLETE | `apps/api/core/metrics.py`, `infra/prometheus_alerts.yml` |
| **Phase 3** | **Task 24**: Exclude ignored transactions from exports | 🟢 COMPLETE | `apps/api/statements/export_service.py` |
| **Phase 4** | **Zustand & React Query**: Client state and caching integration | 🟢 COMPLETE | `apps/web/package.json`, `apps/web/src/lib/local-store.ts`, `apps/web/src/components/query-client-provider.tsx` |
| **Phase 4** | **Task 26**: Bbox Scroll-Into-View behavior | 🟢 COMPLETE | `apps/web/src/components/PDFViewer.tsx` |
| **Phase 4** | **Task 28**: Filter ignored transactions from totals | 🟢 COMPLETE | `apps/web/src/components/TransactionTable.tsx` |
| **Phase 4** | **Task 30**: Uppy upload Pause/Resume/Retry UI | 🟢 COMPLETE | `apps/web/src/components/UppyUploader.tsx` |
| **Phase 4** | **Task 31**: BankTemplateUploadForm Hook Form + Zod | 🟢 COMPLETE | `apps/web/src/components/BankTemplateUploadForm.tsx` |
| **Phase 5** | **Task 32**: Automated Security reviewer scan | 🟢 COMPLETE | `apps/api/core/run_security_scan.py`, `security_report.md` (Artifact) |
| **Phase 5** | **Task 33**: Extraction accuracy evaluator | 🟢 COMPLETE | `apps/api/core/eval_extraction.py`, `accuracy_report.json` (Artifact) |
| **Phase 5** | **Task 34**: Categorization/Ledger mapping evaluator | 🟢 COMPLETE | `apps/api/core/eval_categorization.py`, `llm_accuracy_report.json` (Artifact) |
| **Phase 5** | **Task 35**: k6/Locust performance load test | 🟢 COMPLETE | `e2e/load_test.js`, `load_test_report.md` (Artifact) |

---

## 🛠️ Execution & Verification Commands

All paths are relative to the repository root.

### 1. Run Backend Pytest Suite
To run the full backend verification test suite (including safety, regression, and RLS tests):
```bash
cd apps/api
# Make sure virtual environment is active
venv\Scripts\activate
pytest
```

### 2. Run Bank Template Regression Tests
To run the regression checks for all 30 bank statement YAML templates:
```bash
cd apps/api
venv\Scripts\python -m pytest tests/test_phase6_part_d_regression.py
```

### 3. Generate Bank Template Coverage Report
Generates `coverage_report.json` detailing fields mapped, format validations, and matching regex rules across all templates:
```bash
cd apps/api
venv\Scripts\python core/generate_coverage_report.py
```

### 4. Run Automated Security Auditor Scan
Triggers firm isolation checks, dependency reviews, secrets scanning, and outputs `security_report.md`:
```bash
cd apps/api
venv\Scripts\python core/run_security_scan.py
```

### 5. Run Extraction Accuracy Evaluator
Compares extracted statement fields (date, narration, debit, credit, balance) against expected values and outputs `accuracy_report.json`:
```bash
cd apps/api
venv\Scripts\python core/eval_extraction.py
```

### 6. Run Categorization/LLM Mapping Evaluator
Evaluates Claude narration mapping accuracy and ledger suggestions, outputs `llm_accuracy_report.json`:
```bash
cd apps/api
venv\Scripts\python core/eval_categorization.py
```

### 7. Run Frontend Web Dashboard
Start the Next.js development server:
```bash
cd apps/web
npm install
npm run dev
```

### 8. Run Frontend TypeScript Verification
Ensures all state, form validation, and query client integrations compile successfully:
```bash
cd apps/web
npx tsc --noEmit
```

### 9. Run Performance Load Test
To run the Locust/k6 load test script:
```bash
# Verify k6 is installed
k6 run e2e/load_test.js
```
