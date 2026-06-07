import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-50">
      <section className="mx-auto grid min-h-[85vh] w-full max-w-6xl grid-cols-1 items-center gap-10 px-4 py-10 sm:px-6 lg:grid-cols-2 lg:px-8">
        <div>
          <p className="text-sm font-medium text-blue-700">
            Bank Statement Extraction
          </p>

          <h1 className="mt-3 text-4xl font-semibold tracking-normal text-slate-950 sm:text-5xl">
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

        <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
          <div className="grid gap-4">
            <Feature
              title="Upload"
              body="Import PDF and Excel statements from supported Indian banks."
            />
            <Feature
              title="Review"
              body="Compare extracted transactions with the original statement."
            />
            <Feature
              title="Correct"
              body="Edit values, resolve low-confidence rows, and map ledgers."
            />
            <Feature
              title="Export"
              body="Download CSV, Excel, JSON, or Tally-compatible output."
            />
          </div>
        </div>
      </section>

      <section className="border-t border-slate-200 bg-white">
        <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-6 px-4 py-10 sm:px-6 md:grid-cols-3 lg:px-8">
          <Stat label="Supported banks" value="15+" />
          <Stat label="Review workflow" value="Built in" />
          <Stat label="Export formats" value="4" />
        </div>
      </section>
    </main>
  );
}

function Feature({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-md border border-slate-200 p-4">
      <h2 className="text-base font-semibold text-slate-950">{title}</h2>
      <p className="mt-1 text-sm leading-6 text-slate-600">{body}</p>
    </article>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-3xl font-semibold text-slate-950">{value}</p>
      <p className="mt-1 text-sm text-slate-600">{label}</p>
    </div>
  );
}