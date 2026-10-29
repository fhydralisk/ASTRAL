"use client";
import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { JsonEditor, Formula } from "./common";

export function Candidates({
  snapshot,
  call,
  en,
}: {
  snapshot: any;
  call: (path: string) => Promise<any>;
  en: boolean;
}) {
  const [mode, setMode] = useState("topk"),
    [records, setRecords] = useState<any[]>([]),
    [format, setFormat] = useState("raw");
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await call("/candidates?mode=" + mode);
        if (active) setRecords(result.records || []);
      } catch {
      } finally {
        if (active) timer = setTimeout(poll, 2500);
      }
    }
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [mode, call]);
  const shown = records.length
    ? records
    : mode === "topk"
      ? snapshot.topk_records || []
      : [];
  return (
    <>
      <h3>{en ? "Candidate formulas" : "候选公式"}</h3>
      <div className="toolbar">
        <button
          className={mode === "topk" ? "active" : ""}
          onClick={() => setMode("topk")}
        >
          Top-k
        </button>
        <button
          className={mode === "pareto" ? "active" : ""}
          onClick={() => setMode("pareto")}
        >
          Pareto
        </button>
        <select
          aria-label="Formula format"
          value={format}
          onChange={(e) => setFormat(e.target.value)}
        >
          <option value="raw">Raw / 原式</option>
          <option value="latex">LaTeX</option>
        </select>
      </div>
      {mode === "pareto" && shown.length > 0 && (
        <ResponsiveContainer width="100%" height={160}>
          <ScatterChart>
            <XAxis dataKey="complexity" type="number" name="Complexity" />
            <YAxis dataKey="mse" type="number" name="MSE" />
            <Tooltip />
            <Scatter data={shown} fill="#5177c5" />
          </ScatterChart>
        </ResponsiveContainer>
      )}
      {shown.map((candidate: any, i: number) => (
        <article
          className="card"
          key={`${candidate.node_id || i}-${candidate.formula}`}
        >
          <strong>#{i + 1}</strong>
          {format === 'latex' ? <Formula latex={candidate.formula_latex || candidate.formula || ''}/> : <code>{candidate.formula || candidate.f}</code>}
          <JsonEditor label="Metrics / 指标" value={candidate} readOnly />
        </article>
      ))}
      <JsonEditor label="Session state / 会话状态" value={snapshot} readOnly />
    </>
  );
}
