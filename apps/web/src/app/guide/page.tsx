import Link from "next/link";

export default function GuidePage() {
  const steps = [
    {
      title: "Upload a Statement",
      description:
        "Click Upload Statement and select a PDF or Excel bank statement. The system automatically detects the bank and starts extraction.",
    },
    {
      title: "Review Extracted Transactions",
      description:
        "Verify narration, date, debit, credit, balance and confidence scores against the original statement.",
    },
    {
      title: "Correct Low-Confidence Rows",
      description:
        "Rows with low confidence should be reviewed manually before finalizing the statement.",
    },
    {
      title: "Map Ledgers",
      description:
        "Assign transactions to the correct accounting ledger or category for accurate bookkeeping.",
    },
    {
      title: "Export Final Data",
      description:
        "Export cleaned data to Excel, CSV, JSON or Tally-compatible formats.",
    },
  ];

  return (
    <div className="min-h-screen relative overflow-hidden bg-slate-50 dark:bg-slate-950">
      {/* Background blobs */}
      <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-blue-400/20 rounded-full mix-blend-multiply blur-[120px] opacity-70 pointer-events-none" />
      <div className="absolute top-1/4 left-0 w-[600px] h-[600px] bg-purple-400/20 rounded-full mix-blend-multiply blur-[120px] opacity-70 pointer-events-none" />

      {/* Header */}
      <header className="sticky top-0 z-50 w-full glass border-b border-white/20 dark:border-slate-800/50">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center text-white font-bold shadow-lg">
              B
            </div>

            <span className="font-semibold text-lg tracking-tight bg-gradient-to-br from-slate-800 to-slate-500 dark:from-white dark:to-slate-400 bg-clip-text text-transparent">
              Bank Extract
            </span>
          </div>

        <Link
  href="/"
  className="text-sm font-medium text-slate-600 hover:text-slate-900"
>
  ← Back to App
</Link>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8 relative z-10">
        {/* Hero */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              User Guide
            </h1>

            <p className="text-slate-500 dark:text-slate-400 mt-1">
              Learn how to upload, review, edit and export statements.
            </p>
          </div>

          <Link
            href="/dashboard"
            className="glass-input px-5 py-2 rounded-xl text-sm font-medium"
          >
            Back to Dashboard
          </Link>
        </div>

        {/* Overview Card */}
        <div className="glass-card rounded-3xl p-8 mb-8">
          <h2 className="text-xl font-semibold mb-3 text-slate-900 dark:text-white">
            Workflow Overview
          </h2>

          <p className="text-slate-600 dark:text-slate-300">
            The application converts raw bank statements into structured,
            categorized and export-ready accounting data.
          </p>
        </div>

        {/* Steps */}
        <div className="grid gap-6">
          {steps.map((step, index) => (
            <div
              key={step.title}
              className="glass-card rounded-3xl p-6"
            >
              <div className="flex items-start gap-5">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-blue-600 text-white font-bold shadow-md">
                  {index + 1}
                </div>

                <div>
                  <h3 className="text-xl font-semibold text-slate-900 dark:text-white">
                    {step.title}
                  </h3>

                  <p className="mt-2 text-slate-600 dark:text-slate-300">
                    {step.description}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Tips */}
        <div className="glass-card rounded-3xl p-8 mt-8">
          <h2 className="text-xl font-semibold mb-4">
            Best Practices
          </h2>

          <ul className="space-y-3 text-slate-600 dark:text-slate-300">
            <li>• Use original bank PDFs whenever possible.</li>
            <li>• Review low-confidence transactions before export.</li>
            <li>• Keep bank templates updated from the Admin panel.</li>
            <li>• Verify ledger mappings before generating reports.</li>
            <li>• Export only after final validation.</li>
          </ul>
        </div>
      </main>
    </div>
  );
}