"use client";
export function SearchTree({
  records,
  onSelect,
}: {
  records: any[];
  onSelect: (id: string) => void;
}) {
  const lanes = Array.from(
    new Set(
      records.map(
        (r) => `${r.coord?.R || 1}:${r.coord?.C || 1}:${r.coord?.K || 1}`,
      ),
    ),
  );
  const nodes = records.map((record, i) => ({
    record,
    x: ((record.coord?.L || i + 1) - 1) * 180 + 90,
    y:
      lanes.indexOf(
        `${record.coord?.R || 1}:${record.coord?.C || 1}:${record.coord?.K || 1}`,
      ) *
        90 +
      45,
  }));
  const positions = new Map(nodes.map((n) => [n.record.node_id, n]));
  const width = Math.max(360, ...nodes.map((n) => n.x + 95)),
    height = Math.max(100, lanes.length * 90);
  return (
    <div className="tree-scroll">
      <svg
        width={width}
        height={height}
        role="group"
        aria-label="R-C-L-K search tree"
      >
        <defs>
          <marker
            id="search-arrow"
            markerWidth="7"
            markerHeight="7"
            refX="6"
            refY="3.5"
            orient="auto"
          >
            <path d="M0,0 L7,3.5 L0,7" fill="var(--muted)" />
          </marker>
        </defs>
        {nodes.flatMap((n) =>
          (n.record.parents || []).map((parent: any) => {
            const from = positions.get(parent.node_id);
            if (!from) return null;
            return (
              <path
                key={`${parent.node_id}-${n.record.node_id}`}
                d={`M${from.x + 75},${from.y} C${from.x + 100},${from.y} ${n.x - 100},${n.y} ${n.x - 76},${n.y}`}
                fill="none"
                stroke="var(--muted)"
                markerEnd="url(#search-arrow)"
              />
            );
          }),
        )}
        {nodes.map(({ record, x, y }) => (
          <g
            key={record.node_id}
            role="button"
            tabIndex={0}
            aria-label={record.node_id}
            onClick={() => onSelect(record.node_id)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSelect(record.node_id);
            }}
            style={{ cursor: "pointer" }}
          >
            <title>
              {record.core?.formula || record.progress || record.node_id}
            </title>
            <rect
              x={x - 75}
              y={y - 25}
              width={150}
              height={50}
              rx={7}
              fill="var(--soft)"
              stroke="var(--line)"
            />
            <text
              x={x}
              y={y - 5}
              textAnchor="middle"
              fill="var(--text)"
              fontSize={10}
            >
              {record.node_label || record.node_id}
            </text>
            <text
              x={x}
              y={y + 12}
              textAnchor="middle"
              fill="var(--accent)"
              fontSize={10}
            >
              {String(
                record.core?.formula ||
                  record.core?.tool_names?.join(", ") ||
                  "",
              ).slice(0, 24)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
