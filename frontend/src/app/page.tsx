import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center min-h-screen bg-zinc-50 px-4">
      <div className="max-w-md text-center space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Clauseline</h1>
        <p className="text-zinc-500 text-sm leading-relaxed">
          Contract intelligence with rigorous grounding, honest evals, and
          observable engineering.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
          <Link
            href="/evals"
            className="px-5 py-2.5 rounded-lg bg-zinc-800 text-white text-sm font-medium hover:bg-zinc-700 transition-colors"
          >
            Open evals dashboard
          </Link>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="px-5 py-2.5 rounded-lg border border-zinc-300 text-zinc-700 text-sm font-medium hover:border-zinc-500 transition-colors"
          >
            API docs
          </a>
        </div>
      </div>
    </main>
  );
}
