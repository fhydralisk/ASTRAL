// Layout and controls ported from the original ASTRAL workbench.
export function TreeMarkup() {
  return (
    <>
      <header>
        <h1>{"ASTRAL Search Viewer"}</h1>
        <button id={"refresh"}>{"Refresh"}</button>
        <button id={"home"}>{"Home"}</button>
        <span id={"status"} className={"muted"}></span>
        <div className={"agent-control"} aria-label={"Live agent controls"}>
          <input
            id={"guidance"}
            placeholder={"Send guidance for the next turn…"}
          />
          <button id={"send-guidance"}>{"Send"}</button>
          <button id={"pause-agent"}>{"Pause"}</button>
          <button id={"stop-agent"} className={"danger"}>
            {"Stop"}
          </button>
          <span id={"agent-status"} className={"muted"}>
            {"agent: running"}
          </span>
        </div>
      </header>
      <main>
        <nav id={"run-panel"} className={"run-panel"} aria-label={"Runs"}>
          <div
            className={"run-tabs"}
            role={"tablist"}
            aria-label={"Left panel"}
          >
            <button
              id={"runs-tab"}
              className={"run-tab active"}
              type={"button"}
              data-run-tab={"runs"}
            >
              {"\n        Runs\n      "}
            </button>
            <button
              id={"controls-tab"}
              className={"run-tab"}
              type={"button"}
              data-run-tab={"controls"}
            >
              {"\n        Controls\n      "}
            </button>
          </div>
          <div id={"runs-panel"} className={"run-tab-panel"}>
            <div id={"run-panel-header"} className={"run-panel-header"}>
              <span className={"run-toggle"}></span>
              <span className={"run-panel-title"}>{"Runs"}</span>
            </div>
            <div id={"run-tree"} className={"run-tree"}></div>
          </div>
          <div id={"controls-panel"} className={"run-tab-panel hidden"}>
            <div className={"display-controls"}>
              <div className={"control-actions"}>
                <button id={"layout"} type={"button"}>
                  {"Auto Layout"}
                </button>
                <button id={"weak-edges"} type={"button"}>
                  {"Hide Weak Edges"}
                </button>
                <button id={"labels"} type={"button"}>
                  {"Hide Labels"}
                </button>
              </div>
              <label className={"control-bar"}>
                <span>{"Node"}</span>
                <input
                  id={"node-size"}
                  type={"range"}
                  min={"5"}
                  max={"18"}
                  step={"1"}
                  defaultValue={"9"}
                />
                <span id={"node-size-value"} className={"control-value"}>
                  {"9"}
                </span>
              </label>
              <label className={"control-bar"}>
                <span>{"Gap"}</span>
                <input
                  id={"level-gap"}
                  type={"range"}
                  min={"70"}
                  max={"220"}
                  step={"4"}
                  defaultValue={"118"}
                />
                <span id={"level-gap-value"} className={"control-value"}>
                  {"118"}
                </span>
              </label>
              <label className={"control-bar"}>
                <span>{"Horiz"}</span>
                <input
                  id={"horizontal-scale"}
                  type={"range"}
                  min={"50"}
                  max={"200"}
                  step={"5"}
                  defaultValue={"100"}
                />
                <span id={"horizontal-scale-value"} className={"control-value"}>
                  {"100"}
                </span>
              </label>
              <div className={"color-control"}>
                <label className={"color-control-row"}>
                  <span>{"Color"}</span>
                  <select id={"color-metric"} aria-label={"Color metric"}>
                    <option value={"r2"}>{"R2"}</option>
                    <option value={"mse"}>{"MSE"}</option>
                    <option value={"rmse"}>{"RMSE"}</option>
                    <option value={"smape"}>{"SMAPE"}</option>
                    <option value={"mape"}>{"MAPE"}</option>
                    <option value={"mae"}>{"MAE"}</option>
                    <option value={"spearman_r"}>{"Spearman r"}</option>
                    <option value={"pearson_r"}>{"Pearson r"}</option>
                  </select>
                </label>
                <div className={"color-control-row"}>
                  <span className={"range-pair"}>
                    <input
                      id={"r2-color-min"}
                      type={"range"}
                      min={"0"}
                      max={"1"}
                      step={"0.01"}
                      defaultValue={"0"}
                    />
                    <input
                      id={"r2-color-max"}
                      type={"range"}
                      min={"0"}
                      max={"1"}
                      step={"0.01"}
                      defaultValue={"1"}
                    />
                  </span>
                </div>
                <div className={"color-control-row color-input-row"}>
                  <input
                    id={"r2-color-min-value"}
                    className={"range-input"}
                    type={"number"}
                    step={"0.001"}
                    defaultValue={"0"}
                    aria-label={"R2 color minimum"}
                  />
                  <span>{"~"}</span>
                  <input
                    id={"r2-color-max-value"}
                    className={"range-input"}
                    type={"number"}
                    step={"0.001"}
                    defaultValue={"1"}
                    aria-label={"R2 color maximum"}
                  />
                </div>
              </div>
              <div className={"export-row"}>
                <select id={"export-format"} aria-label={"Export format"}>
                  <option value={"png"}>{"PNG"}</option>
                  <option value={"svg"}>{"SVG"}</option>
                  <option value={"pdf"}>{"PDF"}</option>
                </select>
                <button id={"export"} type={"button"}>
                  {"Export"}
                </button>
              </div>
            </div>
          </div>
        </nav>
        <div
          id={"run-resizer"}
          className={"run-resizer"}
          title={"Drag to resize runs panel"}
        >
          <div className={"run-resizer-tabs"}>
            <button
              className={"run-resizer-tab active"}
              type={"button"}
              data-run-tab={"runs"}
            >
              {"\n        Runs\n      "}
            </button>
            <button
              className={"run-resizer-tab"}
              type={"button"}
              data-run-tab={"controls"}
            >
              {"\n        Controls\n      "}
            </button>
          </div>
        </div>
        <section id={"graph-wrap"}>
          <div id={"legend"} className={"legend"}>
            <strong id={"legend-title"}>
              <span className={"legend-toggle"}></span>
              <span>{"Legend"}</span>
            </strong>
            <div className={"legend-body"}>
              <div className={"legend-row"}>
                <span className={"sample node-dot"}></span>
                <span>
                  {"Node: one sampled step (R, C, L, K) in the search tree."}
                </span>
              </div>
              <div className={"legend-row"}>
                <span className={"sample line"}></span>
                <span>{"Solid edge: primary conversation continuation."}</span>
              </div>
              <div className={"legend-row"}>
                <span className={"sample line weak"}></span>
                <span>
                  {"Dashed edge: shared tool outputs from a sibling sample."}
                </span>
              </div>
              <div className={"legend-row"}>
                <span></span>
                <span>
                  {
                    "Color: node score mapped from red (worse) to green (better) on the\n            selected metric."
                  }
                </span>
              </div>
            </div>
          </div>
          <svg
            id={"graph"}
            width={1200}
            height={760}
            role={"img"}
            aria-label={"Search graph"}
          ></svg>
        </section>
        <div
          id={"side-resizer"}
          className={"side-resizer"}
          title={"Drag to resize details panel"}
        ></div>
        <aside>
          <section className={"side-section"}>
            <strong id={"node-title"}>{"No node selected"}</strong>
            <div id={"node-subtitle"} className={"muted"}></div>
            <div id={"metrics"} className={"metric-grid"}></div>
          </section>
          <section className={"side-section"}>
            <strong>{"Formula"}</strong>
            <div id={"formula-latex"} className={"formula-box muted"}>
              {"\n        (no candidate formula)\n      "}
            </div>
            <button
              id={"formula-editor-toggle"}
              className={"formula-editor-toggle"}
              type={"button"}
            >
              {"\n        LaTeX editor\n      "}
            </button>
            <div id={"formula-editor"} className={"formula-editor hidden"}>
              <div className={"formula-editor-actions"}>
                <span id={"formula-editor-status"} className={"muted"}></span>
                <button id={"copy-latex"} type={"button"}>
                  {"Copy"}
                </button>
              </div>
              <textarea
                id={"latex-source"}
                spellCheck={"false"}
                aria-label={"LaTeX source"}
                defaultValue={""}
              ></textarea>
            </div>
            <pre id={"formula-code"} className={"formula-code"}></pre>
          </section>
          <section className={"side-section"}>
            <strong>{"Preview"}</strong>
            <div id={"preview"} className={"preview-chat muted"}></div>
          </section>
          <section className={"side-section"}>
            <strong>{"Tool Call"}</strong>
            <div id={"tool-call"} className={"tool-grid"}></div>
          </section>
          <section className={"side-section"}>
            <strong>{"Detail"}</strong>
            <div id={"detail"} className={"json-viewer muted"}></div>
          </section>
        </aside>
      </main>
    </>
  );
}
