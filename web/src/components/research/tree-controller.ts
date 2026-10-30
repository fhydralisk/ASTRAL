// @ts-nocheck
// Original search viewer layout, navigation, detail, and export behavior.
import katex from "katex";
import { researchRuntime } from "./runtime";
import { researchTransport } from "./transport";
export function mountTree(root: HTMLElement) {
  const runtime = researchRuntime(root);
  const {
    document,
    window,
    setTimeout,
    setInterval,
    requestAnimationFrame,
    ResizeObserver,
    IntersectionObserver,
  } = runtime;
  const transport = researchTransport(
    runtime.signal,
    new URLSearchParams(location.search).get("conversation") || undefined,
  );
  const MathJax = {
    typesetPromise: async (nodes) => {
      for (const node of nodes) {
        let source = node.textContent.trim();
        if (source.startsWith("\\[") && source.endsWith("\\]"))
          source = source.slice(2, -2);
        node.innerHTML = katex.renderToString(source, {
          throwOnError: false,
          trust: false,
          displayMode: true,
        });
      }
    },
  };

  const ROOT_PREFIX = "__root__:";
  const DEFAULT_LEVEL_GAP = 118;
  const DEFAULT_NODE_RADIUS = 9;
  const SIBLING_GAP = 64;
  const refreshButton = document.getElementById("refresh");
  const homeButton = document.getElementById("home");
  const layoutButton = document.getElementById("layout");
  const weakEdgesButton = document.getElementById("weak-edges");
  const labelsButton = document.getElementById("labels");
  const nodeSizeInput = document.getElementById("node-size");
  const nodeSizeValue = document.getElementById("node-size-value");
  const levelGapInput = document.getElementById("level-gap");
  const levelGapValue = document.getElementById("level-gap-value");
  const horizontalScaleInput = document.getElementById("horizontal-scale");
  const horizontalScaleValue = document.getElementById(
    "horizontal-scale-value",
  );
  const colorMetricSelect = document.getElementById("color-metric");
  const r2ColorMinInput = document.getElementById("r2-color-min");
  const r2ColorMaxInput = document.getElementById("r2-color-max");
  const r2ColorMinValue = document.getElementById("r2-color-min-value");
  const r2ColorMaxValue = document.getElementById("r2-color-max-value");
  const exportFormat = document.getElementById("export-format");
  const exportButton = document.getElementById("export");
  const legend = document.getElementById("legend");
  const legendTitle = document.getElementById("legend-title");
  const main = document.querySelector("main");
  const runPanel = document.getElementById("run-panel");
  const runTree = document.getElementById("run-tree");
  const runResizer = document.getElementById("run-resizer");
  const runTabButtons = [...document.querySelectorAll("[data-run-tab]")];
  const runsPanel = document.getElementById("runs-panel");
  const controlsPanel = document.getElementById("controls-panel");
  const sideResizer = document.getElementById("side-resizer");
  const formulaLatex = document.getElementById("formula-latex");
  const formulaEditorToggle = document.getElementById("formula-editor-toggle");
  const formulaEditor = document.getElementById("formula-editor");
  const latexSource = document.getElementById("latex-source");
  const copyLatexButton = document.getElementById("copy-latex");
  const formulaEditorStatus = document.getElementById("formula-editor-status");
  const detailEl = document.getElementById("detail");
  const statusEl = document.getElementById("status");
  const guidanceInput = document.getElementById("guidance");
  const sendGuidanceButton = document.getElementById("send-guidance");
  const pauseAgentButton = document.getElementById("pause-agent");
  const stopAgentButton = document.getElementById("stop-agent");
  const agentStatusEl = document.getElementById("agent-status");
  let controlSeq = 0;
  let agentPaused = false;
  const svg = document.getElementById("graph");
  const state = {
    runId: null,
    selectedNodeId: null,
    records: new Map(),
    lastSeq: 0,
    source: null,
    positions: new Map(),
    userMoved: new Set(),
    dragging: null,
    panning: null,
    view: { x: 0, y: 0, scale: 1 },
    showWeakEdges: true,
    showLabels: true,
    nodeRadius: DEFAULT_NODE_RADIUS,
    levelGap: DEFAULT_LEVEL_GAP,
    horizontalScale: 100,
    colorMetric: "r2",
    r2ColorDomain: { min: 0, max: 1 },
    r2ColorManual: false,
    runWidth: 280,
    runHeight: 220,
    runHidden: false,
    runDragging: null,
    runTab: "runs",
    sideWidth: 410,
    sideHeight: 360,
    sideHidden: false,
    sideDragging: null,
    nodeDragMoved: false,
    latexSource: "",
    latexRenderToken: 0,
    runs: [],
    collapsedRunNodes: new Set(),
  };
  const mathJaxReady = new Promise((resolve) => {
    const wait = () => {
      if (typeof MathJax.typesetPromise === "function") resolve();
      else setTimeout(wait, 80);
    };
    wait();
  });

  refreshButton.addEventListener("click", loadRuns);
  homeButton.addEventListener("click", centerRoot);
  layoutButton.addEventListener("click", () => {
    state.userMoved.clear();
    resetHorizontalScaleControl();
    state.positions = computeLayout(buildGraphNodes(), true);
    renderGraph();
  });
  weakEdgesButton.addEventListener("click", () => {
    state.showWeakEdges = !state.showWeakEdges;
    weakEdgesButton.textContent = state.showWeakEdges
      ? "Hide Weak Edges"
      : "Show Weak Edges";
    renderGraph();
  });
  labelsButton.addEventListener("click", () => {
    state.showLabels = !state.showLabels;
    labelsButton.textContent = state.showLabels ? "Hide Labels" : "Show Labels";
    renderGraph();
  });
  nodeSizeInput.addEventListener("input", () => {
    state.nodeRadius = Number(nodeSizeInput.value);
    nodeSizeValue.textContent = String(state.nodeRadius);
    renderGraph();
  });
  levelGapInput.addEventListener("input", () => {
    state.levelGap = Number(levelGapInput.value);
    levelGapValue.textContent = String(state.levelGap);
    state.userMoved.clear();
    resetHorizontalScaleControl();
    state.positions = computeLayout(buildGraphNodes(), true);
    renderGraph();
  });
  horizontalScaleInput.addEventListener("input", () => {
    const nextScale = Number(horizontalScaleInput.value);
    horizontalScaleValue.textContent = String(nextScale);
    applyHorizontalScale(nextScale / state.horizontalScale);
    state.horizontalScale = nextScale;
    renderGraph();
  });
  colorMetricSelect.addEventListener("change", () => {
    state.colorMetric = colorMetricSelect.value;
    state.r2ColorManual = false;
    syncR2ColorControls();
    renderGraph();
  });
  r2ColorMinInput.addEventListener("input", () => updateR2ColorRange("min"));
  r2ColorMaxInput.addEventListener("input", () => updateR2ColorRange("max"));
  r2ColorMinValue.addEventListener("change", () =>
    updateR2ColorRangeFromInput("min"),
  );
  r2ColorMaxValue.addEventListener("change", () =>
    updateR2ColorRangeFromInput("max"),
  );
  r2ColorMinValue.addEventListener("keydown", (event) => {
    if (event.key === "Enter") updateR2ColorRangeFromInput("min");
  });
  r2ColorMaxValue.addEventListener("keydown", (event) => {
    if (event.key === "Enter") updateR2ColorRangeFromInput("max");
  });
  exportButton.addEventListener("click", () => exportScene(exportFormat.value));
  legendTitle.addEventListener("click", () =>
    legend.classList.toggle("collapsed"),
  );
  runTabButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      setRunTab(button.dataset.runTab);
      if (state.runHidden) setRunHidden(false);
    });
  });
  runResizer.addEventListener("pointerdown", onRunResizeStart);
  runResizer.addEventListener("click", onRunResizerClick);
  sideResizer.addEventListener("pointerdown", onSideResizeStart);
  sideResizer.addEventListener("click", onSideResizerClick);
  formulaEditorToggle.addEventListener("click", () => {
    formulaEditor.classList.toggle("hidden");
    formulaEditorToggle.textContent = formulaEditor.classList.contains("hidden")
      ? "LaTeX editor"
      : "Hide LaTeX editor";
    if (!formulaEditor.classList.contains("hidden")) latexSource.focus();
  });
  latexSource.addEventListener("input", () => {
    state.latexSource = latexSource.value;
    renderLatexDisplay(state.latexSource, true);
  });
  copyLatexButton.addEventListener("click", copyLatexSource);
  detailEl.addEventListener("click", () => {
    if (detailEl.classList.contains("clickable") && state.selectedNodeId) {
      loadDetail(state.selectedNodeId);
    }
  });
  window.addEventListener("resize", () => {
    applyPanelLayout();
  });
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", onPointerUp);
  svg.addEventListener("pointerleave", onPointerUp);
  svg.addEventListener("pointerdown", onBackgroundPointerDown);
  svg.addEventListener("wheel", onWheel, { passive: false });

  const viewerParams = new URLSearchParams(location.search);
  function reportTree(message, key = null, values = {}) {
    statusEl.textContent = message;
    if (viewerParams.has("embed"))
      parent.postMessage(
        { type: "sr-tree-status", message, key, values },
        location.origin,
      );
  }
  let followLatest = true;
  function frameTree(mode) {
    const wrap = document.getElementById("graph-wrap");
    const points = [...state.positions.values()];
    if (!points.length) return;
    const width = wrap.clientWidth,
      height = wrap.clientHeight;
    if (mode === "fit") {
      const xs = points.map((p) => p.x),
        ys = points.map((p) => p.y);
      const minX = Math.min(...xs) - 50,
        maxX = Math.max(...xs) + 50;
      const minY = Math.min(...ys) - 40,
        maxY = Math.max(...ys) + 45;
      const scale = Math.min(
        1,
        (width - 30) / (maxX - minX),
        (height - 65) / (maxY - minY),
      );
      state.view = {
        scale,
        x: width / 2 - ((minX + maxX) * scale) / 2,
        y: 35 + height / 2 - ((minY + maxY) * scale) / 2,
      };
    } else {
      const latest = [...state.records.values()].sort(
        (a, b) => b.seq - a.seq,
      )[0];
      const point = latest && state.positions.get(latest.node_id);
      if (point)
        state.view = {
          scale: 1,
          x: width / 2 - point.x,
          y: height - 60 - point.y,
        };
    }
    renderGraph();
  }
  window.addEventListener("message", (event) => {
    if (
      !viewerParams.has("embed") ||
      event.source !== parent ||
      event.origin !== location.origin
    )
      return;
    if (event.data?.type === "sr-tree-theme") {
      document.documentElement.dataset.theme =
        event.data.theme === "dark" ? "dark" : "light";
      return;
    }
    if (event.data?.type !== "sr-tree-view") return;
    followLatest = event.data.mode === "latest";
    frameTree(followLatest ? "latest" : "fit");
  });
  let runListLoading = false;
  async function loadRuns() {
    if (runListLoading) return;
    runListLoading = true;
    try {
      const data = await fetchJson("/api/runs");
      state.runs = data.runs || [];
      renderRunTree(state.runs);
      if (
        data.runs.length &&
        (!state.runId || !data.runs.some((run) => runKey(run) === state.runId))
      ) {
        const requested = data.runs.find(
          (run) => run.run_id === viewerParams.get("run"),
        );
        if (requested || !viewerParams.has("run"))
          selectRun(runKey(requested || data.runs[0]));
      }
      statusEl.textContent = data.runs.length
        ? ""
        : "No active run records yet";
    } finally {
      runListLoading = false;
    }
  }

  function renderRunTree(runs) {
    runTree.innerHTML = "";
    if (!runs.length) {
      const empty = document.createElement("div");
      empty.className = "muted";
      empty.textContent = "No active run records yet.";
      runTree.appendChild(empty);
      return;
    }
    const tree = buildRunTree(runs);
    runTree.appendChild(renderTreeChildren(tree.children));
  }

  function buildRunTree(runs) {
    const root = { name: "", key: "", children: new Map(), run: null };
    for (const run of runs) {
      const parts = runPathParts(run);
      let node = root;
      let pathKey = "";
      for (const part of parts) {
        pathKey = pathKey ? `${pathKey}/${part}` : part;
        if (!node.children.has(part)) {
          node.children.set(part, {
            name: part,
            key: pathKey,
            children: new Map(),
            run: null,
          });
        }
        node = node.children.get(part);
      }
      node.run = run;
    }
    return root;
  }

  function runPathParts(run) {
    const path = String(run.path || run.run_id || "").replaceAll("\\", "/");
    const marker = "/logs/";
    const index = path.toLowerCase().lastIndexOf(marker);
    const rel =
      index >= 0
        ? path.slice(index + marker.length)
        : run.run_id || path.split("/").pop();
    return rel.split("/").filter(Boolean);
  }

  function runKey(run) {
    return run.run_key || run.run_id;
  }

  function renderTreeChildren(children) {
    const container = document.createElement("div");
    [...children.values()]
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach((node) => container.appendChild(renderTreeNode(node)));
    return container;
  }

  function renderTreeNode(node) {
    const wrap = document.createElement("div");
    wrap.className = "tree-node";
    if (!node.run && state.collapsedRunNodes.has(node.key))
      wrap.classList.add("collapsed");
    const row = document.createElement("div");
    row.className = "tree-row";
    if (node.run && runKey(node.run) === state.runId)
      row.classList.add("active");
    const caret = document.createElement("span");
    caret.className = "tree-caret";
    caret.textContent = node.children.size
      ? wrap.classList.contains("collapsed")
        ? "▸"
        : "▾"
      : "•";
    const name = document.createElement("span");
    name.className = "tree-name";
    name.textContent = node.name;
    row.append(caret, name);
    if (node.run) {
      const meta = document.createElement("span");
      meta.className = "tree-meta";
      meta.textContent = node.run.record_count;
      row.appendChild(meta);
      row.addEventListener("click", (event) => {
        event.stopPropagation();
        selectRun(runKey(node.run));
      });
    } else {
      row.addEventListener("click", (event) => {
        event.stopPropagation();
        wrap.classList.toggle("collapsed");
        if (wrap.classList.contains("collapsed"))
          state.collapsedRunNodes.add(node.key);
        else state.collapsedRunNodes.delete(node.key);
        caret.textContent = wrap.classList.contains("collapsed") ? "▸" : "▾";
      });
    }
    wrap.appendChild(row);
    if (node.children.size) {
      const childWrap = renderTreeChildren(node.children);
      childWrap.className = "tree-children";
      wrap.appendChild(childWrap);
    }
    return wrap;
  }

  async function selectRun(runId) {
    if (!runId) return;
    if (state.source) state.source.close();
    state.runId = runId;
    state.selectedNodeId = null;
    renderRunTree(state.runs);
    state.records.clear();
    state.positions.clear();
    state.userMoved.clear();
    state.lastSeq = 0;
    await loadRecords();
    startStream();
  }

  async function pollRequestedRun() {
    // The run id is already known. Do not discover/parse every historical run
    // before displaying this one; keep exactly one request in flight.
    state.runId = viewerParams.get("run");
    try {
      await loadRecords();
      reportTree(
        state.records.size
          ? `${state.records.size} 个节点 · 已同步`
          : "等待第一轮完成后生成搜索节点",
        state.records.size ? "treeSynced" : "treeAwaitingFirstNode",
        state.records.size ? { count: state.records.size } : {},
      );
    } catch (error) {
      reportTree(
        error.status === 404
          ? "等待第一轮完成后生成搜索节点"
          : `搜索树同步失败：${error.message} · 自动重试`,
        error.status === 404 ? "treeAwaitingFirstNode" : "treeSyncFailed",
        error.status === 404 ? {} : { message: error.message },
      );
    } finally {
      setTimeout(pollRequestedRun, 3000);
    }
  }

  async function loadRecords() {
    const data = await fetchJson(
      `/api/runs/${encodeURIComponent(state.runId)}/records?after_seq=${state.lastSeq}`,
    );
    if ((data.records || []).length) {
      ingestRecords(data.records);
      if (viewerParams.has("embed") && followLatest) frameTree("latest");
      else renderGraph();
    }
  }

  function startStream() {
    let cancelled = false;
    state.source = {
      close() {
        cancelled = true;
      },
    };
    async function tick() {
      if (cancelled) return;
      try {
        await loadRecords();
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        if (!cancelled) setTimeout(tick, 1500);
      }
    }
    setTimeout(tick, 1500);
  }

  function ingestRecords(records) {
    for (const record of records) {
      state.records.set(record.node_id, record);
      state.lastSeq = Math.max(state.lastSeq, record.seq || 0);
    }
    enrichToolSummaries();
    state.positions = computeLayout(buildGraphNodes(), false);
    syncR2ColorControls();
    statusEl.textContent = `${state.records.size} nodes`;
  }

  function enrichToolSummaries() {
    for (const record of state.records.values()) {
      const ancestorCounts = ancestorToolCounts(record, new Set());
      const outputCounts = new Map();
      for (const name of record.core.tool_names || []) {
        outputCounts.set(name, (outputCounts.get(name) || 0) + 1);
      }
      const existing = record.core.tool_summary || [];
      const existingPrompt = new Map(
        existing.map((item) => [item.name, Number(item.prompt_count || 0)]),
      );
      const names = [
        ...new Set([
          ...ancestorCounts.keys(),
          ...outputCounts.keys(),
          ...existing.map((item) => item.name),
        ]),
      ]
        .filter(Boolean)
        .sort();
      record.core.tool_summary = names.map((name) => ({
        name,
        display_name: displayToolName(name),
        prompt_count: Math.max(
          existingPrompt.get(name) || 0,
          ancestorCounts.get(name) || 0,
        ),
        output_count:
          outputCounts.get(name) ||
          Number(
            (existing.find((item) => item.name === name) || {}).output_count ||
              0,
          ),
      }));
    }
  }

  function ancestorToolCounts(record, seen) {
    const counts = new Map();
    for (const parent of record.parents || []) {
      const parentId = parent && parent.node_id;
      if (!parentId || seen.has(parentId)) continue;
      const parentRecord = state.records.get(parentId);
      if (!parentRecord) continue;
      seen.add(parentId);
      for (const name of parentRecord.core.tool_names || []) {
        counts.set(name, (counts.get(name) || 0) + 1);
      }
      for (const [name, count] of ancestorToolCounts(parentRecord, seen)) {
        counts.set(name, (counts.get(name) || 0) + count);
      }
    }
    return counts;
  }

  function buildGraphNodes() {
    const records = [...state.records.values()].sort(
      (a, b) => (a.seq || 0) - (b.seq || 0),
    );
    const treeIds = [
      ...new Set(records.map((record) => treeIdFor(record))),
    ].sort();
    const roots = treeIds.map((treeId, index) => ({
      node_id: rootId(treeId),
      run_id: treeId,
      tree_index: index,
      virtual_root: true,
      parents: [],
      core: { tool_names: [], tool_count: 0 },
      coord: { R: 0, C: 0, L: 0, K: 0 },
    }));
    return [
      ...roots,
      ...records.map((record) => {
        const treeId = treeIdFor(record);
        const parents = (record.parents || []).length
          ? record.parents
          : [{ node_id: rootId(treeId), relation: "virtual_root" }];
        return { ...record, run_id: treeId, parents };
      }),
    ];
  }

  function computeLayout(nodes, resetMoved) {
    const old = resetMoved ? new Map() : state.positions;
    const byId = new Map(nodes.map((node) => [node.node_id, node]));
    const children = new Map(nodes.map((node) => [node.node_id, []]));
    const indegree = new Map(nodes.map((node) => [node.node_id, 0]));
    for (const node of nodes) {
      for (const parent of node.parents || []) {
        if (!byId.has(parent.node_id)) continue;
        children.get(parent.node_id).push(node.node_id);
        indegree.set(node.node_id, (indegree.get(node.node_id) || 0) + 1);
      }
    }

    const rootNodes = nodes.filter((node) => node.virtual_root);
    const levels = new Map(rootNodes.map((node) => [node.node_id, 0]));
    const queue = rootNodes.map((node) => node.node_id);
    while (queue.length) {
      const id = queue.shift();
      const nextLevel = (levels.get(id) || 0) + 1;
      for (const childId of children.get(id) || []) {
        if (!levels.has(childId) || nextLevel > levels.get(childId)) {
          levels.set(childId, nextLevel);
        }
        indegree.set(childId, (indegree.get(childId) || 1) - 1);
        if (indegree.get(childId) <= 0) queue.push(childId);
      }
    }
    for (const node of nodes) {
      if (!levels.has(node.node_id))
        levels.set(node.node_id, fallbackLevel(node));
    }

    const byLevel = new Map();
    for (const node of nodes) {
      const level = levels.get(node.node_id);
      if (!byLevel.has(level)) byLevel.set(level, []);
      byLevel.get(level).push(node);
    }

    const positions = new Map();
    for (const root of rootNodes) {
      const existing = old.get(root.node_id);
      positions.set(
        root.node_id,
        existing && state.userMoved.has(root.node_id)
          ? existing
          : { x: 360 + root.tree_index * 520, y: 70 },
      );
    }
    const sortedLevels = [...byLevel.keys()].sort((a, b) => a - b);
    for (const level of sortedLevels) {
      if (level === 0) continue;
      const layer = byLevel.get(level);
      const treeGroups = new Map();
      for (const node of layer) {
        const treeId = treeIdFor(node);
        if (!treeGroups.has(treeId)) treeGroups.set(treeId, []);
        treeGroups.get(treeId).push(node);
      }
      for (const [treeId, group] of treeGroups) {
        group.sort((a, b) => {
          const ap = parentX(a, positions, old);
          const bp = parentX(b, positions, old);
          return ap - bp || (a.seq || 0) - (b.seq || 0);
        });
        const width = Math.max(0, (group.length - 1) * SIBLING_GAP);
        const root = positions.get(rootId(treeId));
        const center =
          averageParentX(group, positions, old) || (root && root.x) || 640;
        let start = Math.max(80, center - width / 2);
        for (let index = 0; index < group.length; index++) {
          const node = group[index];
          const existing = old.get(node.node_id);
          if (existing && state.userMoved.has(node.node_id)) {
            positions.set(node.node_id, existing);
            continue;
          }
          positions.set(node.node_id, {
            x: start + index * SIBLING_GAP,
            y: 70 + level * state.levelGap,
          });
        }
      }
    }
    return positions;
  }

  function renderGraph() {
    const nodes = buildGraphNodes();
    if (!state.positions.size) state.positions = computeLayout(nodes, false);
    const byId = new Map(nodes.map((node) => [node.node_id, node]));
    const maxX = Math.max(
      ...[...state.positions.values()].map((p) => p.x),
      1000,
    );
    const maxY = Math.max(
      ...[...state.positions.values()].map((p) => p.y),
      650,
    );
    svg.setAttribute("width", Math.max(1200, maxX + 220));
    svg.setAttribute("height", Math.max(760, maxY + 160));
    if (viewerParams.has("embed")) {
      const wrap = document.getElementById("graph-wrap");
      svg.setAttribute("width", wrap.clientWidth);
      svg.setAttribute("height", wrap.clientHeight);
    }
    svg.innerHTML = "";

    const edgeGroup = svgEl("g");
    const nodeGroup = svgEl("g");
    const viewport = svgEl("g");
    viewport.setAttribute("transform", viewTransform());
    viewport.append(edgeGroup, nodeGroup);
    svg.append(viewport);

    for (const node of nodes) {
      if (node.virtual_root) continue;
      const target = state.positions.get(node.node_id);
      for (const parent of node.parents || []) {
        if (parent.relation === "context_merge" && !state.showWeakEdges)
          continue;
        if (!byId.has(parent.node_id)) continue;
        const source = state.positions.get(parent.node_id);
        if (!source || !target) continue;
        const path = svgEl("path");
        const mid = (source.y + target.y) / 2;
        path.setAttribute(
          "d",
          `M${source.x},${source.y} C${source.x},${mid} ${target.x},${mid} ${target.x},${target.y}`,
        );
        path.setAttribute(
          "class",
          `edge ${parent.relation === "context_merge" ? "weak" : "strong"} ${parent.node_id.startsWith(ROOT_PREFIX) ? "root" : ""}`,
        );
        edgeGroup.appendChild(path);
      }
    }

    for (const node of nodes) {
      const point = state.positions.get(node.node_id);
      if (!point) continue;
      const circle = svgEl("circle");
      const radius = nodeRadius(node);
      circle.setAttribute("cx", point.x);
      circle.setAttribute("cy", point.y);
      circle.setAttribute("r", radius);
      circle.setAttribute("class", `node ${node.virtual_root ? "root" : ""}`);
      circle.setAttribute(
        "fill",
        node.virtual_root ? "var(--root)" : colorFor(node),
      );
      circle.dataset.nodeId = node.node_id;
      circle.addEventListener("pointerdown", onPointerDown);
      circle.addEventListener("click", () => {
        if (state.nodeDragMoved) return;
        showCore(node);
        if (viewerParams.has("embed") && !node.virtual_root)
          parent.postMessage(
            {
              type: "sr-tree-node-selected",
              coord: node.coord,
              nodeId: node.node_id,
              runId: node.run_id || state.runId,
            },
            location.origin,
          );
      });
      nodeGroup.appendChild(circle);

      if (state.showLabels) {
        const label = svgEl("text");
        label.setAttribute("x", point.x);
        label.setAttribute("y", point.y + radius + 15);
        label.setAttribute(
          "class",
          `node-label ${node.virtual_root ? "root-label" : ""}`,
        );
        label.textContent = node.virtual_root
          ? `run ${shortTreeId(node.run_id)}`
          : node.node_label ||
            `R${node.coord.R} C${node.coord.C} L${node.coord.L} K${node.coord.K}`;
        nodeGroup.appendChild(label);
      }
    }
  }

  function onPointerDown(event) {
    const nodeId = event.target.dataset.nodeId;
    if (!nodeId) return;
    event.stopPropagation();
    const point = clientToSvg(event);
    const current = state.positions.get(nodeId);
    if (!current) return;
    const dragFactors = collectDragPositionFactors(nodeId);
    const startPositions = new Map(
      [...dragFactors.keys()]
        .map((id) => [id, state.positions.get(id)])
        .filter(([, position]) => Boolean(position))
        .map(([id, position]) => [id, { x: position.x, y: position.y }]),
    );
    state.dragging = {
      nodeId,
      startPointerX: point.x,
      startPositions,
      dragFactors,
    };
    state.nodeDragMoved = false;
    event.target.setPointerCapture(event.pointerId);
  }

  function onBackgroundPointerDown(event) {
    followLatest = false;
    if (event.target !== svg) return;
    const point = clientPoint(event);
    state.panning = {
      x: point.x,
      y: point.y,
      viewX: state.view.x,
      viewY: state.view.y,
    };
    svg.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event) {
    if (state.dragging) {
      const point = clientToSvg(event);
      const rootStart = state.dragging.startPositions.get(
        state.dragging.nodeId,
      );
      if (!rootStart) return;
      const deltaX = point.x - state.dragging.startPointerX;
      for (const [nodeId, position] of state.dragging.startPositions) {
        const factor = state.dragging.dragFactors.get(nodeId) || 0;
        state.positions.set(nodeId, {
          x: position.x + deltaX * factor,
          y: position.y,
        });
        state.userMoved.add(nodeId);
      }
      state.nodeDragMoved = true;
      renderGraph();
    } else if (state.panning) {
      const point = clientPoint(event);
      state.view.x = state.panning.viewX + point.x - state.panning.x;
      state.view.y = state.panning.viewY + point.y - state.panning.y;
      renderGraph();
    }
  }

  function onPointerUp() {
    state.dragging = null;
    state.panning = null;
    setTimeout(() => {
      state.nodeDragMoved = false;
    }, 0);
  }

  function collectDragPositionFactors(rootNodeId) {
    const nodes = buildGraphNodes();
    const byId = new Map(nodes.map((node) => [node.node_id, node]));
    const children = new Map(nodes.map((node) => [node.node_id, []]));
    const parents = new Map(nodes.map((node) => [node.node_id, []]));
    for (const node of nodes) {
      for (const parent of node.parents || []) {
        if (!byId.has(parent.node_id)) continue;
        if (parent.relation === "context_merge" && !state.showWeakEdges)
          continue;
        children.get(parent.node_id).push(node.node_id);
        parents.get(node.node_id).push(parent.node_id);
      }
    }

    const reachable = new Set();
    const queue = [rootNodeId];
    while (queue.length) {
      const nodeId = queue.shift();
      if (!nodeId || reachable.has(nodeId) || !byId.has(nodeId)) continue;
      reachable.add(nodeId);
      for (const childId of children.get(nodeId) || []) queue.push(childId);
    }

    const factors = new Map([[rootNodeId, 1]]);
    const orderedReachable = [...reachable].sort((a, b) => {
      const nodeA = byId.get(a);
      const nodeB = byId.get(b);
      return (
        fallbackLevel(nodeA) - fallbackLevel(nodeB) ||
        (nodeA.seq || 0) - (nodeB.seq || 0)
      );
    });
    for (let pass = 0; pass < orderedReachable.length; pass++) {
      let changed = false;
      for (const nodeId of orderedReachable) {
        if (nodeId === rootNodeId) continue;
        const parentIds = parents.get(nodeId) || [];
        if (!parentIds.length) continue;
        const factor =
          parentIds.reduce(
            (sum, parentId) => sum + (factors.get(parentId) || 0),
            0,
          ) / parentIds.length;
        if (factor <= 0) continue;
        if (Math.abs((factors.get(nodeId) || 0) - factor) > 1e-6) {
          factors.set(nodeId, factor);
          changed = true;
        }
      }
      if (!changed) break;
    }
    return factors;
  }

  function onWheel(event) {
    followLatest = false;
    event.preventDefault();
    const anchor = clientPoint(event);
    const before = clientToSvg(event);
    const factor = Math.exp(-event.deltaY * 0.001);
    const nextScale = Math.max(0.25, Math.min(3.5, state.view.scale * factor));
    if (nextScale === state.view.scale) return;
    state.view.scale = nextScale;
    state.view.x = anchor.x - before.x * state.view.scale;
    state.view.y = anchor.y - before.y * state.view.scale;
    renderGraph();
  }

  function centerRoot() {
    const nodes = buildGraphNodes();
    if (!state.positions.size) state.positions = computeLayout(nodes, false);
    const selectedRecord = state.selectedNodeId
      ? state.records.get(state.selectedNodeId)
      : null;
    const selectedTreeId = selectedRecord && treeIdFor(selectedRecord);
    const root =
      nodes.find(
        (node) =>
          node.virtual_root && selectedTreeId && node.run_id === selectedTreeId,
      ) || nodes.find((node) => node.virtual_root);
    if (!root) return;
    const rootPoint = state.positions.get(root.node_id);
    if (!rootPoint) return;
    const wrap = document.getElementById("graph-wrap");
    const rect = wrap.getBoundingClientRect();
    const center = screenToSvgViewport(
      rect.left + rect.width / 2,
      rect.top + rect.height / 2,
    );
    state.view.x = center.x - rootPoint.x * state.view.scale;
    state.view.y = center.y - rootPoint.y * state.view.scale;
    renderGraph();
  }

  function onRunResizeStart(event) {
    if (state.runHidden) return;
    event.preventDefault();
    event.stopPropagation();
    const mobile = isNarrowLayout();
    state.runDragging = {
      mobile,
      startX: event.clientX,
      startY: event.clientY,
      startWidth: state.runWidth,
      startHeight: state.runHeight,
      moved: false,
    };
    runResizer.classList.add("dragging");
    runResizer.setPointerCapture(event.pointerId);
    runResizer.addEventListener("pointermove", onRunResizeMove);
    runResizer.addEventListener("pointerup", onRunResizeEnd);
    runResizer.addEventListener("pointercancel", onRunResizeEnd);
  }

  function onRunResizeMove(event) {
    if (!state.runDragging) return;
    const drag = state.runDragging;
    const delta = drag.mobile
      ? event.clientY - drag.startY
      : event.clientX - drag.startX;
    if (Math.abs(delta) > 2) drag.moved = true;
    if (drag.mobile) {
      const nextHeight = drag.startHeight + delta;
      if (nextHeight < 120) {
        setRunHidden(true);
        return;
      }
      state.runHeight = Math.max(
        150,
        Math.min(window.innerHeight * 0.55, nextHeight),
      );
    } else {
      const nextWidth = drag.startWidth + delta;
      if (nextWidth < 140) {
        setRunHidden(true);
        return;
      }
      state.runWidth = Math.max(
        180,
        Math.min(window.innerWidth * 0.45, nextWidth),
      );
    }
    applyPanelLayout();
  }

  function onRunResizeEnd(event) {
    if (runResizer.hasPointerCapture(event.pointerId)) {
      runResizer.releasePointerCapture(event.pointerId);
    }
    runResizer.classList.remove("dragging");
    runResizer.removeEventListener("pointermove", onRunResizeMove);
    runResizer.removeEventListener("pointerup", onRunResizeEnd);
    runResizer.removeEventListener("pointercancel", onRunResizeEnd);
    setTimeout(() => {
      state.runDragging = null;
    }, 0);
  }

  function onRunResizerClick() {
    if (state.runDragging && state.runDragging.moved) return;
    if (state.runHidden) setRunHidden(false);
  }

  function setRunTab(tab) {
    state.runTab = tab === "controls" ? "controls" : "runs";
    runsPanel.classList.toggle("hidden", state.runTab !== "runs");
    controlsPanel.classList.toggle("hidden", state.runTab !== "controls");
    runTabButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.runTab === state.runTab);
    });
  }

  function setRunHidden(hidden) {
    state.runHidden = hidden;
    main.classList.toggle("run-hidden", hidden);
    runResizer.title = hidden
      ? "Click to show runs panel"
      : "Drag to resize runs panel";
    applyPanelLayout();
  }

  function applyHorizontalScale(factor) {
    if (!Number.isFinite(factor) || factor <= 0) return;
    const nodes = buildGraphNodes();
    if (!state.positions.size) state.positions = computeLayout(nodes, false);
    const positioned = nodes
      .map((node) => [node.node_id, state.positions.get(node.node_id)])
      .filter(([, position]) => Boolean(position));
    if (!positioned.length) return;
    const xs = positioned.map(([, position]) => position.x);
    const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
    for (const [nodeId, position] of positioned) {
      state.positions.set(nodeId, {
        x: centerX + (position.x - centerX) * factor,
        y: position.y,
      });
      state.userMoved.add(nodeId);
    }
  }

  function resetHorizontalScaleControl() {
    state.horizontalScale = 100;
    horizontalScaleInput.value = "100";
    horizontalScaleValue.textContent = "100";
  }

  function onSideResizeStart(event) {
    if (state.sideHidden) return;
    event.preventDefault();
    event.stopPropagation();
    const mobile = isNarrowLayout();
    state.sideDragging = {
      mobile,
      startX: event.clientX,
      startY: event.clientY,
      startWidth: state.sideWidth,
      startHeight: state.sideHeight,
      moved: false,
    };
    sideResizer.classList.add("dragging");
    sideResizer.setPointerCapture(event.pointerId);
    sideResizer.addEventListener("pointermove", onSideResizeMove);
    sideResizer.addEventListener("pointerup", onSideResizeEnd);
    sideResizer.addEventListener("pointercancel", onSideResizeEnd);
  }

  function onSideResizeMove(event) {
    if (!state.sideDragging) return;
    const drag = state.sideDragging;
    const delta = drag.mobile
      ? event.clientY - drag.startY
      : drag.startX - event.clientX;
    if (Math.abs(delta) > 2) drag.moved = true;
    if (drag.mobile) {
      const nextHeight = drag.startHeight - delta;
      if (nextHeight < 180) {
        setSideHidden(true);
        return;
      }
      state.sideHeight = Math.max(
        220,
        Math.min(window.innerHeight * 0.7, nextHeight),
      );
    } else {
      const nextWidth = drag.startWidth + delta;
      if (nextWidth < 240) {
        setSideHidden(true);
        return;
      }
      state.sideWidth = Math.max(
        260,
        Math.min(window.innerWidth * 0.72, nextWidth),
      );
    }
    applyPanelLayout();
  }

  function onSideResizeEnd(event) {
    if (sideResizer.hasPointerCapture(event.pointerId)) {
      sideResizer.releasePointerCapture(event.pointerId);
    }
    sideResizer.classList.remove("dragging");
    sideResizer.removeEventListener("pointermove", onSideResizeMove);
    sideResizer.removeEventListener("pointerup", onSideResizeEnd);
    sideResizer.removeEventListener("pointercancel", onSideResizeEnd);
    setTimeout(() => {
      state.sideDragging = null;
    }, 0);
  }

  function onSideResizerClick() {
    if (state.sideDragging && state.sideDragging.moved) return;
    if (state.sideHidden) setSideHidden(false);
  }

  function setSideHidden(hidden) {
    state.sideHidden = hidden;
    main.classList.toggle("side-hidden", hidden);
    sideResizer.title = hidden
      ? "Click to show details panel"
      : "Drag to resize details panel";
    applyPanelLayout();
  }

  function applyPanelLayout() {
    main.style.setProperty("--run-width", `${Math.round(state.runWidth)}px`);
    main.style.setProperty("--side-width", `${Math.round(state.sideWidth)}px`);
    if (isNarrowLayout()) {
      const runRow = state.runHidden ? "0" : `${Math.round(state.runHeight)}px`;
      const runHandle = state.runHidden ? "30px" : "28px";
      const sideHandle = state.sideHidden ? "30px" : "28px";
      const sideRow = state.sideHidden
        ? "0"
        : `${Math.round(state.sideHeight)}px`;
      main.style.gridTemplateRows = `${runRow} ${runHandle} minmax(430px, 58vh) ${sideHandle} ${sideRow}`;
    } else {
      main.style.gridTemplateRows = "";
    }
  }

  function isNarrowLayout() {
    return window.matchMedia("(max-width: 900px)").matches;
  }

  function clientToSvg(event) {
    const point = clientPoint(event);
    return {
      x: (point.x - state.view.x) / state.view.scale,
      y: (point.y - state.view.y) / state.view.scale,
    };
  }

  function clientPoint(event) {
    return screenToSvgViewport(event.clientX, event.clientY);
  }

  function screenToSvgViewport(clientX, clientY) {
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }

  function viewTransform() {
    return `translate(${state.view.x} ${state.view.y}) scale(${state.view.scale})`;
  }

  function colorFor(record) {
    const valueRaw = metricValueFor(record, state.colorMetric);
    if (!Number.isFinite(valueRaw)) return "#718096";
    const domain = r2ColorDomain();
    if (domain.max <= domain.min) return "#8b0000";
    const value = Math.max(domain.min, Math.min(domain.max, valueRaw));
    let scaled = (value - domain.min) / (domain.max - domain.min);
    if (metricLowerIsBetter(state.colorMetric)) scaled = 1 - scaled;
    if (scaled <= 0.5) {
      const t = scaled / 0.5;
      return rgbHex(139 + (245 - 139) * t, 0 + (197 - 0) * t, 0);
    }
    const t = (scaled - 0.5) / 0.5;
    return rgbHex(245 + (0 - 245) * t, 197 + (104 - 197) * t, 0 + (55 - 0) * t);
  }

  function r2ColorDomain() {
    return state.r2ColorDomain;
  }

  function dataR2Domain() {
    const values = metricValues(state.colorMetric);
    if (!values.length) return { min: 0, max: 1 };
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return { min: Math.min(0, min), max: Math.max(1, max) };
    return { min, max };
  }

  function metricValues(metric) {
    return [...state.records.values()]
      .map((record) => metricValueFor(record, metric))
      .filter(Number.isFinite);
  }

  function metricValueFor(record, metric) {
    const score = record.core && record.core.score;
    if (!score || typeof score !== "object") return NaN;
    for (const key of metricKeys(metric)) {
      const value = Number(score[key]);
      if (Number.isFinite(value)) return value;
    }
    return NaN;
  }

  function metricKeys(metric) {
    const aliases = {
      r2: ["r2", "r_2", "R2"],
      mse: ["mse", "MSE"],
      rmse: ["rmse", "RMSE"],
      smape: ["smape", "s_mape", "SMAPE"],
      mape: ["mape", "MAPE"],
      mae: ["mae", "MAE"],
      spearman_r: [
        "spearman_r",
        "spearman",
        "spearmanr",
        "spearman_rho",
        "spearman rho",
        "Spearman r",
      ],
      pearson_r: ["pearson_r", "pearson", "pearsonr", "pearson r", "Pearson r"],
    };
    return aliases[metric] || [metric];
  }

  function metricLowerIsBetter(metric) {
    return new Set(["mse", "rmse", "mae", "mape", "smape"]).has(metric);
  }

  function syncR2ColorControls() {
    const dataDomain = dataR2Domain();
    const controlDomain = r2ControlDomain(dataDomain);
    const step = r2Step(controlDomain);
    for (const input of [r2ColorMinInput, r2ColorMaxInput]) {
      input.min = String(controlDomain.min);
      input.max = String(controlDomain.max);
      input.step = String(step);
    }
    for (const input of [r2ColorMinValue, r2ColorMaxValue]) {
      input.step = String(step);
    }
    if (!state.r2ColorManual) {
      state.r2ColorDomain = dataDomain;
    } else if (state.r2ColorDomain.min >= state.r2ColorDomain.max) {
      state.r2ColorDomain = dataDomain;
    }
    r2ColorMinInput.value = String(state.r2ColorDomain.min);
    r2ColorMaxInput.value = String(state.r2ColorDomain.max);
    syncR2ColorInputsAndTrack();
  }

  function updateR2ColorRange(changed) {
    const controlDomain = r2ControlDomain(dataR2Domain());
    const minGap = r2Step(controlDomain);
    let minValue = Number(r2ColorMinInput.value);
    let maxValue = Number(r2ColorMaxInput.value);
    if (changed === "min" && minValue >= maxValue) {
      minValue = maxValue - minGap;
      r2ColorMinInput.value = String(minValue);
    }
    if (changed === "max" && maxValue <= minValue) {
      maxValue = minValue + minGap;
      r2ColorMaxInput.value = String(maxValue);
    }
    state.r2ColorManual = true;
    state.r2ColorDomain = { min: minValue, max: maxValue };
    syncR2ColorInputsAndTrack();
    renderGraph();
  }

  function updateR2ColorRangeFromInput(changed) {
    const referenceDomain = r2ControlDomain(dataR2Domain());
    const minGap = r2Step(referenceDomain);
    let minValue = Number(r2ColorMinValue.value);
    let maxValue = Number(r2ColorMaxValue.value);
    if (!Number.isFinite(minValue)) minValue = state.r2ColorDomain.min;
    if (!Number.isFinite(maxValue)) maxValue = state.r2ColorDomain.max;
    if (changed === "min" && minValue >= maxValue) minValue = maxValue - minGap;
    if (changed === "max" && maxValue <= minValue) maxValue = minValue + minGap;
    state.r2ColorManual = true;
    state.r2ColorDomain = { min: minValue, max: maxValue };
    const controlDomain = r2ControlDomain(dataR2Domain());
    for (const input of [r2ColorMinInput, r2ColorMaxInput]) {
      input.min = String(controlDomain.min);
      input.max = String(controlDomain.max);
      input.step = String(r2Step(controlDomain));
    }
    syncR2ColorInputsAndTrack();
    renderGraph();
  }

  function syncR2ColorInputsAndTrack() {
    const domain = state.r2ColorDomain;
    r2ColorMinValue.value = formatR2(domain.min);
    r2ColorMaxValue.value = formatR2(domain.max);
    const controlDomain = r2ControlDomain(dataR2Domain());
    r2ColorMinInput.value = String(domain.min);
    r2ColorMaxInput.value = String(domain.max);
    const span = controlDomain.max - controlDomain.min || 1;
    const low = (100 * (domain.min - controlDomain.min)) / span;
    const high = (100 * (domain.max - controlDomain.min)) / span;
    const rangePair = r2ColorMinInput.closest(".range-pair");
    rangePair.style.setProperty("--low", `${Math.max(0, Math.min(100, low))}%`);
    rangePair.style.setProperty(
      "--high",
      `${Math.max(0, Math.min(100, high))}%`,
    );
  }

  function r2ControlDomain(dataDomain) {
    if (!state.r2ColorManual) return dataDomain;
    const min = Math.min(dataDomain.min, state.r2ColorDomain.min);
    const max = Math.max(dataDomain.max, state.r2ColorDomain.max);
    if (min === max) return { min: min - 0.5, max: max + 0.5 };
    return { min, max };
  }

  function r2Step(domain) {
    const span = Math.abs(domain.max - domain.min);
    return span > 0 ? Math.max(span / 100, 0.0001) : 0.01;
  }

  function formatR2(value) {
    return Number(value)
      .toFixed(3)
      .replace(/\.?0+$/, "");
  }

  function rgbHex(r, g, b) {
    const toHex = (value) => Math.round(value).toString(16).padStart(2, "0");
    return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
  }

  function nodeRadius(node) {
    return node.virtual_root ? state.nodeRadius + 5 : state.nodeRadius;
  }

  function showCore(record) {
    if (record.virtual_root) {
      state.selectedNodeId = null;
      document.getElementById("node-title").textContent = "Virtual root";
      document.getElementById("node-subtitle").textContent =
        `Run ${record.run_id}`;
      document.getElementById("metrics").innerHTML = "";
      setFormula(null, null);
      renderPreview(null);
      document.getElementById("tool-call").innerHTML = "";
      setDetailText(
        "Drag nodes horizontally to adjust layout. Auto Layout resets manual positions.",
        false,
      );
      return;
    }
    state.selectedNodeId = record.node_id;
    document.getElementById("node-title").textContent =
      record.node_label || record.node_id;
    document.getElementById("node-subtitle").textContent =
      `${(record.core.tool_names || []).join(", ") || "no tools"}`;
    setFormula(record.core.formula, record.core.formula_latex);
    renderPreview(record, false);
    renderToolCall(record.core.tool_summary || fallbackToolSummary(record));
    setDetailText("Click this Detail area to load detail.", true);
    const metrics = document.getElementById("metrics");
    metrics.innerHTML = "";
    const score = record.core.score || {};
    for (const key of ["mse", "rmse", "mae", "r2"]) {
      const box = document.createElement("div");
      box.className = "metric";
      box.innerHTML = `<span>${key}</span><strong>${score[key] ?? "n/a"}</strong>`;
      metrics.appendChild(box);
    }
  }

  function setFormula(formula, latex) {
    const codeBox = document.getElementById("formula-code");
    if (!formula) {
      state.latexSource = "";
      latexSource.value = "";
      latexSource.disabled = true;
      copyLatexButton.disabled = true;
      formulaEditorStatus.textContent = "";
      renderLatexDisplay("", true);
      codeBox.textContent = "";
      return;
    }
    state.latexSource = latex || formula;
    latexSource.value = state.latexSource;
    latexSource.disabled = false;
    copyLatexButton.disabled = false;
    formulaEditorStatus.textContent = "";
    renderLatexDisplay(state.latexSource, Boolean(latex));
    codeBox.textContent = formula;
  }

  function renderLatexDisplay(source, parseAsLatex) {
    state.latexRenderToken += 1;
    const token = state.latexRenderToken;
    if (!source) {
      formulaLatex.textContent = "(no candidate formula)";
      formulaLatex.classList.add("muted");
      return;
    }
    formulaLatex.classList.remove("muted");
    formulaLatex.textContent = latexDisplaySource(source, parseAsLatex);
    mathJaxReady
      .then(() => {
        if (token !== state.latexRenderToken) return null;
        return MathJax.typesetPromise([formulaLatex]);
      })
      .catch((error) => {
        formulaEditorStatus.textContent = `Render failed: ${error.message || error}`;
      });
  }

  function latexDisplaySource(source, parseAsLatex) {
    const text = String(source || "").trim();
    if (!text) return "(no candidate formula)";
    if (
      text.startsWith("$$") ||
      text.startsWith("\\[") ||
      text.startsWith("$") ||
      text.startsWith("\\(")
    )
      return text;
    return parseAsLatex || /[\\_^{}]/.test(text) ? `$$${text}$$` : text;
  }

  async function copyLatexSource() {
    const text = latexSource.value;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      formulaEditorStatus.textContent = "Copied";
    } catch {
      latexSource.focus();
      latexSource.select();
      document.execCommand("copy");
      formulaEditorStatus.textContent = "Copied";
    }
    setTimeout(() => {
      if (formulaEditorStatus.textContent === "Copied")
        formulaEditorStatus.textContent = "";
    }, 1200);
  }

  function renderToolCall(summary) {
    const box = document.getElementById("tool-call");
    box.innerHTML = "";
    if (!summary.length) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "No tools in prompt or output.";
      box.appendChild(empty);
      return;
    }
    for (const item of summary) {
      const active = Number(item.output_count || 0) > 0;
      const wrap = document.createElement("div");
      wrap.className = `tool-item ${active ? "active" : "inactive"}`;
      const icon = document.createElement("div");
      icon.className = "tool-icon";
      icon.style.background = toolColor(item.name);
      icon.title = item.display_name || displayToolName(item.name);
      icon.textContent = toolInitial(item.name);
      if (Number(item.output_count || 0) > 0) {
        const badge = document.createElement("span");
        badge.className = "tool-badge";
        badge.textContent = item.output_count;
        icon.appendChild(badge);
      }
      const count = document.createElement("div");
      count.className = "tool-count";
      count.textContent = `${item.prompt_count || 0} in prompt`;
      wrap.append(icon, count);
      box.appendChild(wrap);
    }
  }

  function fallbackToolSummary(record) {
    const counts = new Map();
    for (const name of record.core.tool_names || []) {
      counts.set(name, (counts.get(name) || 0) + 1);
    }
    return [...counts.entries()].map(([name, outputCount]) => ({
      name,
      display_name: displayToolName(name),
      prompt_count: 0,
      output_count: outputCount,
    }));
  }

  function detailToolSummary(record) {
    const promptCounts = countPromptTools(
      record.detail && record.detail.prompt,
    );
    const outputCounts = new Map();
    for (const name of record.core.tool_names || []) {
      outputCounts.set(name, (outputCounts.get(name) || 0) + 1);
    }
    const names = [
      ...new Set([...promptCounts.keys(), ...outputCounts.keys()]),
    ].sort();
    return names.map((name) => ({
      name,
      display_name: displayToolName(name),
      prompt_count: promptCounts.get(name) || 0,
      output_count: outputCounts.get(name) || 0,
    }));
  }

  function countPromptTools(prompt) {
    const counts = new Map();
    if (!Array.isArray(prompt)) return counts;
    for (const msg of prompt) {
      if (msg && msg.role === "tool" && msg.name) {
        counts.set(msg.name, (counts.get(msg.name) || 0) + 1);
      }
    }
    for (const msg of prompt) {
      for (const call of (msg && msg.tool_calls) || []) {
        const name = call.name || (call.function && call.function.name);
        if (name && !counts.has(name)) counts.set(name, 0);
      }
    }
    return counts;
  }

  function displayToolName(name) {
    return String(name || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function toolInitial(name) {
    const words = displayToolName(name).split(/\s+/).filter(Boolean);
    if (!words.length) return "?";
    return words
      .slice(0, 2)
      .map((word) => word[0])
      .join("");
  }

  function toolColor(name) {
    const palette = [
      "#1F2C7E",
      "#6f5bd6",
      "#b54f9b",
      "#c75a2b",
      "#3f7fba",
      "#7b6d2d",
      "#2f855a",
      "#a33f4a",
      "#4a6f28",
      "#8b5e34",
    ];
    let hash = 0;
    const text = String(name || "");
    for (let i = 0; i < text.length; i++)
      hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
    return palette[hash % palette.length];
  }

  async function loadDetail(nodeId) {
    const record = await fetchJson(
      `/api/runs/${encodeURIComponent(state.runId)}/records/${encodeURIComponent(nodeId)}`,
    );
    showCore(record);
    renderPreview(record, true);
    renderToolCall(record.core.tool_summary || detailToolSummary(record));
    renderJsonDetail(record.detail || {});
  }

  function renderPreview(record, includeHistory = false) {
    const preview = document.getElementById("preview");
    preview.innerHTML = "";
    if (!record) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "No preview.";
      preview.appendChild(empty);
      return;
    }

    const historyMessages = includeHistory
      ? historyChatMessages(record.detail && record.detail.prompt)
      : [];
    if (historyMessages.length) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "history-toggle";
      toggle.textContent = `Show history (${historyMessages.length} messages)`;
      const history = document.createElement("div");
      history.className = "chat-history hidden";
      historyMessages.forEach((message) =>
        history.appendChild(chatBubble(message)),
      );
      toggle.addEventListener("click", () => {
        const hidden = history.classList.toggle("hidden");
        toggle.textContent = `${hidden ? "Show" : "Hide"} history (${historyMessages.length} messages)`;
      });
      preview.append(toggle, history);
    }

    preview.appendChild(
      chatBubble({
        role: "agent",
        label: "Agent output",
        text: includeHistory
          ? formatAgentOutput(record)
          : record.core.content_preview || "No agent output.",
      }),
    );
  }

  function historyChatMessages(prompt) {
    if (!Array.isArray(prompt)) return [];
    return prompt.map((message, index) => {
      const role = message && message.role ? String(message.role) : "message";
      const name = message && message.name ? ` · ${message.name}` : "";
      const textParts = [];
      const content = stringifyContent(message && message.content);
      if (content) textParts.push(content);
      const toolCalls = formatToolCalls(message && message.tool_calls);
      if (toolCalls) textParts.push(`Tool Calls:\n${toolCalls}`);
      return {
        role: chatRole(role),
        label: `${displayRole(role)}${name} #${index + 1}`,
        text: textParts.join("\n\n") || "(empty message)",
      };
    });
  }

  function chatBubble(message) {
    const wrap = document.createElement("div");
    wrap.className = `chat-bubble ${message.role}`;
    const label = document.createElement("div");
    label.className = "chat-label";
    label.textContent = message.label;
    const box = document.createElement("div");
    box.className = "chat-bubble-box";
    const topResize = document.createElement("div");
    topResize.className = "bubble-resize";
    topResize.title = "Drag to resize";
    const body = document.createElement("div");
    body.className = "chat-bubble-body";
    const pre = document.createElement("pre");
    pre.textContent = message.text || "";
    body.appendChild(pre);
    const bottomResize = document.createElement("div");
    bottomResize.className = "bubble-resize";
    bottomResize.title = "Drag to resize";
    attachBubbleResize(topResize, body, "top");
    attachBubbleResize(bottomResize, body, "bottom");
    box.append(topResize, body, bottomResize);
    wrap.append(label, box);
    return wrap;
  }

  function attachBubbleResize(handle, body, edge) {
    handle.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const startY = event.clientY;
      const startHeight = body.getBoundingClientRect().height;
      const minHeight = 54;
      const maxHeight = Math.max(120, window.innerHeight * 0.55);
      handle.setPointerCapture(event.pointerId);
      const move = (moveEvent) => {
        const delta = moveEvent.clientY - startY;
        const signedDelta = edge === "top" ? -delta : delta;
        const nextHeight = Math.max(
          minHeight,
          Math.min(maxHeight, startHeight + signedDelta),
        );
        body.style.height = `${nextHeight}px`;
        body.style.maxHeight = "none";
      };
      const stop = (upEvent) => {
        handle.releasePointerCapture(upEvent.pointerId);
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", stop);
        handle.removeEventListener("pointercancel", stop);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", stop);
      handle.addEventListener("pointercancel", stop);
    });
  }

  function formatAgentOutput(record) {
    const detail = record.detail || {};
    const parts = [];
    const reason = reasoningText(detail.message);
    if (reason) parts.push(`Reason:\n${reason}`);
    const content = stringifyContent(detail.content);
    if (content) parts.push(`Content:\n${content}`);
    const toolCalls = formatToolCalls(detail.tool_calls);
    if (toolCalls) parts.push(`Tool Calls:\n${toolCalls}`);
    return (
      parts.join("\n\n") || record.core.content_preview || "No agent output."
    );
  }

  function reasoningText(message) {
    if (!message || typeof message !== "object") return "";
    if (message.reasoning) return String(message.reasoning).trim();
    if (!Array.isArray(message.reasoning_details)) return "";
    return message.reasoning_details
      .map((item) => (item && typeof item === "object" ? item.text : ""))
      .filter(Boolean)
      .join("\n")
      .trim();
  }

  function stringifyContent(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value.trim();
    return JSON.stringify(value, null, 2);
  }

  function formatToolCalls(toolCalls) {
    if (!Array.isArray(toolCalls) || !toolCalls.length) return "";
    return toolCalls
      .map((call, index) => {
        const name =
          (call && (call.name || (call.function && call.function.name))) ||
          "tool";
        const params =
          (call &&
            (call.params ||
              call.arguments ||
              (call.function && call.function.arguments))) ||
          {};
        const renderedParams =
          typeof params === "string" ? params : JSON.stringify(params, null, 2);
        return `${String(index + 1).padStart(2, "0")}. ${name}(${renderedParams})`;
      })
      .join("\n");
  }

  function chatRole(role) {
    if (role === "assistant") return "agent";
    if (role === "user") return "user";
    if (role === "tool") return "tool";
    return "system";
  }

  function displayRole(role) {
    if (role === "assistant") return "Assistant";
    if (role === "user") return "User";
    if (role === "tool") return "Tool";
    if (role === "system") return "System";
    return displayToolName(role);
  }

  function setDetailText(text, clickable = false) {
    detailEl.textContent = text;
    detailEl.classList.toggle("clickable", clickable);
  }

  function renderJsonDetail(value) {
    detailEl.classList.remove("clickable");
    detailEl.innerHTML = "";
    detailEl.appendChild(jsonNode(value, null, true));
  }

  function jsonNode(value, key, isRoot = false) {
    const wrapper = document.createElement("div");
    const type = jsonType(value);
    const row = document.createElement("div");
    row.className = "json-row";
    const toggle = document.createElement("span");
    toggle.className =
      type === "object" || type === "array"
        ? "json-toggle"
        : "json-toggle empty";
    toggle.textContent = type === "object" || type === "array" ? "▾" : " ";
    row.appendChild(toggle);
    if (key !== null) {
      const keySpan = document.createElement("span");
      keySpan.className = "json-key";
      keySpan.textContent = JSON.stringify(String(key)) + ": ";
      row.appendChild(keySpan);
    }

    if (type !== "object" && type !== "array") {
      row.appendChild(jsonPrimitive(value, type));
      wrapper.appendChild(row);
      return wrapper;
    }

    const entries =
      type === "array"
        ? value.map((item, index) => [index, item])
        : Object.entries(value);
    const open = bracket(type === "array" ? "[" : "{");
    const close = bracket(type === "array" ? "]" : "}");
    const matchId =
      globalThis.crypto && crypto.randomUUID
        ? crypto.randomUUID()
        : String(Math.random());
    open.dataset.matchId = close.dataset.matchId = matchId;
    row.appendChild(open);
    const summary = document.createElement("span");
    summary.className = "json-summary json-hidden";
    summary.textContent =
      type === "array"
        ? ` ${entries.length} items `
        : ` ${entries.length} keys `;
    row.appendChild(summary);
    row.appendChild(close);
    wrapper.appendChild(row);

    const children = document.createElement("div");
    children.className = isRoot ? "json-node" : "json-node";
    entries.forEach(([childKey, childValue], index) => {
      const child = jsonNode(childValue, childKey);
      if (index < entries.length - 1)
        child.appendChild(document.createTextNode(","));
      children.appendChild(child);
    });
    const closingRow = document.createElement("div");
    closingRow.className = "json-row";
    closingRow.appendChild(document.createElement("span")).className =
      "json-toggle empty";
    const closingBracket = bracket(type === "array" ? "]" : "}");
    closingBracket.dataset.matchId = matchId;
    closingRow.appendChild(closingBracket);
    children.appendChild(closingRow);
    wrapper.appendChild(children);

    const setCollapsed = (collapsed) => {
      children.classList.toggle("json-hidden", collapsed);
      summary.classList.toggle("json-hidden", !collapsed);
      row.lastChild.classList.toggle("json-hidden", !collapsed);
      toggle.textContent = collapsed ? "▸" : "▾";
    };
    row.addEventListener("click", (event) => {
      if (
        event.target.classList.contains("json-bracket") ||
        event.target.classList.contains("json-summary") ||
        event.target.classList.contains("json-toggle")
      ) {
        setCollapsed(!children.classList.contains("json-hidden"));
      }
    });
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      setCollapsed(!children.classList.contains("json-hidden"));
    });
    setCollapsed(false);
    return wrapper;
  }

  function bracket(text) {
    const span = document.createElement("span");
    span.className = "json-bracket";
    span.textContent = text;
    span.addEventListener("mouseenter", () => {
      document
        .querySelectorAll(`[data-match-id="${span.dataset.matchId}"]`)
        .forEach((item) => item.classList.add("match"));
    });
    span.addEventListener("mouseleave", () => {
      document
        .querySelectorAll(`[data-match-id="${span.dataset.matchId}"]`)
        .forEach((item) => item.classList.remove("match"));
    });
    return span;
  }

  function jsonPrimitive(value, type) {
    const span = document.createElement("span");
    span.className = `json-${type}`;
    span.textContent =
      type === "string" ? JSON.stringify(value) : String(value);
    return span;
  }

  function jsonType(value) {
    if (value === null) return "null";
    if (Array.isArray(value)) return "array";
    return typeof value === "object" ? "object" : typeof value;
  }

  const viewerConversationId =
    new URLSearchParams(location.search).get("conversation") || "";

  function withViewerConversation(url) {
    if (!viewerConversationId) return url;
    const value = new URL(url, location.origin);
    value.searchParams.set("conversation", viewerConversationId);
    return value.pathname + value.search + value.hash;
  }

  function viewerHeaders(headers = {}) {
    return headers;
  }

  async function fetchJson(url) {
    return transport.json(url, undefined, "GET");
  }

  async function exportScene(format) {
    const exported = buildExportSvg();
    if (!exported) return;
    const fileBase = `${state.runId || "sr-agent"}-layout`;
    if (format === "svg") {
      downloadBlob(
        new Blob([exported.svgText], { type: "image/svg+xml;charset=utf-8" }),
        `${fileBase}.svg`,
      );
      return;
    }
    if (format === "png") {
      const canvas = await svgTextToCanvas(
        exported.svgText,
        exported.width,
        exported.height,
        3,
      );
      canvas.toBlob(
        (blob) => downloadBlob(blob, `${fileBase}.png`),
        "image/png",
      );
      return;
    }
    const pdfBlob = vectorPdfBlob();
    downloadBlob(pdfBlob, `${fileBase}.pdf`);
  }

  function buildExportSvg() {
    const viewport = svg.querySelector("g");
    if (!viewport) return null;
    const box = viewport.getBBox();
    const padding = 36;
    const width = Math.ceil(box.width + padding * 2);
    const height = Math.ceil(box.height + padding * 2);
    const clone = viewport.cloneNode(true);
    clone.removeAttribute("transform");
    clone.setAttribute(
      "transform",
      `translate(${padding - box.x} ${padding - box.y})`,
    );
    inlineExportStyles(clone);
    const exportSvg = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "svg",
    );
    exportSvg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    exportSvg.setAttribute("width", width);
    exportSvg.setAttribute("height", height);
    exportSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    exportSvg.appendChild(clone);
    return {
      width,
      height,
      svgText: `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(exportSvg)}`,
    };
  }

  function inlineExportStyles(root) {
    root.querySelectorAll("path.edge").forEach((path) => {
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", "#7f8b9d");
      path.setAttribute("stroke-width", "1.6");
      path.setAttribute(
        "opacity",
        path.classList.contains("weak") ? "0.45" : "0.68",
      );
      if (path.classList.contains("weak"))
        path.setAttribute("stroke-dasharray", "6 6");
      if (path.classList.contains("root"))
        path.setAttribute("stroke", "#5c6674");
    });
    root.querySelectorAll("circle.node").forEach((circle) => {
      circle.setAttribute("stroke", "#ffffff");
      circle.setAttribute("stroke-width", "2");
    });
    root.querySelectorAll("text").forEach((text) => {
      text.setAttribute(
        "fill",
        text.classList.contains("root-label") ? "#17202a" : "#334155",
      );
      text.setAttribute(
        "font-size",
        text.classList.contains("root-label") ? "12" : "11",
      );
      text.setAttribute("font-family", "Arial, sans-serif");
      text.setAttribute("text-anchor", "middle");
      if (text.classList.contains("root-label"))
        text.setAttribute("font-weight", "650");
    });
  }

  function svgTextToCanvas(svgText, width, height, scale) {
    return new Promise((resolve, reject) => {
      const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const image = new Image();
      image.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.ceil(width * scale));
        canvas.height = Math.max(1, Math.ceil(height * scale));
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        resolve(canvas);
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("Failed to render SVG export."));
      };
      image.src = url;
    });
  }

  function vectorPdfBlob() {
    const nodes = buildGraphNodes();
    const byId = new Map(nodes.map((node) => [node.node_id, node]));
    const drawable = nodes.filter((node) => state.positions.has(node.node_id));
    if (!drawable.length) return new Blob([], { type: "application/pdf" });
    const padding = 36;
    const radii = new Map(
      drawable.map((node) => [node.node_id, nodeRadius(node)]),
    );
    const xs = drawable.map((node) => state.positions.get(node.node_id).x);
    const ys = drawable.map((node) => state.positions.get(node.node_id).y);
    const minX = Math.min(...xs) - 80;
    const minY = Math.min(...ys) - 50;
    const maxX = Math.max(...xs) + 80;
    const maxY = Math.max(...ys) + 70;
    const pageWidth = maxX - minX + padding * 2;
    const pageHeight = maxY - minY + padding * 2;
    const tx = (x) => x - minX + padding;
    const ty = (y) => pageHeight - (y - minY + padding);
    const commands = [];

    commands.push("1 1 1 rg");
    commands.push(`0 0 ${fmt(pageWidth)} ${fmt(pageHeight)} re f`);

    for (const node of nodes) {
      if (node.virtual_root) continue;
      const target = state.positions.get(node.node_id);
      if (!target) continue;
      for (const parent of node.parents || []) {
        if (parent.relation === "context_merge" && !state.showWeakEdges)
          continue;
        if (!byId.has(parent.node_id)) continue;
        const source = state.positions.get(parent.node_id);
        if (!source) continue;
        const mid = (source.y + target.y) / 2;
        commands.push(
          parent.relation === "context_merge" ? "[6 6] 0 d" : "[] 0 d",
        );
        commands.push(
          parent.node_id.startsWith(ROOT_PREFIX)
            ? "0.36 0.40 0.45 RG"
            : "0.50 0.55 0.62 RG",
        );
        commands.push("1.6 w");
        commands.push(
          `${fmt(tx(source.x))} ${fmt(ty(source.y))} m ${fmt(tx(source.x))} ${fmt(ty(mid))} ${fmt(tx(target.x))} ${fmt(ty(mid))} ${fmt(tx(target.x))} ${fmt(ty(target.y))} c S`,
        );
      }
    }
    commands.push("[] 0 d");

    for (const node of drawable) {
      const point = state.positions.get(node.node_id);
      const radius = radii.get(node.node_id);
      const fill = node.virtual_root
        ? [0.15, 0.2, 0.22]
        : rgb01(colorFor(node));
      const stroke = [1, 1, 1];
      commands.push(`${fmt(fill[0])} ${fmt(fill[1])} ${fmt(fill[2])} rg`);
      commands.push(`${fmt(stroke[0])} ${fmt(stroke[1])} ${fmt(stroke[2])} RG`);
      commands.push("2 w");
      commands.push(circlePath(tx(point.x), ty(point.y), radius) + " B");
    }

    if (state.showLabels)
      for (const node of drawable) {
        const point = state.positions.get(node.node_id);
        const radius = radii.get(node.node_id);
        const label = node.virtual_root
          ? `run ${shortTreeId(node.run_id)}`
          : node.node_label ||
            `R${node.coord.R} C${node.coord.C} L${node.coord.L} K${node.coord.K}`;
        const size = node.virtual_root ? 12 : 11;
        const y = point.y + radius + 15;
        const textWidth = label.length * size * 0.45;
        commands.push("0.20 0.25 0.32 rg");
        commands.push(
          `BT /F1 ${size} Tf ${fmt(tx(point.x) - textWidth / 2)} ${fmt(ty(y))} Td (${escapePdfText(label)}) Tj ET`,
        );
      }

    const stream = commands.join("\n");
    const objects = [
      "<< /Type /Catalog /Pages 2 0 R >>",
      "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${fmt(pageWidth)} ${fmt(pageHeight)}] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>`,
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    ];
    let pdf = "%PDF-1.4\n";
    const offsets = [0];
    objects.forEach((object, index) => {
      offsets.push(pdf.length);
      pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
    });
    const xrefOffset = pdf.length;
    pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
    for (let index = 1; index < offsets.length; index++) {
      pdf += `${String(offsets[index]).padStart(10, "0")} 00000 n \n`;
    }
    pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
    const bytes = new Uint8Array(pdf.length);
    for (let i = 0; i < pdf.length; i++) bytes[i] = pdf.charCodeAt(i) & 0xff;
    return new Blob([bytes], { type: "application/pdf" });
  }

  function circlePath(cx, cy, r) {
    const k = 0.5522847498 * r;
    return [
      `${fmt(cx + r)} ${fmt(cy)} m`,
      `${fmt(cx + r)} ${fmt(cy + k)} ${fmt(cx + k)} ${fmt(cy + r)} ${fmt(cx)} ${fmt(cy + r)} c`,
      `${fmt(cx - k)} ${fmt(cy + r)} ${fmt(cx - r)} ${fmt(cy + k)} ${fmt(cx - r)} ${fmt(cy)} c`,
      `${fmt(cx - r)} ${fmt(cy - k)} ${fmt(cx - k)} ${fmt(cy - r)} ${fmt(cx)} ${fmt(cy - r)} c`,
      `${fmt(cx + k)} ${fmt(cy - r)} ${fmt(cx + r)} ${fmt(cy - k)} ${fmt(cx + r)} ${fmt(cy)} c`,
      "h",
    ].join(" ");
  }

  function rgb01(cssColor) {
    const probe = document.createElement("span");
    probe.style.color = cssColor;
    document.body.appendChild(probe);
    const match = getComputedStyle(probe).color.match(/\d+(\.\d+)?/g);
    probe.remove();
    if (!match || match.length < 3) return [0.45, 0.5, 0.56];
    return match.slice(0, 3).map((value) => Number(value) / 255);
  }

  function escapePdfText(text) {
    return String(text)
      .replace(/\\/g, "\\\\")
      .replace(/\(/g, "\\(")
      .replace(/\)/g, "\\)");
  }

  function fmt(value) {
    return Number(value)
      .toFixed(2)
      .replace(/\.?0+$/, "");
  }

  function downloadBlob(blob, filename) {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function svgEl(name) {
    return document.createElementNS("http://www.w3.org/2000/svg", name);
  }

  function fallbackLevel(node) {
    return node.virtual_root ? 0 : (node.coord.R - 1) * 1000 + node.coord.L;
  }

  function parentX(node, positions, old) {
    const xs = (node.parents || [])
      .map((parent) => positions.get(parent.node_id) || old.get(parent.node_id))
      .filter(Boolean)
      .map((point) => point.x);
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 640;
  }

  function averageParentX(layer, positions, old) {
    const xs = layer
      .map((node) => parentX(node, positions, old))
      .filter(Number.isFinite);
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 640;
  }

  function treeIdFor(record) {
    return record.run_id || state.runId || "current";
  }

  function rootId(treeId) {
    return `${ROOT_PREFIX}${treeId}`;
  }

  function shortTreeId(treeId) {
    return String(treeId || "current").slice(0, 8);
  }

  async function sendControl(action, message = "") {
    const response = await fetch("/api/control/command", {
      method: "POST",
      headers: viewerHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ action, message }),
    });
    if (!response.ok)
      throw new Error(
        (await response.json()).detail || "Control command failed",
      );
    const value = await response.json();
    agentPaused = value.paused;
    pauseAgentButton.textContent = agentPaused ? "Resume" : "Pause";
    agentStatusEl.textContent = value.stopped
      ? "agent: stopped"
      : agentPaused
        ? "agent: paused"
        : "agent: running";
  }

  async function pollControl() {
    try {
      const response = await fetch(
        `/api/control/events?after_seq=${controlSeq}`,
        { headers: viewerHeaders() },
      );
      const payload = await response.json();
      for (const event of payload.events || []) {
        controlSeq = Math.max(controlSeq, event.seq || 0);
        if (event.kind === "question") {
          const answer = window.prompt(
            event.payload.message || "Agent requests guidance",
            "",
          );
          if (answer !== null)
            await fetch(`/api/control/reply/${event.id}`, {
              method: "POST",
              headers: viewerHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ message: answer }),
            });
        }
      }
    } catch (error) {
      agentStatusEl.textContent = `control: ${error.message}`;
    }
  }

  sendGuidanceButton.addEventListener("click", async () => {
    const message = guidanceInput.value.trim();
    if (!message) return;
    await sendControl("message", message);
    guidanceInput.value = "";
  });
  guidanceInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") sendGuidanceButton.click();
  });
  pauseAgentButton.addEventListener("click", () =>
    sendControl(agentPaused ? "resume" : "pause"),
  );
  stopAgentButton.addEventListener("click", () => {
    if (window.confirm("Stop the connected agent?")) sendControl("stop");
  });
  if (!viewerParams.has("embed")) setInterval(pollControl, 1000);

  if (viewerParams.has("embed")) {
    document.body.classList.add("embedded");
    setRunHidden(true);
    setSideHidden(true);
  }

  syncR2ColorControls();
  setRunTab(state.runTab);
  applyPanelLayout();
  if (viewerParams.has("run")) {
    reportTree("正在加载本次搜索树…", "treeLoading");
    pollRequestedRun();
  } else {
    loadRuns().catch((error) => reportTree(error.message));
  }

  return () => {
    runtime.dispose();
    document.body.classList.remove("embedded");
  };
}
