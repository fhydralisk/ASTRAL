"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import katex from "katex";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
export function JsonEditor({
  value,
  onApply,
  label = "JSON",
  readOnly = false,
}: {
  value: unknown;
  onApply?: (v: any) => Promise<void>;
  label?: string;
  readOnly?: boolean;
}) {
  const [text, setText] = useState(JSON.stringify(value, null, 2)),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const dirty = useRef(false),
    serialized = JSON.stringify(value, null, 2);
  useEffect(() => {
    if (!dirty.current) setText(serialized);
  }, [serialized]);
  return (
    <details className="json-editor">
      <summary>{label}</summary>
      <textarea
        aria-label={label}
        value={text}
        readOnly={readOnly}
        onChange={(e) => {
          dirty.current = true;
          setText(e.target.value);
        }}
        rows={12}
      />
      {onApply && (
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onApply(JSON.parse(text));
              dirty.current = false;
              setError("");
            } catch (e) {
              setError(String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          Apply / 应用
        </button>
      )}
      {error && <p className="error">{error}</p>}
    </details>
  );
}
export function Timeline({ events }: { events: any[] }) {
  return (
    <div className="timeline">
      {events.map((event, i) => (
        <article
          className="event"
          key={`${event.seq ?? event.sequence ?? i}-${i}`}
        >
          <small>
            {event.kind || event.type || event.event || "event"} ·{" "}
            {event.seq ?? event.sequence}
          </small>
          {typeof event.payload?.content === "string" ? (
            <Markdown>{event.payload.content}</Markdown>
          ) : typeof event.payload?.message?.content === "string" ? (
            <Markdown>{event.payload.message.content}</Markdown>
          ) : typeof event.payload?.message === "string" ? (
            <Markdown>{event.payload.message}</Markdown>
          ) : null}
          <JsonEditor
            label="Details / 详情"
            value={event.payload ?? event}
            readOnly
          />
        </article>
      ))}
    </div>
  );
}

function Markdown({children}: {children: string}) {
  return <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, {trust: false}]]}>{children}</ReactMarkdown>;
}
export function Formula({latex}: {latex: string}) {
  const html = useMemo(() => katex.renderToString(latex, {throwOnError: false, trust: false, maxExpand: 1000, displayMode: true}), [latex]);
  return <div className="math-formula" dangerouslySetInnerHTML={{__html: html}}/>;
}
