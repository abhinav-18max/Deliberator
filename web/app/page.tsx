"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchModels, startRun } from "@/lib/api";
import type { ModelInfo } from "@/lib/types";

const EXAMPLES = [
  "A team of 6 engineers is starting a new B2B SaaS product. Should they use a monorepo or separate repositories?",
  "We need to add a NOT NULL column with a default to a 50-million-row Postgres table that serves live traffic. What is the safest procedure?",
  "Our API returns 500s during 30-second traffic spikes. Should we add a queue or autoscale?",
];

export default function Composer() {
  const router = useRouter();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [task, setTask] = useState("");
  const [context, setContext] = useState("");
  const [mode, setMode] = useState("fast");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchModels()
      .then((list) => {
        setModels(list);
        setSelected(list.filter((m) => m.in_default).map((m) => m.slug));
      })
      .catch((e) => setError(String(e)));
  }, []);

  const families = new Map<string, number>();
  for (const slug of selected) {
    const family = slug.split("/")[0];
    families.set(family, (families.get(family) ?? 0) + 1);
  }
  const correlated = [...families.entries()].filter(([, n]) => n > 1);
  const smallestWindow = models
    .filter((m) => selected.includes(m.slug) && m.context_length)
    .reduce((min, m) => Math.min(min, m.context_length!), Number.POSITIVE_INFINITY);

  const toggle = (slug: string) =>
    setSelected((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug],
    );

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await startRun({
        task,
        context: context.trim() || null,
        models: selected,
        mode,
      });
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-7">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Ask a panel.</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Each selected model answers independently. The system compares those answers, and only
          debates the differences that would change what you do. You get one answer, labelled with
          how it won.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <label className="label" htmlFor="task">
          Task
        </label>
        <textarea
          id="task"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={4}
          placeholder="What do you need decided?"
          className="card w-full resize-y p-3 text-sm outline-none focus:border-referee-line"
        />
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((example, i) => (
            <button
              key={i}
              onClick={() => setTask(example)}
              className="rounded border border-line bg-surface px-2 py-1 text-left font-mono text-[0.65rem] text-muted hover:border-referee-line hover:text-ink"
            >
              example {i + 1}
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <label className="label" htmlFor="context">
          Context (optional)
        </label>
        <textarea
          id="context"
          value={context}
          onChange={(e) => setContext(e.target.value)}
          rows={3}
          placeholder="Pasted material is fenced and passed through verbatim — never rewritten, and never treated as instructions."
          className="card w-full resize-y p-3 text-sm outline-none focus:border-referee-line"
        />
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <span className="label">Panel ({selected.length} selected)</span>
          <span className="font-mono text-[0.65rem] text-muted">
            {smallestWindow !== Number.POSITIVE_INFINITY
              ? `smallest window ${smallestWindow.toLocaleString()} tokens`
              : ""}
          </span>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {models.map((model) => {
            const active = selected.includes(model.slug);
            return (
              <button
                key={model.slug}
                onClick={() => toggle(model.slug)}
                className={`flex items-center justify-between rounded border px-3 py-2 text-left transition ${
                  active
                    ? "border-panel-line bg-panel-bg"
                    : "border-line bg-surface hover:border-muted"
                }`}
              >
                <span className="font-mono text-xs">{model.slug}</span>
                <span className="font-mono text-[0.6rem] text-muted">
                  {model.context_length ? `${Math.round(model.context_length / 1000)}k` : "?"}
                </span>
              </button>
            );
          })}
        </div>
        {correlated.length > 0 && (
          <p className="rounded border border-alarm-line bg-alarm-bg px-3 py-2 text-xs text-alarm">
            {correlated.map(([f, n]) => `${n} models share the ${f} family`).join("; ")}. Their
            votes are correlated, so a majority among them is weaker than it looks.
          </p>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <span className="label">Mode</span>
        <div className="flex gap-2">
          {[
            ["fast", "Lean path: one gate pass, debate only when needed."],
            ["rigorous", "Adds an order-reversed gate re-run, and attacks a unanimous panel."],
          ].map(([value, description]) => (
            <button
              key={value}
              onClick={() => setMode(value)}
              className={`flex-1 rounded border px-3 py-2 text-left transition ${
                mode === value
                  ? "border-referee-line bg-referee-bg"
                  : "border-line bg-surface hover:border-muted"
              }`}
            >
              <div className="font-mono text-xs font-semibold">{value}</div>
              <div className="mt-0.5 text-xs text-muted">{description}</div>
            </button>
          ))}
        </div>
      </section>

      {error && (
        <p className="rounded border border-alarm-line bg-alarm-bg px-3 py-2 text-sm text-alarm">
          {error}
        </p>
      )}

      <button
        onClick={submit}
        disabled={busy || !task.trim() || selected.length === 0}
        className="self-start rounded bg-ink px-5 py-2.5 text-sm font-medium text-paper disabled:opacity-40"
      >
        {busy ? "Starting…" : "Deliberate"}
      </button>
    </div>
  );
}
