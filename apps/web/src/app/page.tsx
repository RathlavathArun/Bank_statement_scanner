import Link from "next/link";

const workflowSteps = [
  {
    title: "Upload",
    body: "Import PDF or Excel bank statements from supported Indian banks.",
  },
  {
    title: "Extract",
    body: "Detect the bank format and extract dates, narrations, debit, credit, and balance.",
  },
  {
    title: "Review",
    body: "Compare extracted rows with the original statement and fix low-confidence values.",
  },
  {
    title: "Export",
    body: "Download reviewed data as Excel, CSV, JSON, or Tally-compatible XML.",
  },
];

const features = [
  "Side-by-side PDF preview",
  "Editable transaction table",
  "Confidence indicators",
  "OCR and Excel ingestion",
  "Ledger mapping",
  "Multi-bank templates",
  "Tally-compatible export",
  "Template-based parsing",
];

const banks = [
  "HDFC",
  "ICICI",
  "SBI",
  "Axis",
  "Kotak",
  "Yes Bank",
  "IDFC",
  "IndusInd",
  "RBL",
];

const exportFormats = ["Excel", "CSV", "JSON", "Tally XML"];

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="text-base font-semibold text-slate-950">
            Bank Statement Scanner
          </Link>

          <nav aria-label="Main navigation" className="flex items-center gap-4">
            <Link
              href="/guide"
              className="text-sm font-medium text-slate-600 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-blue-700 focus:ring-offset-2"
            >
              Guide
            </Link>
            <Link
              href="/dashboard"
              className="text-sm font-medium text-slate-600 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-blue-700 focus:ring-offset-2"
            >
              Dashboard
            </Link>
            <Link
              href="/dashboard"
              className="rounded-md bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-700 focus:ring-offset-2"
            >
              Start Upload
            </Link>
          </nav>
        </div>
      </header>

      <section className="mx-auto grid min-h-[82vh] w-full max-w-6xl grid-cols-1 items-center gap-10 px-4 py-10 sm:px-6 lg:grid-cols-2 lg:px-8">
        <div>
          <p className="text-sm font-medium text-blue-700">
            Bank Statement Extraction
          </p>

          <h1 className="mt-3 max-w-2xl text-4xl font-semibold tracking-normal text-slate-950 sm:text-5xl">
            Bank Statement Scanner
          </h1>

          <p className="mt-5 max-w-xl text-base leading-7 text-slate-600">
            Upload bank statements, review extracted transactions, fix
            low-confidence rows, and export clean accounting-ready data.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center rounded-md bg-blue-700 px-5 py-3 text-sm font-medium text-white hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-700 focus:ring-offset-2"
            >
              Start Upload
            </Link>

            <Link
              href="/guide"
              className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-5 py-3 text-sm font-medium text-slate-800 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-700 focus:ring-offset-2"
            >
              Read Guide
            </Link>
          </div>
        </div>

        <ProductPreview />
      </section>

      <section className="border-y border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow="Why it helps"
            title="Built for messy real bank statements"
            body="Indian bank statements vary by format, column names, narrations, and export needs. This workflow keeps extraction fast while still allowing human review."
          />

          <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            <InfoCard
              title="Less manual entry"
              body="Reduce repeated typing by extracting transaction rows from uploaded statements."
            />
            <InfoCard
              title="Bank-specific formats"
              body="Use template-based parsing for different statement layouts."
            />
            <InfoCard
              title="Review before export"
              body="Low-confidence rows can be corrected before final output."
            />
            <InfoCard
              title="Accounting-ready data"
              body="Export reviewed transactions in formats useful for downstream accounting."
            />
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="Workflow"
          title="From upload to export"
          body="The app is organized around a simple review flow, so users can move from raw statements to clean transaction data."
        />

        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-4">
          {workflowSteps.map((step, index) => (
            <article
              key={step.title}
              className="rounded-md border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-blue-800">
                {index + 1}
              </div>
              <h3 className="mt-4 text-base font-semibold text-slate-950">
                {step.title}
              </h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {step.body}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-y border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow="Features"
            title="Everything needed for statement review"
            body="The interface supports preview, correction, confidence checks, mapping, and final export."
          />

          <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((feature) => (
              <div
                key={feature}
                className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-800"
              >
                {feature}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-8 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:px-8">
        <div>
          <SectionHeading
            eyebrow="Supported banks"
            title="Template-based bank coverage"
            body="Supports major Indian bank statement formats and can be extended with new templates as more banks are added."
          />

          <div className="mt-6 flex flex-wrap gap-2">
            {banks.map((bank) => (
              <span
                key={bank}
                className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700"
              >
                {bank}
              </span>
            ))}
          </div>
        </div>

        <div>
          <SectionHeading
            eyebrow="Exports"
            title="Clean output formats"
            body="After review, users can export transactions into formats used by accounting and reporting workflows."
          />

          <div className="mt-6 grid grid-cols-2 gap-3">
            {exportFormats.map((format) => (
              <div
                key={format}
                className="rounded-md border border-slate-200 bg-white p-5 text-center text-base font-semibold text-slate-950 shadow-sm"
              >
                {format}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow="Trust"
            title="Designed for controlled review workflows"
            body="Bank data needs careful handling. The product is built around authenticated access, role-based workflows, auditability, and review before export."
          />

          <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
            <InfoCard
              title="Authenticated access"
              body="Private workflows stay behind login-protected app areas."
            />
            <InfoCard
              title="Review controls"
              body="Users can inspect and correct extracted values before export."
            />
            <InfoCard
              title="Audit-ready direction"
              body="The product structure supports traceable actions and controlled file handling."
            />
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="rounded-md border border-slate-200 bg-slate-950 px-5 py-8 text-white sm:px-8">
          <h2 className="text-2xl font-semibold tracking-normal">
            Ready to process a statement?
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
            Start with an upload, review extracted rows, and export clean
            transaction data for accounting workflows.
          </p>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center rounded-md bg-white px-5 py-3 text-sm font-medium text-slate-950 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-slate-950"
            >
              Go to Dashboard
            </Link>
            <Link
              href="/guide"
              className="inline-flex items-center justify-center rounded-md border border-slate-600 px-5 py-3 text-sm font-medium text-white hover:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-slate-950"
            >
              Read User Guide
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-6 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <p>Bank Statement Scanner</p>
          <div className="flex gap-4">
            <Link href="/guide" className="hover:text-slate-950">
              Guide
            </Link>
            <Link href="/dashboard" className="hover:text-slate-950">
              Dashboard
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}

function ProductPreview() {
  return (
    <div
      aria-label="Product preview showing statement review workflow"
      className="rounded-md border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div>
          <p className="text-sm font-semibold text-slate-950">
            Review Statement
          </p>
          <p className="text-xs text-slate-500">HDFC statement detected</p>
        </div>
        <span className="rounded-md bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-800">
          94% confidence
        </span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-[0.9fr_1.1fr]">
        <div className="min-h-72 rounded-md border border-slate-200 bg-slate-100 p-3">
          <div className="mb-3 h-3 w-24 rounded bg-slate-300" />
          <div className="space-y-2">
            <div className="h-3 rounded bg-slate-300" />
            <div className="h-3 w-10/12 rounded bg-slate-300" />
            <div className="h-3 w-11/12 rounded bg-slate-300" />
          </div>
          <div className="mt-6 space-y-2">
            {Array.from({ length: 8 }).map((_, index) => (
              <div
                key={index}
                className="grid grid-cols-4 gap-2 rounded bg-white p-2"
              >
                <div className="h-2 rounded bg-slate-200" />
                <div className="h-2 rounded bg-slate-200" />
                <div className="h-2 rounded bg-slate-200" />
                <div className="h-2 rounded bg-slate-200" />
              </div>
            ))}
          </div>
        </div>

        <div className="overflow-hidden rounded-md border border-slate-200">
          <div className="grid grid-cols-4 bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-600">
            <span>Date</span>
            <span>Narration</span>
            <span>Debit</span>
            <span>Status</span>
          </div>

          {[
            ["02 Apr", "UPI transfer", "1,250", "OK"],
            ["03 Apr", "ATM withdrawal", "5,000", "Review"],
            ["04 Apr", "Salary credit", "-", "OK"],
            ["05 Apr", "Card payment", "899", "OK"],
          ].map((row) => (
            <div
              key={row.join("-")}
              className="grid grid-cols-4 border-t border-slate-200 px-3 py-3 text-xs text-slate-700"
            >
              <span>{row[0]}</span>
              <span>{row[1]}</span>
              <span>{row[2]}</span>
              <span
                className={
                  row[3] === "Review"
                    ? "font-medium text-amber-700"
                    : "font-medium text-emerald-700"
                }
              >
                {row[3]}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div>
      <p className="text-sm font-medium text-blue-700">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-normal text-slate-950">
        {title}
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">{body}</p>
    </div>
  );
}

function InfoCard({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-base font-semibold text-slate-950">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
    </article>
  );
}