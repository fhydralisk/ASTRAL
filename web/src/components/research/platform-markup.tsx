// Layout and controls ported from the original ASTRAL workbench.
export function PlatformMarkup() {
  return (
    <>
      <header>
        <div className={"brand"}>
          <div className={"logo"}>
            <img
              src={"/favicon.svg?v=astral-2"}
              alt={""}
              width={30}
              height={30}
            />
            {"ASTRAL\n    "}
          </div>
          <span id={"app-version"} className={"app-version"}></span>
        </div>
        <span className={"spacer"}></span>
        <span id={"connection"}>{"正在连接"}</span>
        <a
          id={"documentation-link"}
          className={"header-toggle header-documentation"}
          href={"https://yuzhthu.github.io/SRHarness/"}
          target={"_blank"}
          rel={"noopener"}
          aria-label={"打开文档"}
          title={"打开文档"}
        >
          <svg viewBox={"0 0 18 18"} aria-hidden={"true"}>
            <path
              d={
                "M3 3.5h4.2c1 0 1.8.8 1.8 1.8v9.2c0-1-.8-1.8-1.8-1.8H3zM15 3.5h-4.2c-1 0-1.8.8-1.8 1.8v9.2c0-1 .8-1.8 1.8-1.8H15z"
              }
            ></path>
          </svg>
        </a>
        <a
          id={"github-link"}
          className={"header-toggle header-github"}
          href={"https://github.com/yuzhTHU/ASTRAL"}
          target={"_blank"}
          rel={"noopener"}
          aria-label={"打开 GitHub 仓库"}
          title={"打开 GitHub 仓库"}
        >
          <svg viewBox={"0 0 24 24"} aria-hidden={"true"}>
            <path
              d={
                "M15 22v-4a4.8 4.8 0 0 0-1-3.5c3.3-.4 6.8-1.6 6.8-7A5.4 5.4 0 0 0 19.4 4 5 5 0 0 0 19.3.5S18.2.1 15 1.8a13.4 13.4 0 0 0-7 0C4.8.1 3.7.5 3.7.5A5 5 0 0 0 3.6 4a5.4 5.4 0 0 0-1.4 3.7c0 5.4 3.5 6.6 6.8 7A4.8 4.8 0 0 0 8 18v4M8 19c-3 .9-3-1.5-4-2"
              }
            ></path>
          </svg>
        </a>
        <button
          id={"theme-toggle"}
          className={"header-toggle"}
          type={"button"}
          aria-label={"切换到暗色主题"}
          title={"切换到暗色主题"}
        >
          {"\n    ☾"}
        </button>
        <button
          id={"language-toggle"}
          className={"header-toggle language-toggle"}
          type={"button"}
          aria-label={"Switch to English"}
          title={"Switch to English"}
        >
          {"\n    EN"}
        </button>
        <span id={"status"}>{"连接中"}</span>
      </header>
      <div
        id={"toast-stack"}
        className={"toast-stack"}
        aria-live={"polite"}
      ></div>
      <main>
        <aside className={"panel left"} id={"workspace"}>
          <div className={"bar"}>
            <span id={"workspace-title"}>{"工作区"}</span>
            <span className={"spacer"}></span>
            <div className={"workspace-actions"}>
              <button
                id={"new-folder"}
                className={"icon-button"}
                type={"button"}
                title={"新建文件夹"}
                aria-label={"新建文件夹"}
              >
                <svg viewBox={"0 0 16 16"} aria-hidden={"true"}>
                  <path
                    d={"M2.5 4.5h4l1.2 1.4h5.8v6.6h-11zM8 8v3M6.5 9.5h3"}
                  ></path>
                </svg>
              </button>
              <button
                id={"refresh"}
                className={"icon-button"}
                type={"button"}
                title={"刷新文件"}
                aria-label={"刷新文件"}
              >
                <svg viewBox={"0 0 16 16"} aria-hidden={"true"}>
                  <path d={"M12.7 6.2A5 5 0 1 0 13 9M12.7 3.5v2.8H9.9"}></path>
                </svg>
              </button>
            </div>
          </div>
          <form
            id={"workspace-name-editor"}
            className={"workspace-name-editor"}
            hidden={true}
          >
            <span
              id={"workspace-editor-icon"}
              className={"workspace-editor-icon workspace-item-icon"}
              aria-hidden={"true"}
            >
              <svg viewBox={"0 0 18 16"}>
                <path d={"M1.8 3.6h5l1.5 1.7h7.9v8.2H1.8z"}></path>
              </svg>
            </span>
            <input
              id={"workspace-name-input"}
              autoComplete={"off"}
              spellCheck={"false"}
            />
            <button
              id={"workspace-name-confirm"}
              type={"submit"}
              aria-label={"确认"}
            >
              {"\n        ✓"}
            </button>
            <button
              id={"workspace-name-cancel"}
              type={"button"}
              aria-label={"取消"}
            >
              {"\n        ×\n      "}
            </button>
          </form>
          <div id={"files"} role={"tree"}></div>
          <div className={"drop"} id={"drop"}>
            <div className={"drop-copy"}>
              <span id={"drop-title"}>
                {"拖放文件以上传 · 单文件 ≤ 256 MiB"}
              </span>
            </div>
            <button id={"upload"} type={"button"}>
              {"上传"}
            </button>
            <input
              type={"file"}
              id={"file-input"}
              multiple={true}
              hidden={true}
            />
          </div>
        </aside>
        <div
          id={"left-resizer"}
          className={"panel-resizer"}
          role={"separator"}
          aria-label={"调整工作区宽度"}
          aria-orientation={"vertical"}
          tabIndex={0}
        >
          <button
            className={"panel-toggle"}
            type={"button"}
            aria-label={"折叠工作区"}
          >
            {"\n      ‹\n    "}
          </button>
        </div>
        <section className={"panel center"}>
          <div className={"bar"}>
            <div className={"tabs"}>
              <button className={"active"} id={"prepare-tab"}>
                {"数据准备"}
              </button>
              <button id={"data-tab"}>{"任务配置"}</button>
              <button id={"timeline-tab"}>{"符号回归"}</button>
            </div>
            <span id={"tab-hint"} className={"tab-hint"} hidden={true}></span>
            <span className={"spacer"}></span>
            <button id={"context-tab"} type={"button"} hidden={true}>
              {"当前上下文"}
            </button>
          </div>
          <div id={"data-preparation"} className={"data-view"}>
            <div className={"data-intro"}>
              <div>
                <h2>{"数据准备"}</h2>
                <p>
                  {
                    "\n            上传原始数据或加载内置样例，让 Agent 帮你清洗并整理为标准数据集。\n          "
                  }
                </p>
              </div>
            </div>
            <div className={"data-layout"}>
              <section
                className={"data-card wide data-ingest-card"}
                id={"data-ingest"}
              >
                <div className={"ingest-heading"}>
                  <span className={"ingest-mark"} aria-hidden={"true"}>
                    {"↑"}
                  </span>
                  <div>
                    <h3 id={"data-upload-title"}>{"添加数据"}</h3>
                    <p>
                      <span id={"data-upload-help-prefix"}>
                        {"拖放数据文件，也可以从"}
                      </span>
                      <a
                        id={"create-demo"}
                        href={"#"}
                        title={"选择并生成内置的科学发现示例数据集"}
                      >
                        {"样例数据"}
                      </a>
                      <span id={"data-upload-help-suffix"}>{"开始。"}</span>
                    </p>
                  </div>
                </div>
                <div className={"ingest-drop"} id={"data-drop"}>
                  <span id={"data-drop-copy"}>{"将文件拖到此处"}</span>
                  <button id={"data-upload"} type={"button"}>
                    {"选择文件"}
                  </button>
                  <input
                    id={"data-file-input"}
                    type={"file"}
                    multiple={true}
                    hidden={true}
                  />
                </div>
              </section>
              <section className={"data-card wide data-agent-card"}>
                <div className={"data-agent-heading"}>
                  <div>
                    <div className={"data-agent-title-row"}>
                      <h3 id={"data-agent-title"}>{"数据准备 Agent"}</h3>
                      <a
                        id={"data-agent-safety"}
                        className={"data-agent-safety"}
                        href={
                          "https://yuzhthu.github.io/SRHarness/web-ui/#agent-safety"
                        }
                        target={"_blank"}
                        rel={"noopener"}
                      >
                        {"安全与数据权限说明"}
                      </a>
                    </div>
                    <div className={"data-agent-help-row"}>
                      <p id={"data-agent-help"}>
                        {
                          "\n                  直接用自然语言让 Agent\n                  帮你检查、清洗数据或构造衍生变量。整理好的数据保存在\n                  context.data/ 目录下：manifest.json\n                  记录变量、坐标轴及图/超图关系，<name>.npy\n                  保存各变量的数组取值\n                "
                        }
                      </p>
                      <span className={"data-agent-details"}>
                        {"（"}
                        <a
                          id={"context-data-guide-link"}
                          href={
                            "https://yuzhthu.github.io/SRHarness/context-data/"
                          }
                          target={"_blank"}
                          rel={"noopener"}
                        >
                          {"详情"}
                        </a>
                        {"）"}
                      </span>
                    </div>
                  </div>
                  <div className={"data-agent-heading-actions"}>
                    <span id={"data-agent-state"} className={"small muted"}>
                      {"准备就绪"}
                    </span>
                  </div>
                </div>
                <div
                  id={"data-agent-feed"}
                  className={"data-agent-feed"}
                  hidden={true}
                ></div>
                <div className={"data-agent-compose"}>
                  <textarea
                    id={"data-agent-input"}
                    rows={3}
                    placeholder={
                      "例如：提取人口数量作为因变量，并整理其它数值列作为自变量…"
                    }
                    defaultValue={""}
                  ></textarea>
                  <div className={"data-agent-compose-toolbar"}>
                    <button
                      id={"data-agent-settings-toggle"}
                      className={"composer-settings-button"}
                      type={"button"}
                      aria-expanded={"false"}
                    >
                      <svg viewBox={"0 0 16 16"} aria-hidden={"true"}>
                        <path
                          d={"M2.5 4h5m2 0h4M2.5 8h2m2 0h7M2.5 12h7m2 0h2"}
                        ></path>
                        <circle cx={"8.5"} cy={"4"} r={"1"}></circle>
                        <circle cx={"5.5"} cy={"8"} r={"1"}></circle>
                        <circle cx={"10.5"} cy={"12"} r={"1"}></circle>
                      </svg>
                      <span id={"data-agent-settings-toggle-label"}>
                        {"设置"}
                      </span>
                    </button>
                    <span className={"spacer"}></span>
                    <button
                      id={"data-agent-send"}
                      className={"data-agent-send"}
                      type={"button"}
                      aria-label={"交给 Agent"}
                      title={"交给 Agent"}
                    >
                      <svg viewBox={"0 0 18 18"} aria-hidden={"true"}>
                        <path d={"M9 14V4M5 8l4-4 4 4"}></path>
                      </svg>
                    </button>
                  </div>
                  <div
                    id={"data-agent-settings"}
                    className={"settings-panel data-agent-settings"}
                    hidden={true}
                  >
                    <div className={"settings-heading"}>
                      <div>
                        <b id={"data-agent-settings-title"}>{"数据准备设置"}</b>
                        <span id={"data-agent-settings-subtitle"}>
                          {"修改后下一轮 Agent 回复时生效"}
                        </span>
                      </div>
                      <button
                        id={"data-agent-settings-close"}
                        className={"quiet"}
                        type={"button"}
                        aria-label={"关闭"}
                      >
                        {"\n                  ×\n                "}
                      </button>
                    </div>
                    <nav className={"settings-tabs"}>
                      <button
                        className={"active"}
                        type={"button"}
                        data-data-settings-tab={"model"}
                      >
                        {"\n                  模型"}
                      </button>
                      <button
                        type={"button"}
                        data-data-settings-tab={"capabilities"}
                      >
                        {"\n                  能力\n                "}
                      </button>
                    </nav>
                    <div className={"settings-scroll"}>
                      <div
                        className={"settings-pane active"}
                        data-data-settings-pane={"model"}
                      >
                        <div className={"settings-form"}>
                          <label>
                            <span id={"data-provider-label"}>{"Provider"}</span>
                            <select
                              id={"data-provider"}
                              aria-label={"Provider"}
                            >
                              <option>{"openrouter"}</option>
                              <option>{"openai"}</option>
                              <option>{"deepseek"}</option>
                              <option>{"siliconflow"}</option>
                              <option>{"gemini"}</option>
                              <option>{"lmstudio"}</option>
                            </select>
                          </label>
                          <label>
                            <span id={"data-model-label"}>{"Model"}</span>
                            <input
                              id={"data-model"}
                              aria-label={"Model"}
                              placeholder={"Model"}
                            />
                          </label>
                          <label>
                            <span id={"data-proxy-label"}>{"代理"}</span>
                            <input
                              id={"data-proxy"}
                              type={"url"}
                              autoComplete={"off"}
                              spellCheck={"false"}
                              placeholder={"http://127.0.0.1:7890"}
                            />
                          </label>
                          <label className={"api-key-setting"}>
                            <span>
                              <b id={"data-api-key-label"}>{"API Key"}</b>
                              <small id={"data-api-key-env"}></small>
                            </span>
                            <span className={"api-key-control"}>
                              <input
                                id={"data-api-key"}
                                type={"password"}
                                autoComplete={"new-password"}
                                spellCheck={"false"}
                              />
                              <button
                                id={"data-api-key-visibility"}
                                type={"button"}
                              >
                                {
                                  "\n                          显示\n                        "
                                }
                              </button>
                            </span>
                            <small id={"data-api-key-status"}></small>
                          </label>
                          <label>
                            <span id={"data-tool-parser-label"}>
                              {"工具调用格式"}
                            </span>
                            <select id={"data-tool-parser"}>
                              <option value={"openai"}>
                                {"OpenAI Native"}
                              </option>
                              <option value={"text"}>{"Text"}</option>
                              <option value={"json"}>{"JSON"}</option>
                              <option value={"xml"}>{"XML"}</option>
                            </select>
                          </label>
                          <label>
                            <span id={"data-max-tokens-label"}>
                              {"最大输出 Token"}
                            </span>
                            <input
                              id={"data-max-tokens"}
                              type={"number"}
                              placeholder={"Auto"}
                              min={"1"}
                              max={"1000000"}
                            />
                          </label>
                        </div>
                      </div>
                      <div
                        className={"settings-pane"}
                        data-data-settings-pane={"capabilities"}
                        hidden={true}
                      >
                        <div className={"capability-columns"}>
                          <section>
                            <div className={"capability-heading"}>
                              <h4 id={"data-tools-settings-title"}>
                                {"可用工具"}
                              </h4>
                              <span id={"data-tools-count"}></span>
                            </div>
                            <div
                              id={"data-tool-options"}
                              className={"capability-options"}
                            ></div>
                          </section>
                          <section>
                            <div className={"capability-heading"}>
                              <h4 id={"data-skills-settings-title"}>
                                {"可用 Skill"}
                              </h4>
                              <span id={"data-skills-count"}></span>
                            </div>
                            <div
                              id={"data-skill-options"}
                              className={"capability-options"}
                            ></div>
                          </section>
                        </div>
                      </div>
                    </div>
                    <div className={"settings-actions"}>
                      <span id={"data-settings-hint"} className={"small muted"}>
                        {"修改后下一轮Agent回复时生效"}
                      </span>
                      <span className={"spacer"}></span>
                      <span
                        id={"data-model-test-status"}
                        className={"model-test-status"}
                        role={"status"}
                      ></span>
                      <button id={"data-model-test"} type={"button"}>
                        {"测试"}
                      </button>
                      <button id={"data-settings-cancel"} type={"button"}>
                        {"取消"}
                      </button>
                      <button
                        id={"data-settings-apply"}
                        className={"primary"}
                        type={"button"}
                      >
                        {"\n                  确认\n                "}
                      </button>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>
          <div
            id={"data-setup"}
            className={"data-view"}
            style={{ display: "none" }}
          >
            <div className={"data-intro"}>
              <div>
                <h2>{"任务配置"}</h2>
                <p>
                  {
                    "\n            指定因变量与自变量、补充各变量的物理或背景含义，并设置建模目标与公式评测方式。\n          "
                  }
                </p>
              </div>
            </div>
            <div className={"data-layout"}>
              <section
                className={"data-card wide variable-workbench"}
                id={"variable-config-card"}
              >
                <div className={"variable-card-heading"}>
                  <div>
                    <h3>{"配置变量描述"}</h3>
                    <p className={"variable-help"}>
                      {
                        "\n                点击左侧色标切换变量角色（因变量 / 自变量 /\n                暂不参与），点击描述直接编辑，拖动 ⠿ 可调整顺序\n              "
                      }
                    </p>
                  </div>
                  <div className={"variable-card-actions"}>
                    <button
                      id={"data-refresh"}
                      className={"data-refresh-button"}
                      type={"button"}
                    >
                      <svg viewBox={"0 0 16 16"} aria-hidden={"true"}>
                        <path
                          d={"M12.7 6.2A5 5 0 1 0 13 9M12.7 3.5v2.8H9.9"}
                        ></path>
                      </svg>
                      <span id={"data-refresh-label"}>{"刷新"}</span>
                    </button>
                  </div>
                </div>
                <div className={"variable-table-head"}>
                  <span></span>
                  <span>{"角色"}</span>
                  <span>{"变量"}</span>
                  <span>{"描述"}</span>
                </div>
                <div
                  id={"variable-role-table"}
                  className={"variable-role-table"}
                >
                  <div
                    id={"variable-role-body"}
                    className={"variable-role-body"}
                  ></div>
                </div>
              </section>
              <section
                className={"data-card wide task-problem-card"}
                id={"task-problem-card"}
              >
                <h3 id={"task-problem-title"}>{"配置问题描述"}</h3>
                <p id={"task-problem-help"}>
                  {
                    "\n            简要说明你的研究背景与建模目标（将自动加入初始提示词，上方已填写的变量说明无需重复）。\n          "
                  }
                </p>
                <textarea
                  id={"problem-description"}
                  rows={5}
                  placeholder={
                    "例如：研究人口数量与其它变量之间的关系，并寻找可解释的数学表达式。"
                  }
                  defaultValue={
                    "\nFind an interpretable formula explaining the selected target from the selected features."
                  }
                ></textarea>
              </section>
            </div>
          </div>
          <div
            id={"run-setup"}
            className={"data-view run-setup"}
            style={{ display: "none" }}
          >
            <div className={"data-intro"}>
              <div>
                <h2 id={"run-setup-title"}>{"准备探索"}</h2>
                <p id={"run-setup-help"}>
                  {
                    "\n            核对变量配置与初始提示词，点击右下角按钮启动符号回归搜索\n          "
                  }
                </p>
              </div>
            </div>
            <div className={"data-layout"}>
              <section
                className={
                  "data-card wide variable-workbench variable-workbench-preview"
                }
                id={"run-variable-preview"}
              >
                <h3>{"确认变量配置"}</h3>
                <p className={"variable-preview-help"}>
                  {
                    "\n            本次探索将使用以下变量配置（如需修改请返回“任务配置”选项卡）。\n          "
                  }
                </p>
                <div className={"variable-table-head"}>
                  <span></span>
                  <span>{"角色"}</span>
                  <span>{"变量"}</span>
                  <span>{"描述"}</span>
                </div>
                <div className={"variable-role-table"}>
                  <div
                    id={"run-variable-role-body"}
                    className={"variable-role-body"}
                  ></div>
                </div>
              </section>
            </div>
          </div>
          <div id={"feed"} style={{ display: "none" }}>
            <div className={"welcome"} id={"welcome"}>
              <div className={"orb"}>{"✳"}</div>
              <div className={"eyebrow"}>{"SYMBOLIC REGRESSION WORKSPACE"}</div>
              <h1>
                {"从数据出发，"}
                <br />
                {"寻找可解释的公式。"}
              </h1>
              <p className={"muted"}>
                {
                  "\n          上传数据并描述你的科学问题。Agent\n          的思考过程、工具调用与公式探索进展将在这里实时更新。\n        "
                }
              </p>
            </div>
          </div>
          <div id={"context"}></div>
          <button id={"follow"} hidden={true}>
            {"↓ 回到最新事件"}
          </button>
          <div id={"composer"} className={"composer data-mode"}>
            <input id={"target"} type={"hidden"} defaultValue={"y"} />
            <div id={"composer-purpose"} className={"composer-purpose"}>
              <b id={"composer-purpose-title"}>{"确认问题描述"}</b>
              <span id={"composer-purpose-help"}>
                {
                  "已根据任务配置自动生成，可在发送前直接编辑（点击右侧按钮可重新生成）。"
                }
              </span>
            </div>
            <textarea
              id={"prompt"}
              aria-label={"用户提示词"}
              placeholder={"等待根据任务配置生成用户提示词…"}
              defaultValue={""}
            ></textarea>
            <div className={"row"}>
              <span id={"pending"}></span>
              <span className={"spacer"}></span>
              <button
                id={"next-c"}
                className={"advance-button"}
                type={"button"}
                hidden={true}
              >
                {"\n          下一个 C"}
              </button>
              <button
                id={"next-r"}
                className={"advance-button"}
                type={"button"}
                hidden={true}
              >
                {"\n          下一个 R"}
              </button>
              <button
                id={"initial-prompt-toggle"}
                className={"composer-settings-button initial-prompt-toggle"}
                type={"button"}
                aria-expanded={"false"}
              >
                <svg viewBox={"0 0 16 16"} aria-hidden={"true"}>
                  <path
                    d={"M3 2.5h7l3 3v8H3zM10 2.5v3h3M5.5 8h5M5.5 10.5h5"}
                  ></path>
                </svg>
                <span id={"initial-prompt-toggle-label"}>{"系统提示词"}</span>
              </button>
              <button
                id={"settings-toggle"}
                className={"composer-settings-button"}
                type={"button"}
                aria-expanded={"false"}
              >
                <svg viewBox={"0 0 16 16"} aria-hidden={"true"}>
                  <path
                    d={"M2.5 4h5m2 0h4M2.5 8h2m2 0h7M2.5 12h7m2 0h2"}
                  ></path>
                  <circle cx={"8.5"} cy={"4"} r={"1"}></circle>
                  <circle cx={"5.5"} cy={"8"} r={"1"}></circle>
                  <circle cx={"10.5"} cy={"12"} r={"1"}></circle>
                </svg>
                <span id={"settings-toggle-label"}>{"设置"}</span>
              </button>
              <button id={"send"} className={"primary"} disabled={true}>
                {"开始探索 ↗"}
              </button>
            </div>
            <div
              id={"initial-prompt-panel"}
              className={"settings-panel initial-prompt-panel"}
              hidden={true}
            >
              <div className={"settings-heading"}>
                <div>
                  <b id={"initial-prompt-title"}>{"系统提示词"}</b>
                </div>
                <button
                  id={"initial-prompt-close"}
                  className={"quiet"}
                  type={"button"}
                  aria-label={"关闭"}
                >
                  {"\n            ×\n          "}
                </button>
              </div>
              <div className={"initial-prompt-body"}>
                <div className={"initial-prompt-note"}>
                  <b id={"system-prompt-confirm-title"}>{"确认系统提示词"}</b>
                  <span id={"system-prompt-confirm-help"}>
                    {"定义 Agent 的工作规范与搜索策略，可在发送前直接编辑。"}
                  </span>
                </div>
                <textarea
                  id={"system-prompt"}
                  className={"prompt-editor"}
                  aria-label={"System Prompt"}
                  defaultValue={""}
                ></textarea>
              </div>
            </div>
            <div
              id={"settings-panel"}
              className={"settings-panel"}
              hidden={true}
            >
              <div className={"settings-heading"}>
                <div>
                  <b id={"settings-title"}>{"运行设置"}</b>
                  <span id={"settings-subtitle"}>
                    {"确认后从下一轮开始生效"}
                  </span>
                </div>
                <button
                  id={"settings-close"}
                  className={"quiet"}
                  type={"button"}
                  aria-label={"关闭"}
                >
                  {"\n            ×\n          "}
                </button>
              </div>
              <nav className={"settings-tabs"} aria-label={"设置分类"}>
                <button
                  id={"settings-tab-model"}
                  className={"active"}
                  type={"button"}
                  data-settings-tab={"model"}
                >
                  {"\n            模型"}
                </button>
                <button
                  id={"settings-tab-search"}
                  type={"button"}
                  data-settings-tab={"search"}
                >
                  {"\n            搜索"}
                </button>
                <button
                  id={"settings-tab-capabilities"}
                  type={"button"}
                  data-settings-tab={"capabilities"}
                >
                  {"\n            能力\n          "}
                </button>
              </nav>
              <div className={"settings-scroll"}>
                <div
                  id={"settings-pane-model"}
                  className={"settings-pane active"}
                  data-settings-pane={"model"}
                >
                  <div className={"settings-form"}>
                    <label>
                      <span>{"Provider"}</span>
                      <select id={"provider"}>
                        <option>{"openrouter"}</option>
                        <option>{"openai"}</option>
                        <option>{"deepseek"}</option>
                        <option>{"siliconflow"}</option>
                        <option>{"gemini"}</option>
                        <option>{"lmstudio"}</option>
                      </select>
                    </label>
                    <label>
                      <span>{"Model"}</span>
                      <input
                        id={"model"}
                        defaultValue={"qwen/qwen3.5-flash-02-23"}
                      />
                    </label>
                    <label className={"api-key-setting"}>
                      <span>
                        <b id={"api-key-label"}>{"API Key"}</b>
                        <small id={"api-key-env"}></small>
                      </span>
                      <span className={"api-key-control"}>
                        <input
                          id={"api-key"}
                          type={"password"}
                          autoComplete={"new-password"}
                          spellCheck={"false"}
                        />
                        <button id={"api-key-visibility"} type={"button"}>
                          {"\n                    显示\n                  "}
                        </button>
                      </span>
                      <small id={"api-key-status"}></small>
                    </label>
                    <label>
                      <span id={"strong-provider-label"}>
                        {"强模型 Provider"}
                      </span>
                      <select id={"strong-provider"}>
                        <option value={""}>{"跟随基础模型"}</option>
                        <option>{"openrouter"}</option>
                        <option>{"openai"}</option>
                        <option>{"deepseek"}</option>
                        <option>{"siliconflow"}</option>
                        <option>{"gemini"}</option>
                        <option>{"lmstudio"}</option>
                      </select>
                    </label>
                    <label>
                      <span id={"strong-model-label"}>{"强模型"}</span>
                      <input
                        id={"strong-model"}
                        placeholder={"留空表示不启用"}
                      />
                    </label>
                    <label>
                      <span id={"tool-parser-label"}>{"工具调用格式"}</span>
                      <select id={"tool-parser"}>
                        <option value={"openai"}>{"OpenAI Native"}</option>
                        <option value={"text"}>{"Text"}</option>
                        <option value={"json"}>{"JSON"}</option>
                        <option value={"xml"}>{"XML"}</option>
                      </select>
                    </label>
                    <label>
                      <span id={"max-tokens-label"}>{"最大输出 Token"}</span>
                      <input
                        id={"max-tokens"}
                        type={"number"}
                        placeholder={"Auto"}
                        min={"1"}
                        max={"1000000"}
                      />
                    </label>
                  </div>
                  <label className={"switch-row"}>
                    <span>
                      <b id={"auto-routing-label"}>{"自动模型路由"}</b>
                      <small id={"auto-routing-help"}>
                        {
                          "根据任务复杂度与搜索进展，在基础模型与强模型之间自动切换"
                        }
                      </small>
                    </span>
                    <input id={"auto-routing"} type={"checkbox"} />
                  </label>
                </div>
                <div
                  id={"settings-pane-search"}
                  className={"settings-pane"}
                  data-settings-pane={"search"}
                  hidden={true}
                >
                  <div className={"settings-form compact"}>
                    <label>
                      <span>{"R · 重启次数"}</span>
                      <input
                        id={"R"}
                        type={"number"}
                        min={"1"}
                        max={"1000"}
                        defaultValue={"1"}
                      />
                    </label>
                    <label>
                      <span>{"C · 独立分支"}</span>
                      <input
                        id={"C"}
                        type={"number"}
                        min={"1"}
                        max={"1000"}
                        defaultValue={"1"}
                      />
                    </label>
                    <label>
                      <span>{"L · 对话深度"}</span>
                      <input
                        id={"L"}
                        type={"number"}
                        min={"1"}
                        max={"1000"}
                        defaultValue={"50"}
                      />
                    </label>
                    <label>
                      <span>{"K · 每轮采样"}</span>
                      <input
                        id={"K"}
                        type={"number"}
                        min={"1"}
                        max={"1000"}
                        defaultValue={"1"}
                      />
                    </label>
                    <label>
                      <span id={"restart-top-k-label"}>{"重启保留候选数"}</span>
                      <input
                        id={"restart-top-k"}
                        type={"number"}
                        min={"1"}
                        max={"1000"}
                        defaultValue={"1"}
                      />
                    </label>
                    <label>
                      <span id={"max-workers-label"}>{"工具并行进程"}</span>
                      <input
                        id={"max-workers"}
                        type={"number"}
                        min={"0"}
                        max={"1000"}
                        defaultValue={"0"}
                      />
                    </label>
                  </div>
                  <div className={"switch-list"}>
                    <label className={"switch-row"}>
                      <span>
                        <b id={"initial-diagnostics-label"}>{"强制初始诊断"}</b>
                        <small id={"initial-diagnostics-help"}>
                          {
                            "每条新分支第 1 步自动运行基础统计、相关性分析并加载符号发现\n                    Skill"
                          }
                        </small>
                      </span>
                      <input id={"initial-diagnostics"} type={"checkbox"} />
                    </label>
                  </div>
                </div>
                <div
                  id={"settings-pane-capabilities"}
                  className={"settings-pane"}
                  data-settings-pane={"capabilities"}
                  hidden={true}
                >
                  <div className={"capability-columns"}>
                    <section>
                      <div className={"capability-heading"}>
                        <h4 id={"tools-settings-title"}>{"可用工具"}</h4>
                        <span id={"tools-count"}></span>
                      </div>
                      <div
                        id={"tool-options"}
                        className={"capability-options"}
                      ></div>
                    </section>
                    <section>
                      <div className={"capability-heading"}>
                        <h4 id={"skills-settings-title"}>{"可用 Skill"}</h4>
                        <span id={"skills-count"}></span>
                      </div>
                      <div
                        id={"skill-options"}
                        className={"capability-options"}
                      ></div>
                    </section>
                  </div>
                </div>
              </div>
              <div className={"settings-actions"}>
                <span id={"settings-hint"} className={"small muted"}>
                  {"运行中将在下一次对话前生效"}
                </span>
                <span className={"spacer"}></span>
                <button id={"settings-cancel"} type={"button"}>
                  {"取消"}
                </button>
                <button id={"apply"} className={"primary"} disabled={true}>
                  {"确认"}
                </button>
              </div>
            </div>
          </div>
        </section>
        <div
          id={"right-resizer"}
          className={"panel-resizer"}
          role={"separator"}
          aria-label={"调整搜索结果宽度"}
          aria-orientation={"vertical"}
          tabIndex={0}
        >
          <button
            className={"panel-toggle"}
            type={"button"}
            aria-label={"折叠搜索结果"}
          >
            {"\n      ›\n    "}
          </button>
        </div>
        <aside className={"panel right"} id={"insights-panel"}>
          <div
            id={"search-insights"}
            className={"insights-view search-insights"}
          >
            <div className={"bar"}>
              <span id={"tree-title"}>{"搜索树"}</span>
              <button id={"tree-latest"} title={"跟随最新节点"}>
                {"最新"}
              </button>
              <button id={"tree-fit"} title={"显示整棵搜索树"}>
                {"总览"}
              </button>
              <button id={"tree-retry"} title={"重新连接搜索树"}>
                {"↻"}
              </button>
              <span className={"spacer"}></span>
              <a
                id={"full-tree"}
                href={"/viewer"}
                target={"_blank"}
                rel={"noopener"}
              >
                {"完整查看器 ↗"}
              </a>
            </div>
            <div className={"tree-wrap"}>
              <p id={"tree-status"} className={"muted small"}>
                {"任务开始后显示搜索树"}
              </p>
              <iframe
                id={"tree"}
                title={"Agent 搜索树"}
                src={"about:blank"}
              ></iframe>
            </div>
            <div className={"bar candidate-bar"}>
              <span id={"candidate-title"}>{"候选公式"}</span>
              <div
                className={"candidate-mode"}
                role={"group"}
                aria-label={"候选公式范围"}
              >
                <button
                  id={"candidate-topk"}
                  className={"active"}
                  type={"button"}
                >
                  {"Topk"}
                </button>
                <button id={"candidate-pareto"} type={"button"}>
                  {"Pareto Front"}
                </button>
              </div>
              <span className={"spacer"}></span>
              <span className={"eyebrow"} id={"count"}>
                {"0 RECORDS"}
              </span>
            </div>
            <div id={"topk"}>
              <p className={"muted small"}>
                {
                  "\n          搜索过程中评估得到的候选公式与各项指标将显示在此处。\n        "
                }
              </p>
            </div>
          </div>
          <div
            id={"data-insights"}
            className={"insights-view data-insights"}
            hidden={true}
          >
            <div className={"bar relationship-preview-bar"}>
              <span id={"relationship-preview-title"}>{"数据预览"}</span>
              <select id={"relationship-preview-mode"} aria-label={"预览模式"}>
                <option value={"table"}>{"表格"}</option>
                <option value={"structure"}>{"结构"}</option>
                <option value={"scatter"}>{"散点图"}</option>
                <option value={"distribution"}>{"分布"}</option>
                <option value={"heatmap"}>{"热图"}</option>
              </select>
              <span className={"spacer"}></span>
            </div>
            <div
              id={"data-table-preview"}
              className={"data-insights-scroll data-table-preview"}
              hidden={true}
            >
              <div className={"data-preview-toolbar"}>
                <label className={"data-preview-picker"}>
                  <span id={"data-preview-group-label"}>{"预览变量"}</span>
                  <select
                    id={"data-preview-group"}
                    aria-label={"预览变量"}
                  ></select>
                </label>
                <div className={"data-number-format"}>
                  <span id={"data-number-format-label"}>{"数值格式"}</span>
                  <select id={"data-number-format-mode"}>
                    <option value={"decimal"}>{"小数"}</option>
                    <option value={"scientific"}>{"科学计数法"}</option>
                  </select>
                  <label className={"data-number-digits"}>
                    <input
                      id={"data-number-format-digits"}
                      type={"number"}
                      min={"0"}
                      max={"12"}
                      step={"1"}
                      defaultValue={"3"}
                    />
                    <span id={"data-number-digits-label"}>{"位"}</span>
                  </label>
                </div>
              </div>
              <div id={"data-table"} className={"data-table-wrap"}></div>
              <div id={"tensor-preview"} className={"tensor-preview"}></div>
            </div>
            <div className={"data-insights-scroll relationship-preview-scroll"}>
              <div
                id={"plot-variable-palette"}
                className={"plot-variable-palette"}
              >
                <span className={"plot-palette-empty"}>{"暂无可用变量。"}</span>
              </div>
              <div className={"plot-fields"}>
                <div className={"plot-slot"} data-channel={"x"}>
                  <b>{"X"}</b>
                  <span className={"plot-slot-value"}></span>
                </div>
                <div className={"plot-slot"} data-channel={"y"}>
                  <b>{"Y"}</b>
                  <span className={"plot-slot-value"}></span>
                </div>
                <div className={"plot-slot"} data-channel={"hue"}>
                  <b>{"HUE"}</b>
                  <span className={"plot-slot-value"}></span>
                </div>
                <div className={"plot-slot"} data-channel={"size"}>
                  <b>{"SIZE"}</b>
                  <span className={"plot-slot-value"}></span>
                </div>
              </div>
              <div
                id={"distribution-bin-control"}
                className={"distribution-bin-control"}
                hidden={true}
              >
                <label>
                  <span id={"distribution-bin-label"}>{"直方条数量"}</span>
                  <input
                    id={"distribution-bin-count"}
                    type={"number"}
                    min={"2"}
                    max={"100"}
                    defaultValue={"20"}
                  />
                </label>
              </div>
              <div
                id={"heatmap-z-control"}
                className={"heatmap-z-control"}
                hidden={true}
              ></div>
              <div id={"plot-stage"} className={"plot-stage"}>
                <div
                  id={"plot-broadcast-info"}
                  className={"plot-broadcast-info"}
                  hidden={true}
                ></div>
                <svg
                  id={"scatter"}
                  role={"img"}
                  aria-label={"变量关系散点图"}
                ></svg>
                <div id={"plot-empty"} className={"plot-empty"}>
                  {"将数值变量拖入 X 和 Y"}
                </div>
              </div>
            </div>
          </div>
        </aside>
      </main>
      <dialog id={"preview"}>
        <div className={"row"}>
          <b id={"preview-title"}></b>
          <span className={"spacer"}></span>
          <button id={"close-preview"}>{"关闭"}</button>
        </div>
        <div id={"preview-meta"} className={"preview-meta"}></div>
        <pre id={"preview-text"}></pre>
      </dialog>
      <dialog id={"demo-picker"} className={"demo-picker"}>
        <div className={"demo-picker-header"}>
          <div>
            <h3 id={"demo-picker-title"}>{"选择样例数据"}</h3>
            <p id={"demo-picker-help"}>
              {"生成后将作为当前 context.data 加载。"}
            </p>
          </div>
          <button
            id={"demo-picker-close"}
            className={"demo-picker-close"}
            type={"button"}
            aria-label={"关闭"}
          >
            {"\n      ×\n    "}
          </button>
        </div>
        <div
          id={"demo-picker-status"}
          role={"status"}
          aria-live={"polite"}
        ></div>
        <div className={"demo-options"}></div>
      </dialog>
    </>
  );
}
