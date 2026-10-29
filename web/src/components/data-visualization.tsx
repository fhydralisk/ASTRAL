"use client";
import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
} from "recharts";

export function DataVisualization({
  context,
  call,
}: {
  context: any;
  call: (path: string, method?: string, payload?: unknown) => Promise<any>;
}) {
  const [mode, setMode] = useState("table"),
    [x, setX] = useState(""),
    [y, setY] = useState(""),
    [points, setPoints] = useState<any[]>([]),
    [bins, setBins] = useState(20),
    [row, setRow] = useState<string[]>([]),
    [column, setColumn] = useState<string[]>([]),
    [color, setColor] = useState(""),
    [z, setZ] = useState(""),
    [zIndex, setZIndex] = useState(0),
    [heat, setHeat] = useState<any>(null),
    [error, setError] = useState("");
  const columns: string[] = context.columns || [],
    tableColumns: string[] = context.preview_columns || columns;
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        if (mode === "scatter" || mode === "distribution") {
          if (!x || (mode === "scatter" && !y)) return;
          const result = await call(
            `/data/context/plot?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y || x)}&limit=5000`,
          );
          if (!active) return;
          const xs = result.values?.[x] || [],
            ys = result.values?.[y || x] || [];
          if (mode === "scatter")
            setPoints(
              xs
                .map((v: unknown, i: number) => ({
                  x: Number(v),
                  y: Number(ys[i]),
                }))
                .filter(
                  (p: any) => Number.isFinite(p.x) && Number.isFinite(p.y),
                ),
            );
          else {
            const values = xs.map(Number).filter(Number.isFinite);
            const low = Math.min(...values),
              high = Math.max(...values),
              width = high === low ? 1 : (high - low) / bins;
            const histogram = Array.from({ length: bins }, (_, i) => ({
              x: Number((low + i * width).toPrecision(5)),
              count: 0,
            }));
            for (const value of values)
              histogram[
                Math.min(
                  bins - 1,
                  Math.max(0, Math.floor((value - low) / width)),
                )
              ].count++;
            setPoints(histogram);
          }
        } else if (mode === "heatmap" && row.length && column.length) {
          const result = await call("/data/context/heatmap", "POST", {
            row,
            column,
            color,
            z,
            z_index: zIndex,
          });
          if (active) setHeat(result);
        }
        if (active) setError("");
      } catch (e) {
        if (active) setError(String(e));
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [mode, x, y, bins, row, column, color, z, zIndex, call]);
  const numeric = (heat?.values || [])
      .flat()
      .map(Number)
      .filter(Number.isFinite),
    low = Math.min(...numeric),
    high = Math.max(...numeric);
  return (
    <div>
      <div className="toolbar">
        <span>{context.rows || 0} rows</span>
        <select
          aria-label="Visualization"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="table">Table / 表格</option>
          <option value="scatter">Scatter / 散点</option>
          <option value="distribution">Distribution / 分布</option>
          <option value="heatmap">Heatmap / 热图</option>
        </select>
        {["scatter", "distribution"].includes(mode) && (
          <>
            <label>
              X
              <select value={x} onChange={(e) => setX(e.target.value)}>
                <option value="">—</option>
                {columns.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            {mode === "scatter" && (
              <label>
                Y
                <select value={y} onChange={(e) => setY(e.target.value)}>
                  <option value="">—</option>
                  {columns.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
            )}
            {mode === "distribution" && (
              <label>
                Bins
                <input
                  type="number"
                  min={2}
                  max={100}
                  value={bins}
                  onChange={(e) =>
                    setBins(
                      Math.min(100, Math.max(2, Number(e.target.value) || 20)),
                    )
                  }
                />
              </label>
            )}
          </>
        )}
      </div>
      {mode === "heatmap" && (
        <div className="fields">
          {(["Row / 行", "Column / 列"] as const).map((label, i) => (
            <label key={label}>
              {label}
              <select
                multiple
                value={i ? column : row}
                onChange={(e) => {
                  const selected = Array.from(
                    e.target.selectedOptions,
                    (o) => o.value,
                  );
                  i ? setColumn(selected) : setRow(selected);
                }}
              >
                {columns.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
          ))}
          <label>
            Color variable / 颜色变量
            <select value={color} onChange={(e) => setColor(e.target.value)}>
              <option value="">Aligned variables / 对齐变量</option>
              {columns.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Z axis / 切片轴
            <select
              value={z}
              onChange={(e) => {
                setZ(e.target.value);
                setZIndex(0);
              }}
            >
              <option value="">—</option>
              {columns.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          {z && (
            <label>
              Z index
              <input
                type="number"
                min={0}
                value={zIndex}
                onChange={(e) => setZIndex(Number(e.target.value))}
              />
            </label>
          )}
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {mode === "table" && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {tableColumns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(context.data || []).map((r: any, i: number) => (
                <tr key={i}>
                  {tableColumns.map((c) => (
                    <td key={c}>{String(r[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {["scatter", "distribution"].includes(mode) && (
        <div className="chart">
          <ResponsiveContainer width="100%" height={280}>
            {mode === "scatter" ? (
              <ScatterChart>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="x" type="number" name={x} />
                <YAxis dataKey="y" type="number" name={y} />
                <Tooltip />
                <Scatter data={points} fill="#5177c5" />
              </ScatterChart>
            ) : (
              <BarChart data={points}>
                <XAxis dataKey="x" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#5177c5" />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
      {mode === "heatmap" && heat && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th />
                {heat.column_labels?.map((v: unknown, i: number) => (
                  <th key={i}>{String(v)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {heat.values?.map((values: unknown[], i: number) => (
                <tr key={i}>
                  <th>{String(heat.row_labels?.[i] ?? i)}</th>
                  {values.map((v, j) => (
                    <td
                      key={j}
                      title={`${heat.row_labels?.[i]}, ${heat.column_labels?.[j]}: ${v}`}
                      style={{
                        background: `rgba(75,120,210,${Number.isFinite(Number(v)) ? 0.1 + (0.8 * (Number(v) - low)) / (high - low || 1) : 0})`,
                      }}
                    >
                      {typeof v === "number"
                        ? v.toPrecision(4)
                        : String(v ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {heat.truncated && <small>Preview truncated / 预览已截断</small>}
        </div>
      )}
    </div>
  );
}
