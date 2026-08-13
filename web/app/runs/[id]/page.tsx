"use client";

import { useParams } from "next/navigation";
import { AnswerCard } from "@/components/AnswerCard";
import { StageTimeline } from "@/components/StageTimeline";
import { TraceViewer } from "@/components/TraceViewer";
import { useRunStream } from "@/lib/api";

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const { events, stage, final, error, live } = useRunStream(id);
  const started = events.find((e) => e.type === "run.started");

  return (
    <div className="flex flex-col gap-6">
      <section>
        <div className="label">Task</div>
        <p className="mt-1 text-[0.95rem]">
          {started ? String(started.payload.task) : "loading…"}
        </p>
      </section>

      <StageTimeline
        events={events}
        current={stage}
        live={live}
        finished={Boolean(final) || Boolean(error)}
      />

      {error && (
        <p className="rounded border border-alarm-line bg-alarm-bg px-3 py-2 text-sm text-alarm">
          {error}
        </p>
      )}

      {final ? (
        <AnswerCard final={final} />
      ) : (
        !error && (
          <p className="text-sm text-muted">
            {live
              ? "Deliberating. Independent answers first, then only the disagreements that matter."
              : "No final answer was produced."}
          </p>
        )
      )}

      {events.length > 0 && <TraceViewer events={events} />}
    </div>
  );
}
