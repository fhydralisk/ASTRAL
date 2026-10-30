
const $=id=>document.getElementById(id);$('apply').disabled=false;let session=null,seq=0,dataSeq=0,evaluatorSeq=0,treeRun=null,initialized=false,filesSignature='',contextSignature='',workspaceExpansionInitialized=false,workspaceEditItem=null;const expandedDirectories=new Set(),shownSessionErrors=new Set();
let inferredActivity={phase:'idle',since:Date.now()/1000},lastStatusAt=0,lastEventsAt=0,lastCoord={},latestContext=null,selectedContextKey=null;const toolCards=new Map(),dataToolCards=new Map(),assistantCards=new Map(),dataAssistantCards=new Map(),evaluatorAssistantCards=new Map(),assistantStreamStates=new Map(),seenUsageSteps=new Set(),seenDataUsageTurns=new Set(),contextHistory=new Map();let observedUsage={token:{},price:{}},observedDataUsage={token:{},price:{}};
let dataPreview=null,dataPreviewGroups=[],selectedDataPreviewGroup='',dataGroupPreview=null,dataGroupPreviewToken=0,dataNumberFormatMode=localStorage.getItem('sr-harness-data-number-format')||'decimal',dataNumberFormatDigits=Math.max(0,Math.min(12,Number(localStorage.getItem('sr-harness-data-number-digits')??3)||0)),dataChannels={x:'',y:'',hue:'',size:''},distributionChannels={x:'',y:''},distributionBins=Math.max(2,Math.min(100,Number(localStorage.getItem('sr-harness-distribution-bins')??20)||20)),plotMode=localStorage.getItem('sr-harness-plot-mode')||'table',heatmapChannels={row:[],column:[],color:'',z:''},plotPreview=null,plotPreviewToken=0,heatmapPreview=null,heatmapPreviewToken=0,heatmapZIndex=0,plotDragAccepted=false,promptRefreshTimer=null,promptRefreshToken=0,renderedDataRevision=0,useCommittedContext=false,contextHydrationPromise=null,serverSessionGeneration=0;
const DEFAULT_PROBLEM_DESCRIPTION='Find an interpretable formula explaining the selected target from the selected features.';
let promptDefaults={problem_description:DEFAULT_PROBLEM_DESCRIPTION,system_prompt:'',user_prompt:''},promptEdited={user:false,system:false},initialPromptSent=false;
let variableOrder=[],variableRoles={},variableDescriptions={},capabilities=null,dataCapabilities=null,credentialRequestToken=0,dataCredentialRequestToken=0;
let selectionSaveTimer=0,selectionSaveVersion=0,selectionSavedVersion=0,selectionSaveInFlight=false;
let startRequestPending=false;
let candidateMode=localStorage.getItem('sr-harness-candidate-mode')||'topk',candidateRecords=[],candidateFormulaMode=['raw','pretty','latex'].includes(localStorage.getItem('sr-harness-candidate-formula-mode'))?localStorage.getItem('sr-harness-candidate-formula-mode'):'raw',candidateFormulaNumberMode=['decimal','scientific'].includes(localStorage.getItem('sr-harness-candidate-number-mode'))?localStorage.getItem('sr-harness-candidate-number-mode'):'decimal',candidateFormulaDigits=Math.max(0,Math.min(12,Number.parseInt(localStorage.getItem('sr-harness-candidate-number-digits')??'6',10)||0));
const SUPPORTED_LOCALES=['zh-CN','en'],DEFAULT_LOCALE='en',LOCALE_ALIASES={zh:'zh-CN',en:'en'};
const storedLocale=localStorage.getItem('sr-harness-language'),normalizedLocale=LOCALE_ALIASES[storedLocale]||storedLocale;
const legacyMarkdownMode=localStorage.getItem('sr-harness-markdown')==='true';
let currentLocale=SUPPORTED_LOCALES.includes(normalizedLocale)?normalizedLocale:'zh-CN',uiTheme=localStorage.getItem('sr-harness-theme')==='dark'?'dark':'light',markdownModes=Object.fromEntries(['search','data','evaluator'].map(scope=>[scope,(localStorage.getItem('sr-harness-markdown-'+scope)??String(legacyMarkdownMode))==='true']));
const DOCUMENTATION_ROOT=new URL($('documentation-link').href).href;
function documentationUrl(path=''){return new URL((currentLocale==='en'?'en/':'')+String(path).replace(/^\/+/,''),DOCUMENTATION_ROOT).href}
function updateDocumentationLinks(){const targets=[['documentation-link',''],['data-agent-safety','web-ui/#agent-safety'],['context-data-guide-link','context-data/'],['evaluator-guide','evaluator/'],['evaluator-agent-safety','web-ui/#agent-safety']];for(const [id,path] of targets){const link=$(id);if(link)link.href=documentationUrl(path)}}
const MESSAGE_CATALOGS={
  'zh-CN':{
    runSetupSummary:'核对变量配置与初始提示词，点击右下角按钮启动符号回归搜索',variablePreviewTitle:'确认变量配置',variablePreviewSummary:'本次探索将使用以下变量配置（如需修改请返回“任务配置”选项卡）。',composerPurposeTitle:'确认用户提示词',composerPurposeHelp:'已根据任务配置自动生成，可在发送前直接编辑。',systemPromptConfirmTitle:'确认系统提示词',systemPromptConfirmHelp:'定义 Agent 的工作规范与搜索策略，可在发送前直接编辑。',regeneratePrompt:'重新生成',
    appTitle:'ASTRAL · 交互工作台',workspace:'工作区',dropTitle:'拖放文件以上传 · 单文件 ≤ 256 MiB',chooseFile:'上传',parentFolder:'上一级',refreshFiles:'刷新文件',newFolder:'新建文件夹',newFolderPrompt:'输入新文件夹名称',fileActions:'更多操作',rename:'重命名',renamePrompt:'输入新名称',deleteItem:'删除',deleteConfirm:'确定删除“{{name}}”吗？目录中的内容也会被删除。',invalidName:'名称不能为空，也不能包含路径分隔符。',prepare:'数据准备',data:'任务配置',timeline:'符号回归',context:'当前上下文',tree:'搜索树',latest:'最新',overview:'总览',fullViewer:'完整查看器 ↗',candidates:'候选公式',records:'RECORDS',emptyCandidates:'尚无候选公式。',candidateHint:'搜索过程中评估得到的候选公式与各项指标将显示在此处。',pause:'暂停',resume:'继续',stop:'停止',themeDark:'切换到暗色主题',themeLight:'切换到明亮主题',languageSwitch:'Switch to English',languageSwitchShort:'EN',idle:'准备就绪',starting:'正在初始化',running:'探索中',completed:'已完成',interrupted:'已停止',failed:'运行失败',connection:'正在连接',connected:'已连接到后端',connectionLost:'连接中断 · 自动重试',connectionDelayed:'服务已连接 · 事件同步延迟',noFormula:'(无公式)',allMetrics:'所有指标与来源',paretoEmpty:'尚无同时包含误差和复杂度的候选公式。',
    prepareIntro:'上传原始数据或加载内置样例，让 Agent 帮你清洗并整理为标准数据集。',runSetupTitle:'准备探索',runSetupHelp:'核对变量配置与研究问题，按需查看或编辑自动生成的初始提示词。',runUpdateHelp:'调整变量角色与描述；保存后，符号回归 Agent 将在下一轮使用更新后的配置。',timelineEvents:'时间线',taskSetup:'任务配置',applyNextRound:'应用到下一轮',selectionApplyHint:'变量角色将在下一轮搜索开始前生效。',selectionApplied:'变量角色与描述已更新，将在下一轮搜索开始前生效。',uploadDataTitle:'添加数据',uploadDataHelpPrefix:'拖放数据文件，也可以从',sampleData:'样例数据',uploadDataHelpSuffix:'开始。',dataDropCopy:'拖入文件以上传',dataIntro:'指定因变量与自变量、补充各变量的物理或背景含义，并设置建模目标与公式评测方式。',csvData:'数据预览',refreshData:'刷新',refreshingData:'正在刷新…',uploadCsv:'上传数据',dataSummary:'数据中暂无可预览的变量。',contextDataEmpty:'数据中暂无可预览的变量。',noPlotVariables:'暂无可用变量。',dataPreviewGroup:'预览变量',numberFormat:'数值格式',decimalFormat:'小数',scientificFormat:'科学计数法',decimalPlaces:'位',dataPreviewLoading:'正在加载预览…',dataPreviewUnavailable:'该数据组暂不支持直接预览。',dataGroupAxis:'轴 {{axis}} · {{count}} 个一维变量',dataGroupTensor:'{{variable}} · {{dimensions}} 维变量',dataGroupSummary:'{{label}} · shape {{shape}} · {{dtype}}',tensorAxes:'结构轴',tensorSamples:'样例值',tensorRange:'取值范围',contextDataRequired:'请先上传样例或让数据准备 Agent 将数据整理写入 context.data/。',previewRows:'{{rows}} 行预览 · {{columns}} 列 · {{numeric}} 个数值列',variables:'变量描述与角色',variableConfigTitle:'配置变量描述',variableHelp:'点击左侧色标切换变量角色（因变量 / 自变量 / 暂不参与），点击描述直接编辑，拖动 ⠿ 可调整顺序',variablePreviewHelp:'本次探索将使用以下变量配置（如需修改请返回“任务配置”选项卡）。',taskProblemTitle:'配置问题描述',taskProblemHelp:'简要说明你的研究背景与建模目标（将自动加入初始提示词，上方已填写的变量说明无需重复）。',taskProblemPlaceholder:'例如：研究人口数量与其它变量之间的关系，并寻找可解释的数学表达式。',researchQuestion:'研究问题',researchQuestionHelp:'用于生成发送给 Agent 的初始 Prompt',runtimeGuidance:'补充研究方向',runtimeGuidanceHelp:'这段文字会作为新消息插入下一轮对话',initialPromptTitle:'系统提示词',initialPromptHelp:'根据问题描述和变量配置自动生成，可在发送前直接编辑',dataInsightsTitle:'数据预览',role:'角色',variable:'变量',axisKind:'轴',description:'描述',relationship:'关系预览',relationshipHelp:'将变量胶囊拖入槽位；双击槽位可清空',dropVariable:'拖入变量',problem:'问题描述与初始 Prompt',startRun:'开始运行 ↗',settings:'运行设置',apply:'确认',settingsHint:'运行中将在下一次请求前生效',settingsSubtitle:'确认后从下一轮开始生效',settingsToggle:'设置',settingsClose:'关闭',settingsCancel:'取消',modelSettings:'模型',searchSettings:'搜索',capabilitySettings:'能力',strongProvider:'强模型 Provider',strongModel:'强模型',strongModelPlaceholder:'留空表示不启用',followBaseModel:'跟随基础模型',toolParser:'工具调用格式',maxTokens:'输出上限（留空自动）',apiKey:'API Key',apiKeyShow:'显示',apiKeyHide:'隐藏',apiKeyConfigured:'已配置；输入新值可替换',apiKeyMissing:'尚未配置',apiKeyPlaceholder:'输入 {{env}}，确认后写入 .env',apiKeySaved:'{{env}} 已与 .env 同步',autoRouting:'自动模型路由',autoRoutingHelp:'根据任务复杂度与搜索进展，在基础模型与强模型之间自动切换',restartTopK:'重启保留候选数',maxWorkers:'工具并行进程',validationFraction:'验证集比例',splitBy:'验证集划分',splitSeed:'划分随机种子',rankingMetric:'候选排序指标',largerBetter:'排序指标越大越好',largerBetterHelp:'开启表示该指标数值越大越优（如 R²）；关闭表示越小越优（如误差 RMSE）',initialDiagnostics:'强制初始诊断',initialDiagnosticsHelp:'每条新分支第 1 步自动运行基础统计、相关性分析并加载符号发现 Skill',nextC:'下一个 C',nextR:'下一个 R',nextCQueued:'已请求切换到下一个 C',nextRQueued:'已请求切换到下一个 R',availableTools:'可用工具',availableSkills:'可用 Skill',selectedCount:'已启用 {{selected}} / {{total}}',settingsQueued:'配置已排队，将从下一轮开始生效',settingsSaved:'配置已保存',promptPlaceholder:'向下一轮对话补充研究方向…',initialUserPromptPlaceholder:'等待根据任务配置生成用户提示词…',
    feature:'自变量',target:'因变量',unused:'暂不参与',currentRole:'当前角色：{{role}}；点击切换',targetOnly:'每次只能指定一个因变量',dragReorder:'拖动以调整行顺序',dragRelationship:'拖入关系预览槽位',descriptionPlaceholder:'添加变量含义、单位或备注…',descriptionOf:'{{column}} 的描述',variableEmpty:'刷新数据后显示变量。',
    sentContext:'当前发送上下文',contextStats:'{{count}} 条消息 · {{characters}} 字符',systemPrompt:'系统提示词',developerPrompt:'开发者提示词',userPrompt:'用户提示词',agent:'Agent',toolResult:'工具结果',rawMessage:'查看原始消息',
    awaitingReply:'等待人工回复',stopping:'正在停止（等待当前操作返回）',paused:'已暂停',pauseRequested:'暂停已请求',startExploring:'开始探索 ↗',replyAgent:'回复 Agent ↗',insertRound:'插入下一轮 ↗',modelQueued:'配置更新已排队',promptsQueued:'{{count}} 条 Prompt 等待注入',
    expand:'展开',collapse:'收起',toolRunning:'执行中',toolFailed:'执行失败',toolReturned:'已返回',toolNoText:'工具未返回文本结果',errorInfo:'错误信息',result:'返回结果',seconds:'{{count}} 秒',minutesSeconds:'{{minutes}} 分 {{seconds}} 秒',modelWaiting:'等待模型响应',modelStreaming:'正在接收模型输出',modelRetrying:'请求暂时失败，正在重试',modelProgress:'{{status}} · {{duration}}',
    requestTimeout:'请求超时，正在重连',closeNotice:'关闭提示',promptDefault:'默认生成',promptEditing:'编辑中',promptEdited:'已被编辑',promptRestoreOnBlur:'失焦后恢复默认',numericRoleOnly:'{{column}} 不是数值型变量，仅可设为“暂不参与”。',movePlotVariable:'拖动到其他槽位以移动或交换',plotAdjusted:'拖动变量可继续调整关系预览。',runAlreadyStarted:'当前服务已经开始运行',startingRun:'正在启动…',runStartedHint:'任务已开始，请查看执行时间线',
    emptyList:'空列表',emptyObject:'空对象',viewParameters:'查看参数',noParameters:'无参数',callParameters:'调用参数',rawJson:'查看原始 JSON',usageSummary:'本轮 {{stepTokens}} · {{stepMoney}}　累计 {{totalTokens}} · {{totalMoney}}',contextLinkTitle:'查看这一轮发送给模型的上下文',contextLoadFailed:'无法读取该轮上下文：{{message}}',contextNotFound:'尚未找到 R{{R}} · C{{C}} · L{{L}} 的上下文',dataContextNotFound:'尚未找到数据准备 Agent 第 {{count}} 轮的上下文',evaluatorContextNotFound:'尚未找到评测器构建 Agent 第 {{count}} 轮的上下文',contextWaiting:'已发送上下文，等待模型响应',fullRunResult:'完整运行结果',controlPaused:'已暂停',controlResumed:'已继续',controlStopped:'已请求停止',controlMessage:'已插入下一轮',controlNextC:'切换到下一个 C',controlNextR:'切换到下一个 R',controlAction:'控制操作',lastSync:'最近状态同步：{{time}}',neverConnected:'尚未连接',contextEmpty:'尚未发送上下文。',message:'消息',
    previewTruncated:'预览内容已截断',previewShape:'形状 {{value}}',previewDtype:'类型 {{value}}',previewElements:'{{value}} 个元素',downloadFile:'下载 {{name}}',downloadSize:'下载 ({{size}})',downloadZip:'下载 ZIP',downloadZipSize:'下载 ZIP ({{size}})',calculatingSize:'正在计算目录大小',sizeUnavailable:'大小未知',readOnlyItem:'只读挂载',lockedItem:'用户锁定',lockItem:'锁定',unlockItem:'解锁',dataAgentSafety:'安全与数据权限说明',workspaceEmpty:'文件夹为空',uploading:'正在上传 {{name}}…',treeLoading:'正在加载本次搜索树…',connectionError:'连接异常 · 自动重试',eventBufferGap:'部分早期事件已移出缓冲区，可在搜索记录中查看已完成轮次。',eventRenderFailed:'事件 {{seq}} 显示失败：{{message}}',eventSync:'事件同步：{{message}}',treeReconnecting:'正在重新连接搜索树…',resizePanel:'拖动可调整宽度',expandPanel:'展开{{name}}',collapsePanel:'折叠{{name}}',searchResults:'搜索结果',inputRequired:'请输入任务描述或指导信息',demoGenerating:'生成数据中…',demoCreated:'样例 context.data 已生成并加载。',uploadFailed:'上传失败',
    dataAgentTitle:'数据准备 Agent',dataAgentHelp:'直接用自然语言让 Agent 帮你检查、清洗数据或构造衍生变量。整理好的数据保存在 context.data/ 目录下',dataAgentSettingsTitle:'数据准备设置',dataAgentSettingsSubtitle:'修改后下一轮 Agent 回复时生效',dataAgentSettingsHint:'修改后下一轮Agent回复时生效',dataAgentProvider:'Provider',dataAgentModel:'Model',dataAgentProxy:'代理',dataAgentProxyPlaceholder:'例如 http://127.0.0.1:7890；留空表示不使用',dataAgentModelTest:'测试',dataAgentModelTesting:'正在测试模型回复与工具调用…',dataAgentModelTestPassed:'模型可访问，工具调用测试通过。',dataAgentModelTestPartial:'模型可访问，但工具调用测试未通过。',dataAgentModelTestUnavailable:'无法访问指定模型。',dataSettingsSaved:'数据准备配置已保存',dataCommitRequired:'提交结构化数据所必需的工具',dataAgentReady:'准备就绪',dataAgentRunning:'正在处理',dataAgentStop:'停止数据准备 Agent',dataAgentStopping:'正在停止',dataAgentStopped:'已停止',dataAgentPlaceholder:'例如：提取人口数量作为因变量，并整理其它数值列作为自变量…',dataAgentSend:'交给 Agent ↗',dataAgentPauseFirst:'修改运行中的数据前，请先暂停符号回归。',dataAgentCommitted:'结构化数据已经更新。',dataAgentTurn:'第 {{count}} 轮',eventUser:'用户',
    eventTool:'工具',eventToolError:'工具错误',eventAgent:'Agent',eventContext:'上下文',eventQuestion:'Agent 提问',eventReply:'用户回复',eventControl:'用户控制',eventRun:'运行',eventModelUpdated:'运行配置已更新',eventModelError:'配置应用失败',eventWorkspace:'工作区',welcomeEyebrow:'天文发现工作区',welcomeTitle:'从数据出发，\n寻找可解释的公式。',welcomeBody:'上传数据并描述你的科学问题。Agent 的思考过程、工具调用与公式探索进展将在这里实时更新。',timelinePendingEyebrow:'执行时间线',timelinePendingTitle:'正在准备执行…',timelinePendingBody:'搜索任务已启动，正在等待第一条运行事件返回…'
  },
  en:{
    runSetupSummary:'Review the variable configuration and research question, then start the symbolic-regression search.',variablePreviewTitle:'Review Variable Configuration',variablePreviewSummary:'The configuration below will be used for this run. Open the Task Setup tab to make changes.',composerPurposeTitle:'Review User Prompt',composerPurposeHelp:'Generated from the task configuration; edit it before sending.',systemPromptConfirmTitle:'Review System Prompt',systemPromptConfirmHelp:'Built-in default prompt; edit it before sending.',regeneratePrompt:'Regenerate',
    appTitle:'ASTRAL · Interactive',workspace:'Workspace',dropTitle:'Drop files to upload · max 256 MiB each',chooseFile:'Upload',parentFolder:'Parent folder',refreshFiles:'Refresh files',newFolder:'New folder',newFolderPrompt:'Enter a name for the new folder',fileActions:'More actions',rename:'Rename',renamePrompt:'Enter a new name',deleteItem:'Delete',deleteConfirm:'Delete “{{name}}”? The contents of a directory will also be deleted.',invalidName:'Names cannot be empty or contain path separators.',prepare:'Data Preparation',data:'Task Setup',timeline:'Symbolic Regression',context:'Current Context',tree:'Search Tree',latest:'Latest',overview:'Overview',fullViewer:'Full viewer ↗',candidates:'Candidate Formulas',records:'RECORDS',emptyCandidates:'No candidate formulas yet.',candidateHint:'Evaluated candidate formulas and metrics will appear here.',pause:'Pause',resume:'Resume',stop:'Stop',themeDark:'Switch to dark theme',themeLight:'Switch to light theme',languageSwitch:'切换到中文',languageSwitchShort:'中',idle:'Ready',starting:'Starting',running:'Exploring',completed:'Completed',interrupted:'Stopped',failed:'Failed',connection:'Connecting',connected:'Connected to backend',connectionLost:'Disconnected · retrying',connectionDelayed:'Connected · event stream delayed',noFormula:'(no formula)',allMetrics:'All metrics and provenance',paretoEmpty:'No candidate has both an error metric and complexity.',
    prepareIntro:'Upload or generate data, then ask the Agent to turn raw sources into reusable arrays.',runSetupTitle:'Prepare the Run',runSetupHelp:'Review the variable configuration, enter the research question below, and optionally inspect or edit the generated initial prompts.',runUpdateHelp:'Adjust variable roles and descriptions; after confirmation, the symbolic-regression Agent will use the new data configuration from the next round.',timelineEvents:'Timeline',taskSetup:'Task Setup',applyNextRound:'Apply Next Round',selectionApplyHint:'Variable roles take effect before the next search round.',selectionApplied:'Variable roles and descriptions will take effect before the next search round.',uploadDataTitle:'Add Data',uploadDataHelpPrefix:'Drop data files, or begin with the ',sampleData:'sample dataset',uploadDataHelpSuffix:'.',dataDropCopy:'Drop files to upload',dataIntro:'Configure the variables, roles, descriptions, and research question used for symbolic regression.',csvData:'Data Preview',refreshData:'Refresh',refreshingData:'Refreshing…',uploadCsv:'Upload Data',dataSummary:'No variables are available to preview.',contextDataEmpty:'No variables are available to preview.',noPlotVariables:'No variables available.',dataPreviewGroup:'Preview variable',numberFormat:'Number format',decimalFormat:'Decimal',scientificFormat:'Scientific',decimalPlaces:'places',dataPreviewLoading:'Loading preview…',dataPreviewUnavailable:'This data group cannot be previewed.',dataGroupAxis:'Axis {{axis}} · {{count}} one-dimensional variables',dataGroupTensor:'{{variable}} · {{dimensions}}D variable',dataGroupSummary:'{{label}} · shape {{shape}} · {{dtype}}',tensorAxes:'Axes',tensorSamples:'Sample values',tensorRange:'Value range',contextDataRequired:'Ask the preparation Agent to write structured variables to context.data first.',previewRows:'{{rows}} rows · {{columns}} columns · {{numeric}} numeric',variables:'Variables & Roles',variableConfigTitle:'Configure Variable Descriptions',variableHelp:"Click the color bar to change a variable's role, click its description to edit it, or drag the handle to reorder variables.",variablePreviewHelp:'This configuration will be used for the run. To change it, open the Task Setup tab.',taskProblemTitle:'Configure Problem Description',taskProblemHelp:'Describe the research objective for the initial prompt. Do not repeat information already included in variable descriptions.',taskProblemPlaceholder:'For example: Study the relationship between population and the other variables and find an interpretable mathematical expression.',researchQuestion:'Research Question',researchQuestionHelp:'Used to generate the initial prompts sent to the Agent',runtimeGuidance:'Additional Direction',runtimeGuidanceHelp:'This text is inserted as a new message in the next conversation round',initialPromptTitle:'System Prompt',initialPromptHelp:'Generated from the problem description and variable configuration; edit it directly before sending',dataInsightsTitle:'Data Preview',role:'Role',variable:'Variable',axisKind:'Axis',description:'Description',relationship:'Relationship Preview',relationshipHelp:'Drag variables into slots; double-click a slot to clear it',dropVariable:'Drop variable',problem:'Problem Description & Initial Prompts',startRun:'Start Run ↗',settings:'Run Settings',apply:'Confirm',settingsHint:'Changes take effect before the next request',settingsSubtitle:'Takes effect from the next round after confirmation',settingsToggle:'Settings',settingsClose:'Close',settingsCancel:'Cancel',modelSettings:'Model',searchSettings:'Search',capabilitySettings:'Capabilities',strongProvider:'Strong-model Provider',strongModel:'Strong Model',strongModelPlaceholder:'Leave blank to disable',followBaseModel:'Follow base model',toolParser:'Tool-call Format',maxTokens:'Output Token Limit (blank: auto)',apiKey:'API Key',apiKeyShow:'Show',apiKeyHide:'Hide',apiKeyConfigured:'Configured; enter a new value to replace it',apiKeyMissing:'Not configured',apiKeyPlaceholder:'Enter {{env}}; saved to .env on confirmation',apiKeySaved:'{{env}} is synced with .env',autoRouting:'Automatic Model Routing',autoRoutingHelp:'Choose between the base and strong model based on task difficulty',restartTopK:'Restart Seed Candidates',maxWorkers:'Tool Worker Processes',validationFraction:'Validation Fraction',splitBy:'Validation Split',splitSeed:'Split Random Seed',rankingMetric:'Candidate Ranking Metric',largerBetter:'Larger Ranking Metric Is Better',largerBetterHelp:'When disabled, smaller metric values rank first',initialDiagnostics:'Force Initial Diagnostics',initialDiagnosticsHelp:'Run statistics, relationship analysis, and the symbolic-laws skill at each new branch',nextC:'Next C',nextR:'Next R',nextCQueued:'Advancing to the next C',nextRQueued:'Advancing to the next R',availableTools:'Available Tools',availableSkills:'Available Skills',selectedCount:'{{selected}} / {{total}} enabled',settingsQueued:'Settings queued for the next round',settingsSaved:'Settings saved',promptPlaceholder:'Guide the next conversation round…',initialUserPromptPlaceholder:'Waiting to generate the user prompt from task settings…',
    feature:'Feature',target:'Target',unused:'Excluded',currentRole:'Current role: {{role}}; click to change',targetOnly:'Only one target can be selected',dragReorder:'Drag to reorder',dragRelationship:'Drag into a relationship slot',descriptionPlaceholder:'Add meaning, unit, or notes…',descriptionOf:'Description of {{column}}',variableEmpty:'Refresh data to show variables.',
    sentContext:'Sent Context',contextStats:{one:'{{count}} message · {{characters}} chars',other:'{{count}} messages · {{characters}} chars'},systemPrompt:'System Prompt',developerPrompt:'Developer Prompt',userPrompt:'User Prompt',agent:'Agent',toolResult:'Tool Result',rawMessage:'View raw message',
    awaitingReply:'Awaiting reply',stopping:'Stopping after current operation',paused:'Paused',pauseRequested:'Pause requested',startExploring:'Start Exploring ↗',replyAgent:'Reply to Agent ↗',insertRound:'Insert Next Round ↗',modelQueued:'Settings update queued',promptsQueued:{one:'{{count}} prompt queued',other:'{{count}} prompts queued'},
    expand:'Expand',collapse:'Collapse',toolRunning:'Running',toolFailed:'Failed',toolReturned:'Returned',toolNoText:'Tool returned no text result',errorInfo:'Error',result:'Result',seconds:{one:'{{count}} second',other:'{{count}} seconds'},minutesSeconds:'{{minutes}} min {{seconds}} sec',modelWaiting:'Waiting for model response',modelStreaming:'Receiving model output',modelRetrying:'Request interrupted; retrying',modelProgress:'{{status}} · {{duration}}',
    requestTimeout:'Request timed out; reconnecting',closeNotice:'Dismiss notice',promptDefault:'Generated',promptEditing:'Editing',promptEdited:'Edited',promptRestoreOnBlur:'Restore default after focus leaves',numericRoleOnly:'{{column}} is not numeric and can only be excluded from the model.',movePlotVariable:'Drag to another slot to move or swap',plotAdjusted:'Drag variables to further adjust the relationship preview.',runAlreadyStarted:'The service has already started a run',startingRun:'Starting…',runStartedHint:'Run started. View progress in Timeline.',
    emptyList:'Empty list',emptyObject:'Empty object',viewParameters:'View parameters',noParameters:'No parameters',callParameters:'Call parameters',rawJson:'View raw JSON',usageSummary:'Step {{stepTokens}} · {{stepMoney}}　Total {{totalTokens}} · {{totalMoney}}',contextLinkTitle:'View the context sent to the model for this round',contextLoadFailed:'Could not load this round’s context: {{message}}',contextNotFound:'No context found for R{{R}} · C{{C}} · L{{L}}',dataContextNotFound:'No context found for Data Preparation Agent turn {{count}}',evaluatorContextNotFound:'No context found for Evaluator Construction Agent turn {{count}}',contextWaiting:'Context sent; awaiting model response',fullRunResult:'Full run result',controlPaused:'Paused',controlResumed:'Resumed',controlStopped:'Stop requested',controlMessage:'Inserted into next round',controlNextC:'Advance to next C',controlNextR:'Advance to next R',controlAction:'Control action',lastSync:'Last status sync: {{time}}',neverConnected:'Not connected yet',contextEmpty:'No context has been sent.',message:'Message',
    previewTruncated:'Preview truncated',previewShape:'Shape {{value}}',previewDtype:'Dtype {{value}}',previewElements:'{{value}} elements',downloadFile:'Download {{name}}',downloadSize:'Download ({{size}})',downloadZip:'Download ZIP',downloadZipSize:'Download ZIP ({{size}})',calculatingSize:'Calculating directory size',sizeUnavailable:'size unavailable',readOnlyItem:'Read-only mount',lockedItem:'User-locked',lockItem:'Lock',unlockItem:'Unlock',dataAgentSafety:'Can this Agent harm my data or system?',workspaceEmpty:'Folder is empty',uploading:'Uploading {{name}}…',treeLoading:'Loading this run’s search tree…',connectionError:'Connection error · retrying',eventBufferGap:'Some earlier events have left the buffer. Completed rounds remain available in search records.',eventRenderFailed:'Could not render event {{seq}}: {{message}}',eventSync:'Event sync: {{message}}',treeReconnecting:'Reconnecting search tree…',resizePanel:'Drag to resize',expandPanel:'Expand {{name}}',collapsePanel:'Collapse {{name}}',searchResults:'search results',inputRequired:'Enter a task description or guidance',demoGenerating:'Generating sample data…',demoCreated:'The sample context.data was created and loaded.',uploadFailed:'Upload failed',
    dataAgentTitle:'Data Preparation Agent',dataAgentHelp:'Use natural language to guide the Agent in inspecting, cleaning, or extending the data. Results are stored in context.data/: manifest.json records variables and axes; network or hypergraph data also declares num_nodes and relation variables. <name>.npy stores values.',dataAgentSettingsTitle:'Data Preparation Settings',dataAgentSettingsSubtitle:'Changes take effect on the Agent’s next reply',dataAgentSettingsHint:'Changes take effect on the Agent’s next reply',dataAgentProvider:'Provider',dataAgentModel:'Model',dataAgentProxy:'Proxy',dataAgentProxyPlaceholder:'For example, http://127.0.0.1:7890; leave blank to disable',dataAgentModelTest:'Test',dataAgentModelTesting:'Testing model response and tool calling…',dataAgentModelTestPassed:'The model is accessible and the tool-call test passed.',dataAgentModelTestPartial:'The model is accessible, but the tool-call test did not pass.',dataAgentModelTestUnavailable:'The specified model could not be reached.',dataSettingsSaved:'Data-preparation settings saved',dataCommitRequired:'Required to publish structured data',dataAgentReady:'Ready',dataAgentRunning:'Working',dataAgentStop:'Stop Data Preparation Agent',dataAgentStopping:'Stopping',dataAgentStopped:'Stopped',dataAgentPlaceholder:'For example: use population as the target and prepare the other numeric columns as features…',dataAgentSend:'Send to Agent ↗',dataAgentPauseFirst:'Pause symbolic regression before changing its data.',dataAgentCommitted:'Structured data was updated.',dataAgentTurn:'Turn {{count}}',eventUser:'User',
    eventTool:'Tool',eventToolError:'Tool Error',eventAgent:'Agent',eventContext:'Context',eventQuestion:'Agent Question',eventReply:'Human Reply',eventControl:'User Control',eventRun:'Run',eventModelUpdated:'Run Settings Updated',eventModelError:'Settings Error',eventWorkspace:'Workspace',welcomeEyebrow:'ASTRONOMY DISCOVERY WORKSPACE',welcomeTitle:'Start with data.\nFind an interpretable formula.',welcomeBody:'Upload data and describe your research problem. Agent output, model reasoning, and tool execution will update here.',timelinePendingEyebrow:'TIMELINE',timelinePendingTitle:'Preparing the run…',timelinePendingBody:'The task has been submitted. Its first event will appear here shortly.'
  }
};
Object.assign(MESSAGE_CATALOGS['zh-CN'],{uploadDataHelpPrefix:'上传本地数据文件，或直接加载',uploadDataHelpSuffix:'快速体验',dataAgentHelp:'直接用自然语言让 Agent 帮你检查、清洗数据或构造衍生变量，处理结果会自动保存到 context.data/ 目录',dataAgentDetails:'详情',apiKeyConfigured:'已配置，输入新值以替换',apiKeyGet:'获取 {{env}} ↗'});Object.assign(MESSAGE_CATALOGS.en,{uploadDataHelpPrefix:'Upload local data files, or load a ',uploadDataHelpSuffix:' to get started quickly',dataAgentHelp:'Ask the Agent in plain language to inspect, clean, or derive variables. Prepared arrays are saved to context.data/ automatically',dataAgentDetails:'Details',apiKeyConfigured:'Configured; enter a new value to replace it',apiKeyGet:'Get {{env}} ↗'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{restartCount:'R · 重启次数',branchCount:'C · 独立分支',conversationDepth:'L · 对话深度',samplesPerRound:'K · 每轮采样',pauseOnTruncation:'输出被截断时自动暂停',pauseOnTruncationHelp:'当模型回复达到最大输出长度时，保留已生成内容并在本轮结束后暂停'});Object.assign(MESSAGE_CATALOGS.en,{restartCount:'R · Restart Count',branchCount:'C · Independent Branches',conversationDepth:'L · Conversation Depth',samplesPerRound:'K · Samples per Round',pauseOnTruncation:'Pause when output is truncated',pauseOnTruncationHelp:'Keep partial text and pause after the current turn when a model response hits the token limit'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{stopReviewRounds:'无工具回复停机复核轮数',stopGuardMode:'允许提前停止的条件',stopGuardNone:'不限制（Agent 请求即停）',stopGuardTopk:'Top-k 中已有唯一最优公式',stopGuardMetricThreshold:'指定指标达到目标阈值',stopGuardBudget:'跑满当前分支步数 (L)',stopGuardMetric:'达标检查指标',stopGuardThreshold:'目标阈值',stopGuardSplit:'检查数据集',stopGuardLargerBetter:'该指标数值越大越优',stopGuardLargerBetterHelp:'仅用于“指定指标达到目标阈值”模式；开启时要求指标 ≥ 阈值，关闭时要求指标 ≤ 阈值'});Object.assign(MESSAGE_CATALOGS.en,{stopReviewRounds:'Stop-review rounds on text-only replies',stopGuardMode:'Early-stop condition',stopGuardNone:'No restriction (stop when requested)',stopGuardTopk:'Unique best formula in Top-k',stopGuardMetricThreshold:'Target metric reaches threshold',stopGuardBudget:'Finish all L steps in branch',stopGuardMetric:'Target metric',stopGuardThreshold:'Target threshold',stopGuardSplit:'Evaluation split',stopGuardLargerBetter:'Higher metric values are better',stopGuardLargerBetterHelp:'Used when checking a metric threshold; when off, requires the metric to be at or below the threshold'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{evaluatorTitle:'配置评测方案 (Evaluator)',evaluatorHelp:'选择内置评估器或编写自定义代码，控制数据切分、常数拟合与误差指标计算',evaluatorCustom:'Custom Evaluator',evaluatorSave:'保存方案',evaluatorTest:'测试',evaluatorSaved:'评测方案已保存。',evaluatorTesting:'正在使用当前数据测试…',evaluatorTestPassed:'测试通过',evaluatorAgentToggle:'需要特殊指标？让 Agent 帮你编写自定义 Evaluator',evaluatorAgentTitle:'评测器构建 Agent',evaluatorAgentNote:'用自然语言描述评测需求（如轨迹积分误差或物理约束），Agent 会自动编写并测试自定义 Evaluator。',evaluatorAgentPlaceholder:'例如：改成按轨迹 RMSE 评测，并用当前数据测试和修复代码…',evaluatorAgentSend:'交给 Agent',evaluatorAgentWorking:'Agent 正在构建并检验 Evaluator…',evaluatorNoTools:'未调用工具'});Object.assign(MESSAGE_CATALOGS.en,{evaluatorTitle:'Configure Evaluation Protocol',evaluatorHelp:'Choose a built-in evaluator or define a custom evaluator for data splitting, model fitting, and model evaluation.',evaluatorCustom:'Custom Evaluator',evaluatorSave:'Save Protocol',evaluatorTest:'Test',evaluatorSaved:'Evaluation protocol saved.',evaluatorTesting:'Testing against the current data…',evaluatorTestPassed:'Test passed',evaluatorAgentToggle:'Or describe what you need and let the Agent create an Evaluator',evaluatorAgentTitle:'Evaluator Construction Agent',evaluatorAgentNote:'The Agent can inspect relevant source and create and validate a custom Evaluator in the workspace.',evaluatorAgentPlaceholder:'For example: evaluate trajectory RMSE, then test and repair the implementation with the current data…',evaluatorAgentSend:'Send to Agent',evaluatorAgentWorking:'The Agent is constructing and testing the Evaluator…',evaluatorNoTools:'No tools called'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{composerEnterHint:'Shift/⌘ + Enter 换行；Enter 发送'});Object.assign(MESSAGE_CATALOGS.en,{composerEnterHint:'Shift/⌘ + Enter for newline; Enter to send'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{dataAgentPlaceholder:'例如：读取我上传的文件，清洗缺失值并整理为 ASTRAL 标准数据集格式…',dataNextHint:'数据准备就绪后，继续前往',dataNextAction:'任务配置',taskNextHint:'任务配置完成后，继续前往',taskNextAction:'符号回归'});Object.assign(MESSAGE_CATALOGS.en,{dataAgentPlaceholder:'For example: organize my uploaded files into a format accepted by ASTRAL',dataNextHint:'Once the data are ready, continue to the next step',dataNextAction:'Task Configuration',taskNextHint:'Once configuration is complete, continue to the next step',taskNextAction:'Symbolic Regression'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{markdownOutput:'Markdown',plainText:'纯文本',showMarkdown:'切换为 Markdown 和数学公式显示',showPlainText:'切换为纯文本显示'});Object.assign(MESSAGE_CATALOGS.en,{markdownOutput:'Markdown',plainText:'Plain text',showMarkdown:'Switch to rendered Markdown and mathematics',showPlainText:'Switch to plain text'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{candidateFormulaDisplay:'候选方程显示格式',candidateFormulaRaw:'原始',candidateFormulaPretty:'公式',candidateFormulaLatex:'LaTeX',candidateNumberFormat:'方程数值格式',candidateNumberDigits:'精度'});Object.assign(MESSAGE_CATALOGS.en,{candidateFormulaDisplay:'Candidate formula display',candidateFormulaRaw:'Raw',candidateFormulaPretty:'Formula',candidateFormulaLatex:'LaTeX',candidateNumberFormat:'Formula number format',candidateNumberDigits:'Precision'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{interactionStateChanged:'状态：{{previous}} → {{current}}',interactionIdle:'准备就绪',interactionRunning:'正在运行',interactionPausing:'等待本轮结束后暂停',interactionInterrupting:'正在中断当前操作',interactionPaused:'已暂停'});Object.assign(MESSAGE_CATALOGS.en,{interactionStateChanged:'State: {{previous}} → {{current}}',interactionIdle:'Ready',interactionRunning:'Running',interactionPausing:'Pausing after the current turn',interactionInterrupting:'Interrupting the current operation',interactionPaused:'Paused'});Object.assign(MESSAGE_CATALOGS['zh-CN'],{eventTopkUpdated:'候选公式已更新 · {{count}} 条'});Object.assign(MESSAGE_CATALOGS.en,{eventTopkUpdated:'Candidate formulas updated · {{count}}'});Object.assign(MESSAGE_CATALOGS['zh-CN'],{documentation:'打开文档',githubRepository:'打开 GitHub 仓库'});Object.assign(MESSAGE_CATALOGS.en,{documentation:'Open documentation',githubRepository:'Open GitHub repository'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{safeStopNotice:'已请求暂停，Agent 将在本轮结束后停下；再次点击可立即强制中断本轮',forceStopNotice:'用户强制中止',forceStop:'强制结束本轮'});Object.assign(MESSAGE_CATALOGS.en,{safeStopNotice:'Stop requested. The Agent will pause after this turn. Click again to force-end the turn.',forceStopNotice:'User force-stopped the turn',forceStop:'Force-end this turn'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{evaluatorAgentStop:'停止评测器构建 Agent',evaluatorAgentStopping:'正在停止评测器构建 Agent…',evaluatorAgentStopped:'评测器构建 Agent 已停止'});Object.assign(MESSAGE_CATALOGS.en,{evaluatorAgentStop:'Stop Evaluator Construction Agent',evaluatorAgentStopping:'Stopping Evaluator Construction Agent…',evaluatorAgentStopped:'Evaluator Construction Agent stopped'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{evaluatorGuide:'查看 Evaluator 接口文档',evaluatorArgs:'参数配置',evaluatorArgsTitle:'context.args.*',evaluatorValidationFraction:'留作验证集的样本比例（0 ~ 1 之间）。',evaluatorSplitRandomState:'随机切分数据集或处理并列值时使用的随机种子。',evaluatorSplitBy:'切分方式：random 为随机抽样；ood 为按指定变量排序后切分分布外验证集。',evaluatorSplitOodVariable:'使用 ood 外推切分时用于排序的变量名（split_by=ood 时必填）。',evaluatorRankingMetric:'对候选公式排序时依据的指标名称（如 mse、rmse、r2 或自定义指标）。',evaluatorLargerIsBetter:'勾选表示该指标越大越优（如 R²）；取消勾选表示越小越优（如误差 RMSE）。'});Object.assign(MESSAGE_CATALOGS.en,{evaluatorGuide:'View Evaluator interface guide',evaluatorArgs:'Parameters',evaluatorArgsTitle:'context.args.*',evaluatorValidationFraction:'Fraction of samples reserved for evaluation.',evaluatorSplitRandomState:'Seed used for random splitting and OOD tie handling.',evaluatorSplitBy:'Split strategy: random sampling, or OOD extrapolation ordered by a selected variable.',evaluatorSplitOodVariable:'Variable used to order an OOD split; required explicitly when split_by=ood.',evaluatorRankingMetric:'Field returned by evaluate that ranks candidate formulas.',evaluatorLargerIsBetter:'Whether larger values of the ranking metric are preferred.'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{dataAgentSafety:'安全与数据权限说明'});Object.assign(MESSAGE_CATALOGS.en,{dataAgentSafety:'Safety & data permissions'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{graphPreview:'有向图预览',hypergraphPreview:'有向超图预览',relationPreviewCount:'{{nodes}} 个节点 · {{relations}} 条关系',relationPreviewTruncated:'图规模较大，仅显示部分节点和关系。',hyperedgeRoles:'小张角为目标 · 大张角为来源'});Object.assign(MESSAGE_CATALOGS.en,{graphPreview:'Directed graph preview',hypergraphPreview:'Directed hypergraph preview',relationPreviewCount:'{{nodes}} nodes · {{relations}} relations',relationPreviewTruncated:'The relation is large; only a subset of nodes and relations is shown.',hyperedgeRoles:'narrow target · wide source'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{plotLoading:'正在按轴对齐数据…',plotNoFinitePoints:'广播后的数据中没有可绘制的有限值。',scalarAxes:'标量',plotShape:'{{shape}}',plotShapeTruncated:'{{shape}} · 仅显示部分数据点'});Object.assign(MESSAGE_CATALOGS.en,{plotLoading:'Aligning data by axis…',plotNoFinitePoints:'The broadcast data contains no finite points to plot.',scalarAxes:'scalar',plotShape:'{{shape}}',plotShapeTruncated:'{{shape}} · showing a subset of points'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{relationshipPreviewMode:'预览模式',tablePreview:'表格',structurePreview:'结构',scatterPlot:'散点图',distributionPlot:'分布',heatmapPlot:'热图',distributionBins:'直方条数量',distributionDropX:'将变量拖入 X 以查看分布',structureSelectRelation:'请选择图或超图变量。',plotVariableAxes:'轴：{{axes}}；拖动以预览关系',heatmapDropVariables:'将轴拖入 ROW 与 COL，或将轴与同轴的一维变量分别放入两侧',heatmapShape:'{{shape}}',heatmapShapeTruncated:'{{shape}} · 仅显示部分单元格',value:'值'});Object.assign(MESSAGE_CATALOGS.en,{relationshipPreviewMode:'Preview mode',tablePreview:'Table',structurePreview:'Structure',scatterPlot:'Scatter plot',distributionPlot:'Distribution',heatmapPlot:'Heatmap',distributionBins:'Histogram bins',distributionDropX:'Drop a variable into X to view its distribution',structureSelectRelation:'Select a graph or hypergraph variable.',plotVariableAxes:'Axes: {{axes}}; drag to preview relationships',heatmapDropVariables:'Drop axes into ROW and COL, or place an axis on one side and aligned 1D variables on the other',heatmapShape:'{{shape}}',heatmapShapeTruncated:'{{shape}} · showing a subset of cells',value:'value'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{treeIdle:'任务开始后显示搜索树',treeSynced:'{{count}} 个节点 · 已同步',treeAwaitingFirstNode:'等待第一轮完成后生成搜索节点',treeSyncFailed:'搜索树同步失败：{{message}} · 自动重试',treeLatestTitle:'跟随最新节点',treeFitTitle:'显示整棵搜索树',treeRetryTitle:'重新连接搜索树',followLatest:'↓ 回到最新事件'});Object.assign(MESSAGE_CATALOGS.en,{treeIdle:'The search tree will appear after the run starts',treeSynced:{one:'{{count}} node · synced',other:'{{count}} nodes · synced'},treeAwaitingFirstNode:'Search nodes will appear after the first round completes',treeSyncFailed:'Search-tree sync failed: {{message}} · retrying',treeLatestTitle:'Follow the latest node',treeFitTitle:'Fit the entire search tree',treeRetryTitle:'Reconnect the search tree',followLatest:'↓ Back to latest event'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{demoPickerTitle:'选择内置样例数据',demoPickerHelp:'生成后将自动加载为当前工作区的 context.data 数据集。',demoPolynomialTitle:'多项式回归',demoPolynomialHelp:'含两个连续自变量的二元二次多项式。',demoGroupedTitle:'分组参数',demoGroupedHelp:'不同类别标签对应不同衰减系数的分组回归数据。',demoOdeTitle:'受迫非线性振荡 ODE',demoOdeHelp:'多频周期驱动下的非线性一维振子状态与速度轨迹。',demoKuramotoTitle:'Kuramoto 耦合网络',demoKuramotoHelp:'10 节点无标度（BA）有向网络上的耦合振子相位动力学。'});Object.assign(MESSAGE_CATALOGS.en,{demoPickerTitle:'Choose Sample Data',demoPickerHelp:'The generated dataset will be loaded as the current context.data.',demoPolynomialTitle:'Polynomial Regression',demoPolynomialHelp:'Two continuous inputs and one regression target.',demoGroupedTitle:'Grouped Parameters',demoGroupedHelp:'A categorical label selects one of several hidden parameters.',demoOdeTitle:'Oscillatory ODE',demoOdeHelp:'A nonlinear one-dimensional trajectory with multi-frequency periodic forcing.',demoKuramotoTitle:'Kuramoto Network',demoKuramotoHelp:'Coupled-oscillator trajectories on a 10-node scale-free network.'});
Object.assign(MESSAGE_CATALOGS['zh-CN'],{conversations:'对话',workspacePanel:'工作区',newConversation:'新建对话',refreshConversations:'刷新对话',renameConversation:'重命名',exportConversation:'导出',archiveConversation:'删除',conversationMore:'更多操作',conversationEmpty:'还没有对话。',conversationNamePlaceholder:'输入对话名称'});Object.assign(MESSAGE_CATALOGS.en,{conversations:'Chats',workspacePanel:'Workspace',newConversation:'New chat',refreshConversations:'Refresh chats',renameConversation:'Rename',exportConversation:'Export',archiveConversation:'Delete',conversationMore:'More actions',conversationEmpty:'No chats yet.',conversationNamePlaceholder:'Enter a chat name'});
function _(key,values={}){
  const baseLocale=currentLocale.split('-')[0],catalog=MESSAGE_CATALOGS[currentLocale]||MESSAGE_CATALOGS[baseLocale]||{},fallback=MESSAGE_CATALOGS[DEFAULT_LOCALE]||{};
  let message=catalog[key]??fallback[key];if(message===undefined)return key;
  if(message&&typeof message==='object'){const category=new Intl.PluralRules(currentLocale).select(Number(values.count));message=message[category]??message.other??Object.values(message)[0]}
  return String(message).replace(/\{\{\s*([\w]+)\s*\}\}/g,(_,name)=>values[name]===undefined?'{{'+name+'}}':String(values[name]));
}
function setText(selector,key,values){const node=document.querySelector(selector);if(node)node.textContent=_(key,values)}
let treeStatusKey='treeIdle',treeStatusValues={};
function setTreeStatus(key,values={}){treeStatusKey=key;treeStatusValues=values;$('tree-status').textContent=_(key,values)}
function configureTreeControls(){
  const controls={
    'tree-latest':['treeLatestTitle','<circle cx="8" cy="8" r="4.5"/><circle cx="8" cy="8" r="1.4"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2"/>'],
    'tree-fit':['treeFitTitle','<path d="M6 3H3v3M10 3h3v3M6 13H3v-3M10 13h3v-3"/>'],
    'tree-retry':['treeRetryTitle','<path d="M12.7 6.2A5 5 0 1 0 13 9M12.7 3.5v2.8H9.9"/>'],
  };
  for(const [id,[key,icon]] of Object.entries(controls)){const button=$(id),label=_(key);button.classList.add('icon-button');if(!button.querySelector('svg'))button.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true">'+icon+'</svg>';button.title=label;button.setAttribute('aria-label',label)}
}
function timelineToolState(pending,failed,duration){
  const node=el('span',undefined,'tool-state'+(failed?' failed':''));node.dataset.timelineState=pending?'toolRunning':failed?'toolFailed':'toolReturned';node.dataset.duration=String(duration);renderLocalizedTimelineText(node);return node;
}
function markContextStatus(node,coord,count,characters){node.dataset.contextCoord=coord;node.dataset.contextCount=String(count);node.dataset.contextCharacters=characters;renderLocalizedTimelineText(node);return node}
function renderLocalizedTimelineText(root=document){
  const nodes=root.matches?.('[data-timeline-state],[data-context-count]')?[root]:root.querySelectorAll?.('[data-timeline-state],[data-context-count]')||[];
  for(const node of nodes){
    if(node.dataset.timelineState){const pending=node.dataset.timelineState==='toolRunning',label=_(node.dataset.timelineState);node.textContent=pending?label:label+' · '+formatDuration(Number(node.dataset.duration||0))}
    else if(node.dataset.contextCount){const size=_('contextStats',{count:Number(node.dataset.contextCount),characters:node.dataset.contextCharacters}),parts=[node.dataset.contextCoord,size,_('contextWaiting')].filter(Boolean);node.textContent=parts.join(' · ')}
  }
}
function renderSearchSettingLabels(){for(const [id,key] of [['R','restartCount'],['C','branchCount'],['L','conversationDepth'],['K','samplesPerRound'],['stop-review-rounds','stopReviewRounds'],['stop-guard-mode','stopGuardMode'],['stop-guard-metric','stopGuardMetric'],['stop-guard-threshold','stopGuardThreshold'],['stop-guard-split','stopGuardSplit']]){const control=$(id),label=control?.closest('.settings-field,label')?.querySelector('span');if(label)label.textContent=_(key)}setText('#pause-on-truncation-label','pauseOnTruncation');setText('#pause-on-truncation-help','pauseOnTruncationHelp');setText('#stop-guard-larger-label','stopGuardLargerBetter');setText('#stop-guard-larger-help','stopGuardLargerBetterHelp');if($('stop-guard-mode'))for(const option of $('stop-guard-mode').options)option.textContent=_({none:'stopGuardNone',best_in_topk:'stopGuardTopk',metric_threshold:'stopGuardMetricThreshold',budget_exhausted:'stopGuardBudget'}[option.value])}
function renderAdvanceControls(){for(const [id,key] of [['next-c','nextC'],['next-r','nextR']]){const button=$(id),label=_(key);button.textContent='+1';button.title=label;button.setAttribute('aria-label',label)}}
function mountAdvanceControls(){for(const [inputId,buttonId] of [['R','next-c'],['C','next-r']]){const input=$(inputId),button=$(buttonId),control=document.createElement('span');control.className='search-step-control';input.replaceWith(control);control.append(input,button)}renderAdvanceControls()}
function mountTruncationSetting(){const list=$('initial-diagnostics').closest('.switch-list'),label=el('label',undefined,'switch-row'),copy=el('span'),title=el('b',undefined);title.id='pause-on-truncation-label';const help=el('small',undefined);help.id='pause-on-truncation-help';const input=document.createElement('input');input.id='pause-on-truncation';input.type='checkbox';input.checked=true;copy.append(title,help);label.append(copy,input);list.append(label)}
function updateStopSettingVisibility(){const mode=$('stop-guard-mode').value,usesThreshold=mode==='metric_threshold';$('stop-guard-metric').closest('label').hidden=!usesThreshold;for(const id of ['stop-guard-threshold','stop-guard-split'])$(id).closest('label').hidden=!usesThreshold;$('stop-guard-larger').closest('label').hidden=!usesThreshold}
function mountStopSettings(){const pane=$('settings-pane-search'),form=pane.querySelector('.settings-form'),list=pane.querySelector('.switch-list');function field(id,type,options){const label=el('label'),title=el('span'),control=document.createElement(type==='select'?'select':'input');control.id=id;if(type==='select')for(const [value,text] of options)control.append(Object.assign(el('option',text),{value}));else control.type=type;label.append(title,control);form.append(label);return control}const rounds=field('stop-review-rounds','number');rounds.min='0';rounds.max='1000';rounds.value='1';const mode=field('stop-guard-mode','select',[['none',''],['best_in_topk',''],['metric_threshold',''],['budget_exhausted','']]);field('stop-guard-metric','text').placeholder='r2';const threshold=field('stop-guard-threshold','number');threshold.step='any';field('stop-guard-split','select',[['validation','validation'],['train','train']]);const label=el('label',undefined,'switch-row'),copy=el('span'),title=el('b'),help=el('small'),input=document.createElement('input');title.id='stop-guard-larger-label';help.id='stop-guard-larger-help';input.id='stop-guard-larger';input.type='checkbox';input.checked=true;copy.append(title,help);label.append(copy,input);list.append(label);mode.onchange=updateStopSettingVisibility;renderSearchSettingLabels();updateStopSettingVisibility()}
function normalizeCompositeField(controlId,labelId){const control=$(controlId),host=control?.closest('label');if(!host)return;const field=document.createElement('div');field.className=(host.className+' settings-field').trim();if(controlId.includes('api-key'))field.classList.add('api-key-setting');for(const attribute of host.attributes)if(attribute.name!=='class'&&attribute.name!=='for')field.setAttribute(attribute.name,attribute.value);field.append(...host.childNodes);host.replaceWith(field);let label=field.querySelector('#'+CSS.escape(labelId));if(!label)label=field.firstElementChild;if(label){label.id=labelId;control.setAttribute('aria-labelledby',labelId)}}
function renderIconAction(button,label,kind){if(!button)return;const icons={upload:'<path d="M8 10.5v-7m-3 3 3-3 3 3M3 10v2.5h10V10"/>',save:'<path d="M3 2.5h8l2 2v9H3zM5 2.5v4h5v-4M5 13v-4h6v4"/>'};button.classList.add('icon-only-action');button.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true">'+icons[kind]+'</svg>';button.title=label;button.setAttribute('aria-label',label)}
function applyTheme(){document.documentElement.dataset.theme=uiTheme;const dark=uiTheme==='dark',button=$('theme-toggle'),label=_(dark?'themeLight':'themeDark');document.querySelector('meta[name="theme-color"]').content='#1F2C7E';button.textContent=dark?'☀':'☾';button.title=label;button.setAttribute('aria-label',label);renderIconAction($('data-upload'),_('uploadCsv'),'upload');localStorage.setItem('sr-harness-theme',uiTheme);try{$('tree').contentWindow.postMessage({type:'sr-tree-theme',theme:uiTheme},location.origin)}catch{}}
function renderHeaderControls(){
  if(!session){$('connection').textContent=_('connection');$('status').textContent=_('connection');return}
  const interaction=session.interaction_state;
  $('status').textContent=interaction==='paused'?_('paused'):interaction==='pausing'?_('pauseRequested'):interaction==='interrupting'?_('stopping'):_(session.state);
  renderActivity();
}
function renderTimelineWelcome(){
  const welcome=$('welcome');if(!welcome)return;const active=session&&session.state!=='idle',prefix=active?'timelinePending':'welcome';
  welcome.querySelector('.eyebrow').textContent=_(prefix+'Eyebrow');welcome.querySelector('h1').textContent=_(prefix+'Title');welcome.querySelector('p').textContent=_(prefix+'Body');
}
function renderDataAgentHelp(){const help=$('data-agent-help'),link=$('data-agent-safety'),guide=$('context-data-guide-link'),titleRow=document.querySelector('.data-agent-title-row');help.textContent=_('dataAgentHelp');link.textContent=_('dataAgentSafety');guide.textContent=_('dataAgentDetails');if(link.parentElement!==titleRow)titleRow.append(link)}
const DATA_PROVIDER_API_KEY_URLS={openrouter:'https://openrouter.ai/settings/keys',openai:'https://platform.openai.com/api-keys',deepseek:'https://platform.deepseek.com/api_keys',siliconflow:'https://cloud.siliconflow.cn/account/ak',gemini:'https://aistudio.google.com/app/apikey',lmstudio:'https://lmstudio.ai/docs/developer/openai-compat'},DATA_PROVIDER_ENV_VARS={openrouter:'OPENROUTER_API_KEY',openai:'OPENAI_API_KEY',deepseek:'DEEPSEEK_API_KEY',siliconflow:'SILICONFLOW_API_KEY',gemini:'GEMINI_API_KEY',lmstudio:'LMSTUDIO_API_KEY'};let apiKeyEnvVar='',dataApiKeyEnvVar='';
function renderApiKeyLabel(provider=$('provider').value,envVar=apiKeyEnvVar){provider=String(provider||'').toLowerCase();envVar=envVar||DATA_PROVIDER_ENV_VARS[provider]||'API_KEY';const link=document.createElement('a');link.href=DATA_PROVIDER_API_KEY_URLS[provider]||'#';link.target='_blank';link.rel='noopener';link.textContent=_('apiKeyGet',{env:envVar});$('api-key-label').replaceChildren('API Key (',link,')')}
function renderApiKeyVisibility(){const button=$('api-key-visibility'),visible=$('api-key').type==='text',label=_(visible?'apiKeyHide':'apiKeyShow');button.innerHTML='<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M2.2 10s2.8-5 7.8-5 7.8 5 7.8 5-2.8 5-7.8 5-7.8-5-7.8-5Z"/><circle cx="10" cy="10" r="2.2"/><path class="visibility-slash" d="m4 4 12 12"/></svg>';button.classList.toggle('is-visible',visible);button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(visible))}
function renderDataApiKeyLabel(provider=$('data-provider').value,envVar=dataApiKeyEnvVar){provider=String(provider||'').toLowerCase();envVar=envVar||DATA_PROVIDER_ENV_VARS[provider]||'API_KEY';const link=document.createElement('a');link.href=DATA_PROVIDER_API_KEY_URLS[provider]||'#';link.target='_blank';link.rel='noopener';link.textContent=_('apiKeyGet',{env:envVar});$('data-api-key-label').replaceChildren('API Key (',link,')')}
function renderDataApiKeyVisibility(){const button=$('data-api-key-visibility'),visible=$('data-api-key').type==='text',label=_(visible?'apiKeyHide':'apiKeyShow');button.innerHTML='<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M2.2 10s2.8-5 7.8-5 7.8 5 7.8 5-2.8 5-7.8 5-7.8-5-7.8-5Z"/><circle cx="10" cy="10" r="2.2"/><path class="visibility-slash" d="m4 4 12 12"/></svg>';button.classList.toggle('is-visible',visible);button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(visible))}
function renderDemoPickerLanguage(){
  $('demo-picker-title').textContent=currentLocale==='en'?'Scientific discovery tasks':'选择科学发现任务';
  $('demo-picker-help').textContent=currentLocale==='en'?'Choose a study to begin.':'选择一项研究，开始探索。';
  $('demo-picker-close').setAttribute('aria-label',_('settingsClose'));$('create-demo').title=$('demo-picker-title').textContent;
}
function applyLanguage(){
  document.documentElement.lang=currentLocale;document.title=_('appTitle');localStorage.setItem('sr-harness-language',currentLocale);renderDemoPickerLanguage();
  renderMarkdownModeButtons();
  configureTreeControls();setTreeStatus(treeStatusKey,treeStatusValues);$('follow').textContent=_('followLatest');renderLocalizedTimelineText();
  updateDocumentationLinks();
  renderHeaderControls();renderTimelineWelcome();renderEvaluatorLanguage();renderConversationLanguage();
  if($('model-test'))$('model-test').textContent=_('dataAgentModelTest');
  for(const [id,key] of [['workspace-title','workspace'],['drop-title','dropTitle'],['upload','chooseFile'],['prepare-tab','prepare'],['data-tab','data'],['timeline-tab','timeline'],['task-problem-title','taskProblemTitle'],['task-problem-help','taskProblemHelp'],['composer-purpose-title','composerPurposeTitle'],['composer-purpose-help','composerPurposeHelp'],['system-prompt-confirm-title','systemPromptConfirmTitle'],['system-prompt-confirm-help','systemPromptConfirmHelp'],['initial-prompt-title','systemPrompt'],['initial-prompt-toggle-label','systemPrompt'],['data-insights-title','dataInsightsTitle'],['relationship-preview-title','relationship'],['context-tab','context'],['tree-title','tree'],['tree-latest','latest'],['tree-fit','overview'],['full-tree','fullViewer'],['candidate-title','candidates'],['data-upload','uploadCsv'],['create-demo','sampleData'],['settings-title','settings'],['settings-subtitle','settingsSubtitle'],['settings-tab-model','modelSettings'],['settings-tab-search','searchSettings'],['settings-tab-capabilities','capabilitySettings'],['strong-provider-label','strongProvider'],['strong-model-label','strongModel'],['tool-parser-label','toolParser'],['max-tokens-label','maxTokens'],['api-key-label','apiKey'],['auto-routing-label','autoRouting'],['auto-routing-help','autoRoutingHelp'],['restart-top-k-label','restartTopK'],['max-workers-label','maxWorkers'],['validation-fraction-label','validationFraction'],['split-by-label','splitBy'],['split-seed-label','splitSeed'],['ranking-metric-label','rankingMetric'],['larger-better-label','largerBetter'],['larger-better-help','largerBetterHelp'],['initial-diagnostics-label','initialDiagnostics'],['initial-diagnostics-help','initialDiagnosticsHelp'],['tools-settings-title','availableTools'],['skills-settings-title','availableSkills'],['next-c','nextC'],['next-r','nextR'],['settings-toggle-label','settingsToggle'],['settings-cancel','settingsCancel'],['apply','apply']])if($(id))$(id).textContent=_(key);
  configureTreeControls();
  for(const [id,key] of [['data-agent-settings-toggle-label','settingsToggle'],['data-agent-settings-title','dataAgentSettingsTitle'],['data-agent-settings-subtitle','dataAgentSettingsSubtitle'],['data-provider-label','dataAgentProvider'],['data-model-label','dataAgentModel'],['data-proxy-label','dataAgentProxy'],['data-api-key-label','apiKey'],['data-tool-parser-label','toolParser'],['data-max-tokens-label','maxTokens'],['data-tools-settings-title','availableTools'],['data-skills-settings-title','availableSkills'],['data-settings-hint','dataAgentSettingsHint'],['data-model-test','dataAgentModelTest'],['data-settings-cancel','settingsCancel'],['data-settings-apply','apply']])$(id).textContent=_(key);for(const button of document.querySelectorAll('[data-data-settings-tab]'))button.textContent=_(button.dataset.dataSettingsTab==='model'?'modelSettings':'capabilitySettings');$('data-api-key-visibility').textContent=_($('data-api-key').type==='password'?'apiKeyShow':'apiKeyHide');$('data-agent-settings-close').title=_('settingsClose');$('data-agent-settings-close').setAttribute('aria-label',_('settingsClose'));updateDataCapabilityCounts();setText('#data-preparation .data-intro h2','prepare');setText('#data-preparation .data-intro p','prepareIntro');setText('#data-setup .data-intro h2','data');setText('#data-setup .data-intro p','dataIntro');setText('#run-setup-title','runSetupTitle');setText('#run-setup-help','runSetupSummary');setText('#data-upload-title','uploadDataTitle');setText('#data-upload-help-prefix','uploadDataHelpPrefix');setText('#data-upload-help-suffix','uploadDataHelpSuffix');setText('#data-drop-copy','dataDropCopy');setText('#data-table-title','csvData');setText('#data-refresh-label','refreshData');const dataRefreshLabel=_('refreshData');$('data-refresh').title=dataRefreshLabel;$('data-refresh').setAttribute('aria-label',dataRefreshLabel);setText('#data-agent-title','dataAgentTitle');setText('#data-agent-safety','dataAgentSafety');setText('#data-agent-help','dataAgentHelp');setText('#variable-config-card h3','variableConfigTitle');setText('#run-variable-preview h3','variablePreviewTitle');setText('.variable-help','variableHelp');setText('.variable-preview-help','variablePreviewSummary');setText('.relationship-heading h3','relationship');setText('.relationship-heading span','relationshipHelp');setText('.problem-card>h3','problem');
  renderDataAgentHelp();renderApiKeyLabel();renderApiKeyVisibility();renderDataApiKeyLabel();renderDataApiKeyVisibility();
  for(const head of document.querySelectorAll('.variable-table-head')){const headings=head.querySelectorAll(':scope>span');if(head.closest('#run-variable-preview')&&headings.length>=2){headings[0].textContent=_('variable');headings[1].textContent=_('description')}else if(headings.length>=4){headings[1].textContent=_('role');headings[2].textContent=_('variable');headings[3].textContent=_('description')}}
  $('plot-empty').textContent=_('dropVariable');for(const value of document.querySelectorAll('.plot-slot-value'))value.dataset.placeholder=_('dropVariable');$('problem-description').placeholder=_('taskProblemPlaceholder');$('data-agent-input').placeholder=_('dataAgentPlaceholder');$('data-proxy').placeholder=_('dataAgentProxyPlaceholder');const dataSendLabel=_('dataAgentSend');$('data-agent-send').title=dataSendLabel;$('data-agent-send').setAttribute('aria-label',dataSendLabel);$('settings-hint').textContent=_('settingsHint');$('api-key-visibility').textContent=_($('api-key').type==='password'?'apiKeyShow':'apiKeyHide');$('strong-model').placeholder=_('strongModelPlaceholder');$('strong-provider').querySelector('option[value=""]').textContent=_('followBaseModel');$('settings-close').title=_('settingsClose');$('settings-close').setAttribute('aria-label',_('settingsClose'));$('initial-prompt-close').title=_('settingsClose');$('initial-prompt-close').setAttribute('aria-label',_('settingsClose'));for(const [id,key] of [['new-folder','newFolder'],['refresh','refreshFiles'],['workspace-name-confirm','apply'],['workspace-name-cancel','settingsCancel']]){const label=_(key);$(id).title=label;$(id).setAttribute('aria-label',label)}if(!$('workspace-name-editor').hidden)$('workspace-name-input').placeholder=_(workspaceEditItem?'renamePrompt':'newFolderPrompt');filesSignature='';refreshFiles().catch(notice);updateCapabilityCounts();
  renderApiKeyVisibility();renderSearchSettingLabels();renderAdvanceControls();const documentationLabel=_('documentation'),documentationLink=$('documentation-link');documentationLink.title=documentationLabel;documentationLink.setAttribute('aria-label',documentationLabel);const githubLabel=_('githubRepository'),githubLink=$('github-link');githubLink.title=githubLabel;githubLink.setAttribute('aria-label',githubLabel);const languageButton=$('language-toggle'),languageLabel=_('languageSwitch');languageButton.textContent=_('languageSwitchShort');languageButton.title=languageLabel;languageButton.setAttribute('aria-label',languageLabel);renderVariableRoleTable();renderPlotVariablePalette();renderPlotSlots();renderPlotModeLanguage();renderDataNumberFormatControls();renderDataPreviewGroupPicker();renderDataTable();renderActivePlot();const visibleContext=selectedContextKey?contextHistory.get(selectedContextKey):latestContext;if(visibleContext){contextSignature='';renderContext(visibleContext)}applyTheme();applyPanelLayout();$('topk').dataset.sig='';renderTopk();renderTimelineSurface();renderWorkflowNextControls();
}
async function ensureCapabilities(){if(!capabilities)capabilities=await api('/api/session/capabilities',undefined,'GET');return capabilities}
function effectiveSettings(){return {...(session?.settings||{}),...(session?.pending_settings||{})}}
function sessionSettingsEditable(value=session){return ['idle','starting','running'].includes(value?.state)}
function sessionSettingsQueued(value=session){return ['starting','running'].includes(value?.state)}
function agentSettingsQueued(interactionState){return ['running','pausing','interrupting','paused'].includes(interactionState)}
function selectedCapabilityNames(id){return [...$(id).querySelectorAll('input[type=checkbox]:checked')].map(input=>input.value)}
function updateCapabilityCounts(){for(const [hostId,countId] of [['tool-options','tools-count'],['skill-options','skills-count']]){const host=$(hostId),inputs=[...host.querySelectorAll('input[type=checkbox]')];$(countId).textContent=_('selectedCount',{selected:inputs.filter(input=>input.checked).length,total:inputs.length})}}
function renderCapabilityOptions(hostId,items,selected,onchange=updateCapabilityCounts){const host=$(hostId),enabled=new Set(selected??items.map(item=>item.name));host.replaceChildren();for(const item of items){const label=el('label',undefined,'capability-option'),input=document.createElement('input'),copy=el('span',undefined,'capability-copy');input.type='checkbox';input.value=item.name;input.checked=enabled.has(item.name);input.onchange=onchange;copy.append(el('span',item.name,'capability-name'),el('span',item.description||'','capability-description'));label.title=item.description||item.name;label.append(input,copy);host.append(label)}}
async function refreshProviderCredential(){const provider=$('provider').value,token=++credentialRequestToken,input=$('api-key');input.placeholder='…';const credential=await api('/api/session/provider-credential?provider='+encodeURIComponent(provider),undefined,'GET');if(token!==credentialRequestToken||provider!==$('provider').value)return;apiKeyEnvVar=credential.env_var;$('api-key-env').textContent=credential.env_var;renderApiKeyLabel(provider,credential.env_var);input.placeholder=credential.configured?_('apiKeyConfigured'):_('apiKeyPlaceholder',{env:credential.env_var})}
async function saveProviderCredential(){const input=$('api-key'),apiKey=input.value.trim();if(!apiKey)return null;const credential=await api('/api/session/provider-credential',{provider:$('provider').value,api_key:apiKey},'PUT');input.value='';input.type='password';renderApiKeyVisibility();await refreshProviderCredential();return credential}
async function syncSettingsForm(){const available=await ensureCapabilities(),settings=effectiveSettings();$('provider').value=settings.llm_provider||'openrouter';$('model').value=settings.llm_model||'';$('strong-provider').value=settings.strong_llm_provider||'';$('strong-model').value=settings.strong_llm_model||'';$('tool-parser').value=settings.tool_parser||'openai';$('max-tokens').value=settings.llm_max_tokens??'';$('auto-routing').checked=Boolean(settings.auto_routing);for(const [id,key] of Object.entries({R:'max_restart_loop',C:'global_width',L:'max_refinement_depth',K:'local_sample_size','restart-top-k':'restart_top_k','max-workers':'max_workers','stop-review-rounds':'tool_free_stop_review_rounds'}))if(settings[key]!==undefined)$(id).value=settings[key]??'';$('initial-diagnostics').checked=Boolean(settings.force_initial_diagnostics);$('pause-on-truncation').checked=settings.pause_on_truncated_response!==false;$('stop-guard-mode').value=settings.stop_guard_mode||'none';$('stop-guard-metric').value=settings.stop_guard_metric||'';$('stop-guard-threshold').value=settings.stop_guard_threshold??'';$('stop-guard-split').value=settings.stop_guard_split||'validation';$('stop-guard-larger').checked=settings.stop_guard_larger_is_better!==false;updateStopSettingVisibility();renderCapabilityOptions('tool-options',available.tools,settings.tools??available.default_tools);renderCapabilityOptions('skill-options',available.skills,settings.skills??available.default_skills);updateCapabilityCounts();await refreshProviderCredential()}
function setInitialPromptOpen(open){open=Boolean(open&&(session?.state||'idle')==='idle');$('initial-prompt-panel').hidden=!open;$('initial-prompt-toggle').setAttribute('aria-expanded',String(open));if(open){$('settings-panel').hidden=true;$('settings-toggle').setAttribute('aria-expanded','false')}}
async function setSettingsOpen(open){$('settings-panel').hidden=!open;$('settings-toggle').setAttribute('aria-expanded',String(open));if(open){setInitialPromptOpen(false);await syncSettingsForm()}}
async function ensureDataCapabilities(){if(!dataCapabilities)dataCapabilities=await api('/api/session/capabilities?agent=data',undefined,'GET');return dataCapabilities}
function updateDataCapabilityCounts(){for(const [hostId,countId] of [['data-tool-options','data-tools-count'],['data-skill-options','data-skills-count']]){const host=$(hostId),inputs=[...host.querySelectorAll('input[type=checkbox]')];$(countId).textContent=_('selectedCount',{selected:inputs.filter(input=>input.checked).length,total:inputs.length})}}
async function refreshDataProviderCredential(){const provider=$('data-provider').value,token=++dataCredentialRequestToken,input=$('data-api-key');input.placeholder='…';const credential=await api('/api/session/provider-credential?provider='+encodeURIComponent(provider),undefined,'GET');if(token!==dataCredentialRequestToken||provider!==$('data-provider').value)return;dataApiKeyEnvVar=credential.env_var;$('data-api-key-env').textContent=credential.env_var;renderDataApiKeyLabel(provider,credential.env_var);input.placeholder=credential.configured?_('apiKeyConfigured'):_('apiKeyPlaceholder',{env:credential.env_var})}
async function saveDataProviderCredential(){const input=$('data-api-key'),apiKey=input.value.trim();if(!apiKey)return null;const credential=await api('/api/session/provider-credential',{provider:$('data-provider').value,api_key:apiKey},'PUT');input.value='';input.type='password';renderDataApiKeyVisibility();await refreshDataProviderCredential();return credential}
function dataAgentSettingsPayload(){return {llm_provider:$('data-provider').value,llm_model:$('data-model').value.trim(),proxy:$('data-proxy').value.trim(),tool_parser:$('data-tool-parser').value,llm_max_tokens:optionalTokenLimit('data-max-tokens'),tools:selectedCapabilityNames('data-tool-options'),skills:selectedCapabilityNames('data-skill-options')}}
async function syncDataAgentSettingsForm(){const available=await ensureDataCapabilities(),settings=session?.data_agent_settings||{};$('data-provider').value=settings.llm_provider||'openrouter';$('data-model').value=settings.llm_model||'';$('data-proxy').value=settings.proxy||'';$('data-tool-parser').value=settings.tool_parser||'openai';$('data-max-tokens').value=settings.llm_max_tokens??'';renderCapabilityOptions('data-tool-options',available.tools,settings.tools??available.default_tools,updateDataCapabilityCounts);renderCapabilityOptions('data-skill-options',available.skills,settings.skills??available.default_skills,updateDataCapabilityCounts);updateDataCapabilityCounts();await refreshDataProviderCredential()}
function selectDataSettingsTab(name){for(const button of document.querySelectorAll('[data-data-settings-tab]'))button.classList.toggle('active',button.dataset.dataSettingsTab===name);for(const pane of document.querySelectorAll('[data-data-settings-pane]')){const active=pane.dataset.dataSettingsPane===name;pane.classList.toggle('active',active);pane.hidden=!active}}
async function setDataAgentSettingsOpen(open){$('data-agent-settings').hidden=!open;$('data-agent-settings-toggle').setAttribute('aria-expanded',String(open));if(open)await syncDataAgentSettingsForm()}
async function testDataAgentModel(){const button=$('data-model-test'),status=$('data-model-test-status');button.disabled=true;status.className='model-test-status';status.textContent=_('dataAgentModelTesting');try{await saveDataProviderCredential();const result=await api('/api/data/agent/test',dataAgentSettingsPayload());status.classList.add(result.ok?'passed':'failed');status.textContent=_(result.ok?'dataAgentModelTestPassed':result.accessible?'dataAgentModelTestPartial':'dataAgentModelTestUnavailable')}catch(error){status.classList.add('failed');status.textContent=error?.message||String(error)}finally{button.disabled=false}}

function settingsPayload(){const stopThreshold=$('stop-guard-threshold').value.trim();return {llm_provider:$('provider').value,llm_model:$('model').value.trim(),strong_llm_provider:$('strong-provider').value||null,strong_llm_model:$('strong-model').value.trim()||null,auto_routing:$('auto-routing').checked,tool_parser:$('tool-parser').value,llm_max_tokens:optionalTokenLimit('max-tokens'),tools:selectedCapabilityNames('tool-options'),skills:selectedCapabilityNames('skill-options'),max_restart_loop:Number($('R').value),global_width:Number($('C').value),max_refinement_depth:Number($('L').value),local_sample_size:Number($('K').value),restart_top_k:Number($('restart-top-k').value),max_workers:Number($('max-workers').value),force_initial_diagnostics:$('initial-diagnostics').checked,pause_on_truncated_response:$('pause-on-truncation').checked,tool_free_stop_review_rounds:Number($('stop-review-rounds').value),stop_guard_mode:$('stop-guard-mode').value,stop_guard_metric:$('stop-guard-metric').value.trim()||null,stop_guard_threshold:stopThreshold===''?null:Number(stopThreshold),stop_guard_split:$('stop-guard-split').value,stop_guard_larger_is_better:$('stop-guard-larger').checked}}
async function testModel(){const button=$('model-test'),status=$('model-test-status');button.disabled=true;status.className='model-test-status';status.textContent=_('dataAgentModelTesting');try{await saveProviderCredential();const result=await api('/api/session/test',settingsPayload());status.classList.add(result.ok?'passed':'failed');status.textContent=_(result.ok?'dataAgentModelTestPassed':result.accessible?'dataAgentModelTestPartial':'dataAgentModelTestUnavailable')}catch(error){status.classList.add('failed');status.textContent=error?.message||String(error)}finally{button.disabled=false}}
function selectSettingsTab(name){for(const button of document.querySelectorAll('[data-settings-tab]'))button.classList.toggle('active',button.dataset.settingsTab===name);for(const pane of document.querySelectorAll('[data-settings-pane]')){const active=pane.dataset.settingsPane===name;pane.classList.toggle('active',active);pane.hidden=!active}}
function optionalTokenLimit(id){const value=$(id).value.trim();return value===''?null:Number(value)}
const pretty=v=>typeof v==='string'?v:JSON.stringify(v,null,2);
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
const agentOutputSources=new WeakMap(),MATH_NS='http://www.w3.org/1998/Math/MathML';
function mathNode(tag,text){const node=document.createElementNS(MATH_NS,tag);if(text!==undefined)node.textContent=text;return node}
function texMath(source,display=false){
  const commands={alpha:'α',beta:'β',gamma:'γ',delta:'δ',epsilon:'ϵ',varepsilon:'ε',theta:'θ',vartheta:'ϑ',lambda:'λ',mu:'μ',pi:'π',rho:'ρ',sigma:'σ',phi:'ϕ',varphi:'φ',omega:'ω',Gamma:'Γ',Delta:'Δ',Theta:'Θ',Lambda:'Λ',Sigma:'Σ',Phi:'Φ',Omega:'Ω',times:'×',cdot:'·',pm:'±',mp:'∓',le:'≤',leq:'≤',ge:'≥',geq:'≥',neq:'≠',approx:'≈',infty:'∞',sum:'∑',prod:'∏',int:'∫',partial:'∂',nabla:'∇',rightarrow:'→',leftarrow:'←'};
  const spacing={'!':'-0.1667em',',':'0.1667em','>':'0.2222em',':':'0.2222em',';':'0.2778em',' ':'0.3333em',thinspace:'0.1667em',medspace:'0.2222em',thickspace:'0.2778em',negthinspace:'-0.1667em',quad:'1em',qquad:'2em'};
  let index=0;
  const group=()=>{if(source[index]==='{'){index+=1;const value=sequence('}');if(source[index]==='}')index+=1;return value}return atom()};
  const atom=()=>{
    if(index>=source.length)return mathNode('mrow');
    const character=source[index++];
    if(character==='\\'){
      const match=source.slice(index).match(/^[A-Za-z]+/),command=match?.[0]||source[index++]||'';if(match)index+=command.length;
      if(Object.hasOwn(spacing,command)){const space=mathNode('mspace'),width=spacing[command];if(width.startsWith('-')){space.setAttribute('width','0');space.style.marginInlineStart=width}else space.setAttribute('width',width);return space}
      if(command==='left'||command==='right')return atom();
      if(command==='frac'){const fraction=mathNode('mfrac');fraction.append(group(),group());return fraction}
      if(command==='sqrt'){const root=mathNode('msqrt');root.append(group());return root}
      if(['text','operatorname','mathrm','mathbf','mathit'].includes(command)){const content=group(),style=mathNode(command==='text'||command==='operatorname'?'mtext':'mstyle');if(command==='mathbf')style.setAttribute('mathvariant','bold');if(command==='mathit')style.setAttribute('mathvariant','italic');style.append(content);return style}
      return mathNode(/[A-Za-zα-ωΑ-Ω]/.test(commands[command]||command)?'mi':'mo',commands[command]||command);
    }
    if(character==='{'){const value=sequence('}');if(source[index]==='}')index+=1;return value}
    if(/\d|\./.test(character)){let number=character;while(index<source.length&&/[\d.]/.test(source[index]))number+=source[index++];return mathNode('mn',number)}
    if(/[A-Za-z]/.test(character))return mathNode('mi',character);
    if(/\s/.test(character))return mathNode('mspace');
    return mathNode('mo',character);
  };
  const sequence=stop=>{const row=mathNode('mrow');while(index<source.length&&source[index]!==stop){let base=atom(),sub=null,sup=null;while(source[index]==='_'||source[index]==='^'){const marker=source[index++],script=group();if(marker==='_')sub=script;else sup=script}if(sub&&sup){const scripted=mathNode('msubsup');scripted.append(base,sub,sup);base=scripted}else if(sub){const scripted=mathNode('msub');scripted.append(base,sub);base=scripted}else if(sup){const scripted=mathNode('msup');scripted.append(base,sup);base=scripted}row.append(base)}return row};
  const math=mathNode('math');math.setAttribute('display',display?'block':'inline');math.setAttribute('aria-label',source.trim());math.append(sequence(''));return math;
}
function appendMarkdownInline(parent,text){
  let index=0,plain='';const flush=()=>{if(plain){parent.append(document.createTextNode(plain));plain=''}};
  while(index<text.length){
    if(text.startsWith('**',index)){const end=text.indexOf('**',index+2);if(end>=0){flush();const strong=el('strong');appendMarkdownInline(strong,text.slice(index+2,end));parent.append(strong);index=end+2;continue}}
    if(text[index]==='`'){const end=text.indexOf('`',index+1);if(end>=0){flush();parent.append(el('code',text.slice(index+1,end)));index=end+1;continue}}
    if(text[index]==='$'&&text[index+1]!=='$'){const end=text.indexOf('$',index+1);if(end>index+1){flush();const holder=el('span',undefined,'markdown-math-inline');holder.append(texMath(text.slice(index+1,end)));parent.append(holder);index=end+1;continue}}
    if(text[index]==='['){const middle=text.indexOf('](',index+1),end=middle>=0?text.indexOf(')',middle+2):-1;if(middle>=0&&end>=0){const href=text.slice(middle+2,end).trim();if(/^(https?:|mailto:)/i.test(href)){flush();const link=el('a');link.href=href;link.target='_blank';link.rel='noopener';appendMarkdownInline(link,text.slice(index+1,middle));parent.append(link);index=end+1;continue}}}
    if(text[index]==='*'){const end=text.indexOf('*',index+1);if(end>index+1){flush();const emphasis=el('em');appendMarkdownInline(emphasis,text.slice(index+1,end));parent.append(emphasis);index=end+1;continue}}
    plain+=text[index++];
  }
  flush();
}
function markdownFragment(value){
  const fragment=document.createDocumentFragment(),lines=String(value).replace(/\r\n?/g,'\n').split('\n');let index=0;
  const inlineBlock=(tag,text)=>{const node=el(tag);appendMarkdownInline(node,text);fragment.append(node)};
  while(index<lines.length){
    const line=lines[index];if(!line.trim()){index+=1;continue}
    if(/^\s*```/.test(line)){const language=line.trim().slice(3).trim(),content=[];index+=1;while(index<lines.length&&!/^\s*```/.test(lines[index]))content.push(lines[index++]);if(index<lines.length)index+=1;const code=el('code',content.join('\n'));if(language)code.className='language-'+language.replace(/[^\w-]/g,'');const pre=el('pre');pre.append(code);fragment.append(pre);continue}
    if(line.trim().startsWith('$$')){let formula=line.trim().slice(2),closed=formula.endsWith('$$');if(closed)formula=formula.slice(0,-2);index+=1;while(!closed&&index<lines.length){const part=lines[index++];if(part.trim().endsWith('$$')){formula+='\n'+part.trim().slice(0,-2);closed=true}else formula+='\n'+part}const holder=el('div',undefined,'markdown-math');holder.append(texMath(formula,true));fragment.append(holder);continue}
    const heading=line.match(/^\s*(#{1,6})\s+(.+)$/);if(heading){inlineBlock('h'+heading[1].length,heading[2]);index+=1;continue}
    if(/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)){fragment.append(el('hr'));index+=1;continue}
    const list=line.match(/^\s*(?:([-+*])|(\d+)\.)\s+(.+)$/);if(list){const ordered=Boolean(list[2]),container=el(ordered?'ol':'ul');while(index<lines.length){const item=lines[index].match(/^\s*(?:([-+*])|(\d+)\.)\s+(.+)$/);if(!item||Boolean(item[2])!==ordered)break;const entry=el('li');appendMarkdownInline(entry,item[3]);container.append(entry);index+=1}fragment.append(container);continue}
    if(/^\s*>\s?/.test(line)){const parts=[];while(index<lines.length&&/^\s*>\s?/.test(lines[index]))parts.push(lines[index++].replace(/^\s*>\s?/,''));const quote=el('blockquote');appendMarkdownInline(quote,parts.join('\n'));fragment.append(quote);continue}
    const paragraph=[],start=index;while(index<lines.length&&lines[index].trim()&&!/^\s*(?:```|\$\$|#{1,6}\s|>|(?:[-+*]|\d+\.)\s)/.test(lines[index]))paragraph.push(lines[index++].trim());if(index===start)paragraph.push(lines[index++]);inlineBlock('p',paragraph.join(' '));
  }
  return fragment;
}
function agentOutputScope(node){if(node.closest('#evaluator-agent-feed'))return'evaluator';if(node.closest('#data-agent-feed'))return'data';return'search'}
function renderVisibleAgentOutput(node){if(!node.isConnected||!markdownModes[agentOutputScope(node)])return;const source=agentOutputSources.get(node);if(source===undefined)return;node.classList.add('markdown-rendered');node.replaceChildren(markdownFragment(source));const block=node.closest('.reasoning-block');if(block)requestAnimationFrame(()=>layoutPreview(block))}
const agentOutputObserver='IntersectionObserver' in window?new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.target.isConnected){agentOutputObserver.unobserve(entry.target);continue}if(entry.isIntersecting){agentOutputObserver.unobserve(entry.target);renderVisibleAgentOutput(entry.target)}}},{rootMargin:'240px 0px'}):null;
function renderAgentOutput(node,value){const source=pretty(value);if(agentOutputSources.get(node)===source)return;agentOutputSources.set(node,source);node.classList.add('agent-output');node.classList.remove('markdown-rendered');node.textContent=source;if(agentOutputObserver)agentOutputObserver.observe(node);else requestAnimationFrame(()=>renderVisibleAgentOutput(node))}
function agentOutputBlock(value,extraClass=''){const node=el('div',undefined,'agent-output '+extraClass);renderAgentOutput(node,value);return node}
function refreshAgentOutputs(scope){for(const node of document.querySelectorAll('.agent-output')){if(agentOutputScope(node)!==scope)continue;agentOutputObserver?.unobserve(node);node.classList.remove('markdown-rendered');node.textContent=agentOutputSources.get(node)??'';if(markdownModes[scope])agentOutputObserver?agentOutputObserver.observe(node):requestAnimationFrame(()=>renderVisibleAgentOutput(node))}}
function renderMarkdownModeButtons(){for(const scope of ['search','data','evaluator']){const button=$(scope+'-markdown-toggle');if(!button)continue;const enabled=markdownModes[scope],label=_(enabled?'markdownOutput':'plainText'),help=_(enabled?'showPlainText':'showMarkdown');button.querySelector('span').textContent=label;button.title=help;button.setAttribute('aria-label',help);button.setAttribute('aria-pressed',String(enabled))}}
function mountMarkdownModeButtons(){const targets={search:$('settings-toggle'),data:$('data-agent-settings-toggle'),evaluator:$('evaluator-agent-settings-toggle')};for(const [scope,target] of Object.entries(targets)){const button=el('button',undefined,'composer-settings-button markdown-mode-button');button.id=scope+'-markdown-toggle';button.type='button';button.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 12V4l3 4 3-4v8M10.5 9.5l1.5 2 2-3"/></svg><span></span>';button.onclick=()=>{markdownModes[scope]=!markdownModes[scope];localStorage.setItem('sr-harness-markdown-'+scope,String(markdownModes[scope]));renderMarkdownModeButtons();refreshAgentOutputs(scope)};target.after(button)}renderMarkdownModeButtons()}
function bindEnterToSend(input,button){input.onkeydown=event=>{if(event.key!=='Enter'||event.shiftKey||event.metaKey||event.isComposing)return;event.preventDefault();if(input.value.trim()&&!button.disabled&&!button.classList.contains('stop'))button.click()}}
function composerKeyboardHint(id){const hint=el('span',_('composerEnterHint'),'composer-keyboard-hint');hint.id=id;return hint}
const AGENT_SEND_ICON='<svg viewBox="0 0 18 18" aria-hidden="true"><path d="M9 14V4M5 8l4-4 4 4"/></svg>';
const AGENT_STOP_ICON='<svg viewBox="0 0 18 18" aria-hidden="true"><rect x="5.5" y="5.5" width="7" height="7" rx="1" fill="currentColor" stroke="none"/></svg>';
const ACTIVE_INTERACTION_STATES=new Set(['running','pausing','interrupting','paused']);
function agentComposerControlState({hasInput,interaction,startAction=null,canMessage=false,canControl=false,blocked=false}){
  let action=null;
  if(!blocked){
    if(hasInput&&(startAction||canMessage))action=startAction||'message';
    else if(!hasInput&&canControl&&interaction==='running')action='pause';
    else if(!hasInput&&canControl&&interaction==='pausing')action='force_pause';
  }
  const mode=hasInput||interaction==='paused'||(interaction==='idle'&&!canControl)?'send':'stop';
  return {action,disabled:action===null,interaction,mode};
}
function renderAgentComposerButton(button,control,{sendLabel,pauseLabel,stoppingLabel=pauseLabel}){
  const pending=control.interaction==='pausing',label=control.action==='force_pause'?_('forceStop'):control.action==='pause'?pauseLabel:control.mode==='stop'?stoppingLabel:sendLabel;
  button.classList.toggle('stop',control.mode==='stop');
  button.classList.toggle('pending',pending);
  button.classList.toggle('stop-pending',pending);
  button.disabled=control.disabled;
  button.title=label;
  button.setAttribute('aria-label',label);
  button.innerHTML=control.mode==='stop'?AGENT_STOP_ICON:AGENT_SEND_ICON;
}
async function sendAgentComposerMessage({input,button,request,render,apply=syncSession,beforeRequest}){
  const message=input.value.trim();
  if(!message)throw Error(_('inputRequired'));
  button.disabled=true;
  if(beforeRequest)beforeRequest();
  try{
    const response=await request(message);
    input.value='';
    apply(response);
  }finally{
    render();
  }
}
let evaluatorConfiguration=null,evaluatorDirty=false,evaluatorCapabilities=null,evaluatorResultSignature='';
const PYTHON_KEYWORDS=new Set('and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield'.split(' '));
const PYTHON_BUILTINS=new Set('abstractmethod bool dict float int len list max min object property range set staticmethod str super tuple type'.split(' '));
const PYTHON_TOKEN_PATTERN=/(#[^\n]*|'''[\s\S]*?(?:'''|$)|"""[\s\S]*?(?:"""|$)|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\b|\b[A-Za-z_]\w*\b)/gi;
function escapeEvaluatorCode(value){return value.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}
function highlightPython(source){let output='',cursor=0;for(const match of source.matchAll(PYTHON_TOKEN_PATTERN)){output+=escapeEvaluatorCode(source.slice(cursor,match.index));const token=match[0],lower=token.toLowerCase();let kind='';if(token.startsWith('#'))kind='comment';else if(token.startsWith("'")||token.startsWith('"'))kind='string';else if(/^\d/.test(token))kind='number';else if(PYTHON_KEYWORDS.has(token))kind='keyword';else if(PYTHON_BUILTINS.has(lower))kind='builtin';output+=kind?`<span class="py-${kind}">${escapeEvaluatorCode(token)}</span>`:escapeEvaluatorCode(token);cursor=match.index+token.length}return output+escapeEvaluatorCode(source.slice(cursor))}
function mountEvaluatorHighlight(){const code=$('evaluator-code'),highlight=el('pre',undefined,'evaluator-highlight');highlight.id='evaluator-highlight';highlight.setAttribute('aria-hidden','true');code.before(highlight);code.addEventListener('scroll',()=>{highlight.scrollTop=code.scrollTop;highlight.scrollLeft=code.scrollLeft;$('evaluator-line-numbers').scrollTop=code.scrollTop})}
function mountEvaluatorWorkbench(){
  const card=el('section',undefined,'evaluator-config-card');card.id='evaluator-config-card';card.innerHTML=`<div class="evaluator-config-heading step-heading"><div class="step-heading-copy"><h3 id="evaluator-title"></h3><p id="evaluator-help"></p></div></div><div class="evaluator-editor"><div class="evaluator-editor-toolbar"><select id="evaluator-select" aria-label="Evaluator"></select><span class="spacer"></span><button id="evaluator-test" type="button"></button><button id="evaluator-save" class="primary" type="button"></button></div><div class="evaluator-code-wrap"><pre id="evaluator-line-numbers" class="evaluator-line-numbers" aria-hidden="true"></pre><textarea id="evaluator-code" class="evaluator-code" spellcheck="false" aria-label="Evaluator Python source"></textarea></div><div id="evaluator-status" class="evaluator-editor-status" role="status"></div></div><div class="evaluator-agent"><div class="evaluator-agent-heading step-heading"><div class="step-heading-copy"><div class="evaluator-agent-title-row"><b id="evaluator-agent-title"></b><a id="evaluator-agent-safety" class="data-agent-safety" href="https://yuzhthu.github.io/SRHarness/web-ui/#agent-safety" target="_blank" rel="noopener"></a></div><p id="evaluator-agent-note" class="evaluator-agent-note"></p></div></div><div id="evaluator-agent-feed" class="data-agent-feed evaluator-agent-feed" hidden></div><div class="data-agent-compose evaluator-agent-compose"><textarea id="evaluator-agent-input" rows="3"></textarea><div class="data-agent-compose-toolbar evaluator-agent-compose-toolbar"><button id="evaluator-agent-settings-toggle" class="composer-settings-button" type="button" aria-expanded="false"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 4h5m2 0h4M2.5 8h2m2 0h7M2.5 12h7m2 0h2"/><circle cx="8.5" cy="4" r="1"/><circle cx="5.5" cy="8" r="1"/><circle cx="10.5" cy="12" r="1"/></svg><span id="evaluator-agent-settings-toggle-label"></span></button><span class="spacer"></span><button id="evaluator-agent-send" class="data-agent-send evaluator-agent-send" type="button"><svg viewBox="0 0 18 18" aria-hidden="true"><path d="M9 14V4M5 8l4-4 4 4"/></svg></button></div><div id="evaluator-agent-settings" class="settings-panel data-agent-settings evaluator-agent-settings" hidden><div class="settings-scroll"><div class="settings-pane active"><div class="settings-form"><label><span id="evaluator-agent-provider-label"></span><select id="evaluator-agent-provider"><option>openrouter</option><option>openai</option><option>deepseek</option><option>siliconflow</option><option>gemini</option><option>lmstudio</option></select></label><label><span id="evaluator-agent-model-label"></span><input id="evaluator-agent-model"></label><label><span id="evaluator-agent-proxy-label"></span><input id="evaluator-agent-proxy" type="url" autocomplete="off" spellcheck="false"></label><label><span id="evaluator-agent-api-key-label"></span><span class="api-key-control"><input id="evaluator-agent-api-key" type="password" autocomplete="new-password" spellcheck="false"><button id="evaluator-agent-api-key-visibility" type="button"></button></span></label><label><span id="evaluator-agent-tool-parser-label"></span><select id="evaluator-agent-tool-parser"><option value="openai">OpenAI Native</option><option value="text">Text</option><option value="json">JSON</option><option value="xml">XML</option></select></label><label><span id="evaluator-agent-max-tokens-label"></span><input id="evaluator-agent-max-tokens" type="number" placeholder="Auto" min="1" max="1000000"></label><label><span id="evaluator-agent-max-steps-label"></span><input id="evaluator-agent-max-steps" type="number" min="1" max="256"></label></div></div></div><div class="settings-actions"><span id="evaluator-agent-settings-hint" class="small muted"></span><span class="spacer"></span><span id="evaluator-agent-model-test-status" class="model-test-status" role="status"></span><button id="evaluator-agent-model-test" type="button"></button><button id="evaluator-agent-settings-cancel" type="button"></button><button id="evaluator-agent-settings-apply" class="primary" type="button"></button></div></div></div></div>`;
  $('data-setup').append(card);const title=$('evaluator-title'),titleRow=el('span',undefined,'evaluator-title-row'),guide=document.createElement('a');title.before(titleRow);titleRow.append(title);guide.id='evaluator-guide';guide.className='evaluator-help-link';guide.href=documentationUrl('evaluator/');guide.target='_blank';guide.rel='noopener';guide.textContent='?';titleRow.append(guide);
  const toolbar=card.querySelector('.evaluator-editor-toolbar'),argsToggle=el('button',undefined);argsToggle.id='evaluator-args-toggle';argsToggle.type='button';argsToggle.setAttribute('aria-expanded','false');argsToggle.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3.5h10M3 8h10M3 12.5h10"/><circle cx="6" cy="3.5" r="1.4"/><circle cx="10.5" cy="8" r="1.4"/><circle cx="7.5" cy="12.5" r="1.4"/></svg><span id="evaluator-args-toggle-label"></span>';toolbar.insertBefore(argsToggle,$('evaluator-test'));const argsPanel=el('div',undefined,'evaluator-args-panel');argsPanel.id='evaluator-args-panel';argsPanel.hidden=true;argsPanel.innerHTML='<div class="settings-heading"><div><b id="evaluator-args-title"></b></div></div><div class="evaluator-args-grid" id="evaluator-args-grid"></div><div class="settings-actions"><span class="spacer"></span><button id="evaluator-args-cancel" type="button"></button><button id="evaluator-args-apply" class="primary" type="button"></button></div>';toolbar.after(argsPanel);
  const agentSettings=$('evaluator-agent-settings'),agentScroll=agentSettings.querySelector('.settings-scroll'),modelPane=agentScroll.querySelector('.settings-pane');modelPane.dataset.evaluatorAgentSettingsPane='model';const agentTabs=document.createElement('nav');agentTabs.className='settings-tabs';agentTabs.innerHTML='<button class="active" type="button" data-evaluator-agent-settings-tab="model"></button><button type="button" data-evaluator-agent-settings-tab="capabilities"></button>';agentSettings.insertBefore(agentTabs,agentScroll);const capabilityPane=el('div',undefined,'settings-pane');capabilityPane.dataset.evaluatorAgentSettingsPane='capabilities';capabilityPane.hidden=true;capabilityPane.innerHTML='<div class="capability-columns"><section><div class="capability-heading"><h4 id="evaluator-agent-tools-title"></h4><span id="evaluator-agent-tools-count"></span></div><div id="evaluator-agent-tool-options" class="capability-options"></div></section><section><div class="capability-heading"><h4 id="evaluator-agent-skills-title"></h4><span id="evaluator-agent-skills-count"></span></div><div id="evaluator-agent-skill-options" class="capability-options"></div></section></div>';agentScroll.append(capabilityPane);
  $('evaluator-code').oninput=()=>{evaluatorDirty=true;renderEvaluatorLineNumbers();renderEvaluatorAvailability()};$('evaluator-code').onscroll=event=>$('evaluator-line-numbers').scrollTop=event.currentTarget.scrollTop;$('evaluator-code').onkeydown=event=>{if(event.key!=='Tab')return;event.preventDefault();const input=event.currentTarget,start=input.selectionStart,end=input.selectionEnd;input.setRangeText('    ',start,end,'end');input.dispatchEvent(new Event('input'))};$('evaluator-select').onchange=guard(selectEvaluatorSource);$('evaluator-save').onclick=guard(saveEvaluatorConfiguration);$('evaluator-test').onclick=guard(testEvaluatorConfiguration);$('evaluator-args-toggle').onclick=()=>setEvaluatorArgsOpen($('evaluator-args-panel').hidden);$('evaluator-args-cancel').onclick=()=>setEvaluatorArgsOpen(false);$('evaluator-args-apply').onclick=guard(applyEvaluatorArgs);$('evaluator-agent-send').onclick=guard(runEvaluatorAgent);$('evaluator-agent-input').oninput=renderEvaluatorAgentControl;$('evaluator-agent-settings-toggle').onclick=guard(()=>setEvaluatorAgentSettingsOpen($('evaluator-agent-settings').hidden));$('evaluator-agent-settings-cancel').onclick=()=>setEvaluatorAgentSettingsOpen(false);$('evaluator-agent-settings-apply').onclick=guard(applyEvaluatorAgentSettings);$('evaluator-agent-model-test').onclick=guard(testEvaluatorAgentModel);$('evaluator-agent-provider').onchange=()=>refreshEvaluatorAgentCredential().catch(notice);$('evaluator-agent-api-key-visibility').onclick=()=>{const input=$('evaluator-agent-api-key');input.type=input.type==='password'?'text':'password';renderEvaluatorAgentApiKeyVisibility()};for(const button of agentTabs.querySelectorAll('[data-evaluator-agent-settings-tab]'))button.onclick=()=>selectEvaluatorAgentSettingsTab(button.dataset.evaluatorAgentSettingsTab);bindEnterToSend($('evaluator-agent-input'),$('evaluator-agent-send'));renderEvaluatorLanguage()}
function workflowNextControl(id,hintId,labelId){
  const control=el('div',undefined,'workflow-next'),hint=el('span',undefined,'workflow-next-copy'),button=el('button',undefined,'workflow-next-button');control.id=id;hint.id=hintId;button.id=id+'-button';button.type='button';button.disabled=true;button.innerHTML=`<span id="${labelId}"></span><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9M9 4.5 12.5 8 9 11.5"/></svg>`;control.append(hint,button);return control
}
function taskConfigurationReady(){
  const selected=evaluatorChoices().find(item=>item.id===$('evaluator-select')?.value);
  return Boolean(useCommittedContext&&targetVariable()&&researchProblemDescription()&&selected&&!selected.abstract&&!selected.invalid&&!evaluatorDirty)
}
function renderWorkflowNextControls(){
  const dataButton=$('data-preparation-next-button'),taskButton=$('data-setup-next-button');if(!dataButton||!taskButton)return;
  $('data-preparation-next-hint').textContent=_('dataNextHint');$('data-preparation-next-label').textContent=_('dataNextAction');$('data-setup-next-hint').textContent=_('taskNextHint');$('data-setup-next-label').textContent=_('taskNextAction');dataButton.disabled=!useCommittedContext;taskButton.disabled=!taskConfigurationReady()
}
function mountWorkflowNextControls(){
  const dataControl=workflowNextControl('data-preparation-next','data-preparation-next-hint','data-preparation-next-label'),taskControl=workflowNextControl('data-setup-next','data-setup-next-hint','data-setup-next-label');document.querySelector('#data-preparation>.data-layout').after(dataControl);$('evaluator-config-card').after(taskControl);$('data-preparation-next-button').onclick=()=>selectCenterTab('data');$('data-setup-next-button').onclick=()=>selectCenterTab('timeline');$('problem-description').addEventListener('input',renderWorkflowNextControls);renderWorkflowNextControls()
}
function renderEvaluatorLineNumbers(){const code=$('evaluator-code'),lines=Math.max(1,code.value.split('\n').length);$('evaluator-line-numbers').textContent=Array.from({length:lines},(_,index)=>index+1).join('\n');const highlight=$('evaluator-highlight');if(highlight)highlight.innerHTML=highlightPython(code.value)+(code.value.endsWith('\n')?' ':'')}
// Display choices belong to this editor; the server only resolves class IDs and reads source.
function evaluatorChoices(){return [
  {id:'default',label:'DefaultEvaluator（默认评测）',label_en:'DefaultEvaluator (default)'},
  {id:'graph',label:'GraphEvaluator（图与超图）',label_en:'GraphEvaluator (graph/hypergraph)'},
  {id:'observational',label:'ObservationalEvaluator（观测数据）',label_en:'ObservationalEvaluator (observations)'},
  ...(evaluatorConfiguration?.evaluators||[]),
]}
async function selectEvaluatorSource(){
  const selected=$('evaluator-select').value,generation=serverSessionGeneration,item=evaluatorChoices().find(entry=>entry.id===selected);
  $('evaluator-code').value='';evaluatorDirty=selected!==evaluatorConfiguration?.selected;renderEvaluatorAvailability();
  const result=item?.custom?item:await api('/api/evaluator?selected='+encodeURIComponent(selected),undefined,'GET');
  if(generation!==serverSessionGeneration||$('evaluator-select').value!==selected||$('evaluator-code').value)return;
  $('evaluator-code').value=result.source;renderEvaluatorLineNumbers();renderEvaluatorSelectionStatus(item);
}
function renderEvaluatorSelectionStatus(item){const status=$('evaluator-status');status.className='evaluator-editor-status'+(item?.invalid?' failed':'');status.textContent=item?.invalid?'⚠ '+item.error:item?.abstract?(currentLocale==='en'?'Abstract reference: choose another Evaluator to create an implementation.':'抽象基类仅供参考；请选择其它 Evaluator 创建具体实现。'):''}
function renderEvaluatorAvailability(){if(!$('evaluator-config-card'))return;const state=session?.state||'idle',safePaused=['starting','running'].includes(state)&&session?.interaction_state==='paused',locked=state!=='idle'&&!safePaused,selected=evaluatorChoices().find(item=>item.id===$('evaluator-select').value),abstract=Boolean(selected?.abstract),invalid=Boolean(selected?.invalid),agentActive=['running','pausing','interrupting','paused'].includes(session?.evaluator_interaction_state);$('evaluator-select').disabled=locked;$('evaluator-code').readOnly=locked||abstract;$('evaluator-save').disabled=locked||abstract;$('evaluator-test').disabled=locked||abstract||invalid;$('evaluator-agent-input').disabled=!agentActive&&(locked||abstract);$('evaluator-agent-settings-toggle').disabled=locked||agentActive;renderEvaluatorAgentControl();renderWorkflowNextControls()}
function evaluatorAgentControlState(){
  const state=session?.state||'idle',interaction=session?.evaluator_interaction_state||'idle',active=ACTIVE_INTERACTION_STATES.has(interaction),safePaused=state==='running'&&session?.interaction_state==='paused',selected=evaluatorChoices().find(item=>item.id===$('evaluator-select').value),canStart=(state==='idle'||safePaused)&&!selected?.abstract;
  return agentComposerControlState({hasInput:Boolean($('evaluator-agent-input').value.trim()),interaction,startAction:canStart?'message':null,canMessage:active,canControl:active});
}
function renderEvaluatorAgentControl(){
  if(!$('evaluator-agent-send'))return;const button=$('evaluator-agent-send'),control=evaluatorAgentControlState(),running=control.interaction==='running',stopping=['pausing','interrupting'].includes(control.interaction);
  renderAgentComposerButton(button,control,{sendLabel:_('evaluatorAgentSend'),pauseLabel:_('evaluatorAgentStop'),stoppingLabel:_('evaluatorAgentStopping')});
  const status=$('evaluator-agent-state');if(status)status.textContent=_(stopping?'evaluatorAgentStopping':running?'evaluatorAgentWorking':session?.evaluator_agent_state==='stopped'?'evaluatorAgentStopped':'dataAgentReady');renderIconAction($('evaluator-save'),_('evaluatorSave'),'save');
}
function applyEvaluatorAgentResult(){
  const result=session?.evaluator_agent_result;if(!result)return;const signature=JSON.stringify(result);if(signature===evaluatorResultSignature)return;evaluatorResultSignature=signature;
  if(result.source)loadEvaluatorConfiguration(result.custom_file).catch(notice)
  $('evaluator-status').textContent=_(result.status==='stopped'?'evaluatorAgentStopped':result.status==='failed'?'eventModelError':'evaluatorSaved');renderEvaluatorAvailability();
}
function renderEvaluatorArgs(){if(!$('evaluator-args-grid'))return;const settings=effectiveSettings(),entries=[['validation_fraction','evaluatorValidationFraction','number',{min:'0',max:'0.999999',step:'0.05'}],['split_random_state','evaluatorSplitRandomState','number',{}],['split_by','evaluatorSplitBy','select',['random','ood']],['split_ood_variable','evaluatorSplitOodVariable','text',{}],['ranking_metric','evaluatorRankingMetric','text',{}],['larger_is_better','evaluatorLargerIsBetter','checkbox',{}]];$('evaluator-args-title').textContent=_('evaluatorArgsTitle');$('evaluator-args-grid').replaceChildren(...entries.map(([name,helpKey,type,options])=>{const row=document.createElement('label'),copy=el('span',undefined,'evaluator-arg-copy'),control=type==='select'?document.createElement('select'):document.createElement('input'),value=settings[name];row.className='evaluator-arg';copy.append(el('b',name),el('small',_(helpKey)));control.id='evaluator-arg-'+name.replaceAll('_','-');if(type==='select'){control.replaceChildren(...options.map(option=>Object.assign(el('option',option),{value:option})));control.value=value||'random'}else{control.type=type;if(type==='checkbox')control.checked=Boolean(value);else{control.value=value??'';for(const [key,setting] of Object.entries(options))control.setAttribute(key,setting)}}row.append(copy,control);return row}))}
function evaluatorArgsPayload(){return{validation_fraction:Number($('evaluator-arg-validation-fraction').value),split_random_state:Number($('evaluator-arg-split-random-state').value),split_by:$('evaluator-arg-split-by').value,split_ood_variable:$('evaluator-arg-split-ood-variable').value.trim()||null,ranking_metric:$('evaluator-arg-ranking-metric').value.trim(),larger_is_better:$('evaluator-arg-larger-is-better').checked}}
async function applyEvaluatorArgs(){const result=await api('/api/session/settings',evaluatorArgsPayload());syncSession(result);setEvaluatorArgsOpen(false);notice(_('settingsSaved'))}
function setEvaluatorArgsOpen(open){$('evaluator-args-panel').hidden=!open;$('evaluator-args-toggle').setAttribute('aria-expanded',String(open));if(open)renderEvaluatorArgs()}
async function ensureEvaluatorCapabilities(){if(!evaluatorCapabilities)evaluatorCapabilities=await api('/api/session/capabilities?agent=evaluator',undefined,'GET');return evaluatorCapabilities}
function updateEvaluatorCapabilityCounts(){for(const [hostId,countId] of [['evaluator-agent-tool-options','evaluator-agent-tools-count'],['evaluator-agent-skill-options','evaluator-agent-skills-count']]){const inputs=[...$(hostId).querySelectorAll('input[type=checkbox]')];$(countId).textContent=_('selectedCount',{selected:inputs.filter(input=>input.checked).length,total:inputs.length})}}
function selectEvaluatorAgentSettingsTab(name){for(const button of document.querySelectorAll('[data-evaluator-agent-settings-tab]'))button.classList.toggle('active',button.dataset.evaluatorAgentSettingsTab===name);for(const pane of document.querySelectorAll('[data-evaluator-agent-settings-pane]')){const active=pane.dataset.evaluatorAgentSettingsPane===name;pane.classList.toggle('active',active);pane.hidden=!active}}
function renderEvaluatorLanguage(){if(!$('evaluator-config-card'))return;updateDocumentationLinks();for(const [id,key] of [['evaluator-title','evaluatorTitle'],['evaluator-help','evaluatorHelp'],['evaluator-test','evaluatorTest'],['evaluator-save','evaluatorSave'],['evaluator-args-toggle-label','evaluatorArgs'],['evaluator-args-cancel','settingsCancel'],['evaluator-args-apply','apply'],['evaluator-agent-title','evaluatorAgentTitle'],['evaluator-agent-safety','dataAgentSafety'],['evaluator-agent-note','evaluatorAgentNote'],['evaluator-agent-settings-toggle-label','settingsToggle'],['evaluator-agent-provider-label','dataAgentProvider'],['evaluator-agent-model-label','dataAgentModel'],['evaluator-agent-proxy-label','dataAgentProxy'],['evaluator-agent-tool-parser-label','toolParser'],['evaluator-agent-max-tokens-label','maxTokens'],['evaluator-agent-tools-title','availableTools'],['evaluator-agent-skills-title','availableSkills'],['evaluator-agent-settings-hint','dataAgentSettingsHint'],['evaluator-agent-model-test','dataAgentModelTest'],['evaluator-agent-settings-cancel','settingsCancel'],['evaluator-agent-settings-apply','apply']])$(id).textContent=_(key);for(const button of document.querySelectorAll('[data-evaluator-agent-settings-tab]'))button.textContent=_(button.dataset.evaluatorAgentSettingsTab==='model'?'modelSettings':'capabilitySettings');$('evaluator-guide').title=_('evaluatorGuide');$('evaluator-guide').setAttribute('aria-label',_('evaluatorGuide'));$('evaluator-agent-settings-toggle').title=_('settingsToggle');$('evaluator-agent-max-steps-label').textContent=currentLocale==='en'?'Maximum interaction steps':'最大交互轮数';$('evaluator-agent-input').placeholder=_('evaluatorAgentPlaceholder');$('evaluator-agent-proxy').placeholder=_('dataAgentProxyPlaceholder');renderEvaluatorAgentApiKeyVisibility();updateEvaluatorCapabilityCounts();if(!$('evaluator-args-panel').hidden)renderEvaluatorArgs();if(evaluatorConfiguration){const selected=$('evaluator-select').value;$('evaluator-select').replaceChildren(...evaluatorChoices().map(item=>{const option=el('option',(item.invalid?'⚠ ':'')+(currentLocale==='en'?item.label_en:item.label));option.value=item.id;option.className=item.invalid?'evaluator-option-invalid':'';option.title=item.error||'';return option}));$('evaluator-select').value=selected||evaluatorConfiguration.selected}renderEvaluatorAgentControl()}
async function loadEvaluatorConfiguration(preferredFile=null){evaluatorConfiguration=await api('/api/evaluator',undefined,'GET');renderEvaluatorLanguage();const preferred=preferredFile&&evaluatorChoices().find(item=>item.file===preferredFile),selected=preferred?.id||evaluatorConfiguration.selected,item=evaluatorChoices().find(entry=>entry.id===selected);$('evaluator-select').value=selected;$('evaluator-code').value=item?.source||evaluatorConfiguration.source;evaluatorDirty=Boolean(preferred&&selected!==evaluatorConfiguration.selected);renderEvaluatorLineNumbers();renderEvaluatorAvailability();renderEvaluatorSelectionStatus(item)}
function evaluatorPayload(){return{selected:$('evaluator-select').value,source:$('evaluator-code').value}}
async function saveEvaluatorConfiguration(){const status=$('evaluator-status');status.className='evaluator-editor-status';try{const result=await api('/api/evaluator',evaluatorPayload(),'PUT');evaluatorConfiguration={...evaluatorConfiguration,...result};evaluatorDirty=false;status.classList.add('passed');status.textContent=_('evaluatorSaved');renderEvaluatorLanguage();$('evaluator-select').value=result.selected;renderWorkflowNextControls();return result}catch(error){status.classList.add('failed');status.textContent=error?.message||String(error);throw error}}
async function testEvaluatorConfiguration(){const button=$('evaluator-test'),status=$('evaluator-status');button.disabled=true;status.className='evaluator-editor-status';status.textContent=_('evaluatorTesting');try{const result=await api('/api/evaluator/test',evaluatorPayload());const metrics=result.result?.data_split_results?.train?.metrics||{};status.classList.add('passed');status.textContent=_('evaluatorTestPassed')+' · '+Object.entries(metrics).filter(([key])=>['mse','r2','complexity'].includes(key)).map(([key,value])=>key+'='+(typeof value==='number'&&Number.isFinite(value)?Number(value.toPrecision(4)):String(value))).join(' · ')}catch(error){status.classList.add('failed');status.textContent=error?.message||String(error)}finally{button.disabled=false}}
function evaluatorAgentSettingsPayload(){return{llm_provider:$('evaluator-agent-provider').value,llm_model:$('evaluator-agent-model').value.trim(),proxy:$('evaluator-agent-proxy').value.trim(),tool_parser:$('evaluator-agent-tool-parser').value,llm_max_tokens:optionalTokenLimit('evaluator-agent-max-tokens'),max_steps:Number($('evaluator-agent-max-steps').value),tools:selectedCapabilityNames('evaluator-agent-tool-options'),skills:selectedCapabilityNames('evaluator-agent-skill-options')}}
function renderEvaluatorAgentApiKeyVisibility(){if(!$('evaluator-agent-api-key'))return;const input=$('evaluator-agent-api-key'),visible=input.type==='text',label=_(visible?'apiKeyHide':'apiKeyShow'),button=$('evaluator-agent-api-key-visibility');button.innerHTML='<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M2.2 10s2.8-5 7.8-5 7.8 5 7.8 5-2.8 5-7.8 5-7.8-5-7.8-5Z"/><circle cx="10" cy="10" r="2.2"/><path class="visibility-slash" d="m4 4 12 12"/></svg>';button.classList.toggle('is-visible',visible);button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(visible))}
async function refreshEvaluatorAgentCredential(){const provider=$('evaluator-agent-provider').value,input=$('evaluator-agent-api-key'),credential=await api('/api/session/provider-credential?provider='+encodeURIComponent(provider),undefined,'GET'),env=credential.env_var,link=document.createElement('a');link.href=DATA_PROVIDER_API_KEY_URLS[provider]||'#';link.target='_blank';link.rel='noopener';link.textContent=_('apiKeyGet',{env});$('evaluator-agent-api-key-label').replaceChildren('API Key (',link,')');input.placeholder=credential.configured?_('apiKeyConfigured'):_('apiKeyPlaceholder',{env})}
async function saveEvaluatorAgentCredential(){const input=$('evaluator-agent-api-key'),apiKey=input.value.trim();if(!apiKey)return null;const result=await api('/api/session/provider-credential',{provider:$('evaluator-agent-provider').value,api_key:apiKey},'PUT');input.value='';input.type='password';renderEvaluatorAgentApiKeyVisibility();await refreshEvaluatorAgentCredential();return result}
async function syncEvaluatorAgentSettingsForm(){const available=await ensureEvaluatorCapabilities(),settings=session?.evaluator_agent_settings||{};$('evaluator-agent-provider').value=settings.llm_provider||'openrouter';$('evaluator-agent-model').value=settings.llm_model||'';$('evaluator-agent-proxy').value=settings.proxy||'';$('evaluator-agent-tool-parser').value=settings.tool_parser||'openai';$('evaluator-agent-max-tokens').value=settings.llm_max_tokens??'';$('evaluator-agent-max-steps').value=settings.max_steps??64;renderCapabilityOptions('evaluator-agent-tool-options',available.tools,settings.tools??available.default_tools,updateEvaluatorCapabilityCounts);renderCapabilityOptions('evaluator-agent-skill-options',available.skills,settings.skills??available.default_skills,updateEvaluatorCapabilityCounts);updateEvaluatorCapabilityCounts();await refreshEvaluatorAgentCredential()}
async function setEvaluatorAgentSettingsOpen(open){$('evaluator-agent-settings').hidden=!open;$('evaluator-agent-settings-toggle').setAttribute('aria-expanded',String(open));if(open)await syncEvaluatorAgentSettingsForm()}
async function applyEvaluatorAgentSettings(){const queued=agentSettingsQueued(session?.evaluator_interaction_state),credential=await saveEvaluatorAgentCredential();syncSession(await api('/api/evaluator/agent/settings',evaluatorAgentSettingsPayload(),'PUT'));await setEvaluatorAgentSettingsOpen(false);notice(credential?_('apiKeySaved',{env:credential.env_var}):_(queued?'settingsQueued':'settingsSaved'))}
async function testEvaluatorAgentModel(){const button=$('evaluator-agent-model-test'),status=$('evaluator-agent-model-test-status');button.disabled=true;status.className='model-test-status';status.textContent=_('dataAgentModelTesting');try{await saveEvaluatorAgentCredential();const result=await api('/api/evaluator/agent/test',evaluatorAgentSettingsPayload());status.classList.add(result.ok?'passed':'failed');status.textContent=_(result.ok?'dataAgentModelTestPassed':result.accessible?'dataAgentModelTestPartial':'dataAgentModelTestUnavailable')}catch(error){status.classList.add('failed');status.textContent=error?.message||String(error)}finally{button.disabled=false}}
function appendEvaluatorAgentEvent(kind,payload,timestamp=Date.now()/1000){const feed=$('evaluator-agent-feed'),failed=kind==='tool_error',resultFailed=payload.result?.ok===false,card=el('article',undefined,'event '+(kind==='user'?'data_user':kind==='assistant'?'assistant':failed?'tool_error':'tool_result')),meta=el('div',undefined,'meta'),time=el('span',new Date(Number(timestamp)*1000).toLocaleTimeString(currentLocale),'meta-time');if(kind==='user'){meta.append(eventBadge('user',_('eventUser')),time);card.append(meta);previewBlock(card,payload.content||'','message-preview-block')}else if(kind==='assistant'){meta.append(eventBadge('agent',_('eventAgent')));const badge=modelBadge(payload.provider,payload.model);if(badge)meta.append(badge);meta.append(time);card.append(meta);reasoningBlock(card,payload.reasoning||payload.message?.reasoning||'');if(payload.content)previewBlock(card,payload.content,'message-preview-block',true);toolCallsBlock(card,payload.tool_calls)}else{meta.append(eventBadge('tool',_(failed?'eventToolError':'eventTool'),failed||resultFailed),el('span',payload.call?.name||payload.tool||'Tool','tool-event-name'),el('span',_(failed?'toolFailed':'toolReturned'),'tool-state'+(failed?' failed':'')),time);card.append(meta,el('div',_('callParameters'),'tool-caption'));const parameters=toolParameters(payload.call?.params||{},undefined,true);parameters.classList.add('tool-event-params');card.append(parameters,el('div',_(failed?'errorInfo':'result'),'tool-caption'));previewBlock(card,payload.result?.result_str||_('toolNoText'),'tool-result-block');if(payload.result?.result!==undefined){const raw=el('details',undefined,'raw-json tool-result-raw');raw.append(el('summary',_('rawJson')),el('pre',pretty(payload.result.result)));card.append(raw)}}feed.hidden=false;feed.append(card);feed.scrollTop=feed.scrollHeight}
async function runEvaluatorAgent(){
  const control=evaluatorAgentControlState();
  if(control.action==='message')return sendAgentComposerMessage({input:$('evaluator-agent-input'),button:$('evaluator-agent-send'),request:message=>api('/api/evaluator/agent/start',{message,source:$('evaluator-code').value}),render:renderEvaluatorAgentControl,beforeRequest:()=>$('evaluator-status').textContent=_('evaluatorAgentWorking')});
  if(control.action){const result=await api('/api/evaluator/agent/stop',{});syncSession(result);if(result.cancellation_error)notice(result.cancellation_error)}
}
function describe(element,description){
  if(description){element.classList.add('has-description');element.dataset.description=description;element.tabIndex=0;element.setAttribute('aria-label',`${element.textContent}：${description}`)}
  return element;
}
const eventIconPaths={
  agent:'<path d="M8 2.2c.35 3.35 1.55 4.55 4.9 4.9-3.35.35-4.55 1.55-4.9 4.9-.35-3.35-1.55-4.55-4.9-4.9C6.45 6.75 7.65 5.55 8 2.2Z" fill="currentColor"/><circle cx="12.6" cy="3.3" r="1" fill="currentColor"/><circle cx="3.4" cy="12.7" r=".8" fill="currentColor"/>',
  tool:'<path d="M9.8 3.1a3.15 3.15 0 0 0-3.65 4.05L2.8 10.5a1.55 1.55 0 0 0 2.2 2.2l3.35-3.35A3.15 3.15 0 0 0 12.4 5.7L10.5 7.6 8.4 5.5l1.4-2.4Z" fill="currentColor"/>',
  context:'<path d="m2.5 5 5.5-3 5.5 3L8 8 2.5 5Zm0 3L8 11l5.5-3M2.5 11 8 14l5.5-3" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round"/>',
  user:'<circle cx="8" cy="5" r="2.25" fill="currentColor"/><path d="M3.5 13c.45-2.85 2.1-4.25 4.5-4.25s4.05 1.4 4.5 4.25" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  question:'<path d="M5.7 5.7A2.35 2.35 0 1 1 8.6 8c-.65.25-.85.65-.85 1.35M7.75 12.25h.01" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  reply:'<path d="M13 4.2H6.7a3.7 3.7 0 0 0 0 7.4H9M5.1 8.6 2.5 11l2.6 2.4" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>',
  'user-control':'<path d="M3.5 2.5 12 8.2l-3.5.65 1.9 3.05-2 1.2-1.85-3.05-2.15 2.7-.9-10.25Z" fill="currentColor"/>',
  run:'<path d="m5 3.5 7 4.5-7 4.5v-9Z" fill="currentColor"/>',
  settings:'<path d="M3 4.5h5m2 0h3M3 8h2m2 0h6M3 11.5h6m2 0h2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="9" cy="4.5" r="1" fill="currentColor"/><circle cx="6" cy="8" r="1" fill="currentColor"/><circle cx="10" cy="11.5" r="1" fill="currentColor"/>',
  file:'<path d="M8 2.5v7m-2.5-2L8 10l2.5-2.5M3 12v1.5h10V12" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round"/>',
  event:'<circle cx="8" cy="8" r="3" fill="currentColor"/>'
};
function eventBadge(key,label,error=false){
  const badge=el('span',undefined,'event-kind event-kind-'+key+(error?' event-kind-error':'')),svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 16 16');svg.setAttribute('aria-hidden','true');svg.innerHTML=eventIconPaths[key]||eventIconPaths.event;badge.append(svg);badge.dataset.label=label;badge.tabIndex=0;badge.setAttribute('aria-label',label);return badge;
}
const MODEL_BRANDS=[
  {key:'deepseek',name:'DeepSeek',pattern:/deepseek/i},
  {key:'zhipu',name:'Zhipu AI',pattern:/(^|[\/_.-])(?:chat)?glm(?:[\/_.-]|$)|zhipu|z\.ai/i},
  {key:'openai',name:'OpenAI',pattern:/(^|[\/_.-])(?:gpt|chatgpt|codex|o[134])(?:[\/_.-]|$)|openai/i},
  {key:'gemini',name:'Google Gemini',pattern:/gemini/i},
  {key:'anthropic',name:'Anthropic',pattern:/claude|anthropic/i},
  {key:'qwen',name:'Qwen',pattern:/qwen|tongyi/i},
  {key:'meta',name:'Meta',pattern:/(^|[\/_.-])llama(?:[\/_.-]|$)|meta-llama/i},
  {key:'mistral',name:'Mistral AI',pattern:/mistral|mixtral/i},
  {key:'kimi',name:'Moonshot AI',pattern:/moonshot|kimi/i},
  {key:'minimax',name:'MiniMax',pattern:/minimax/i}
];
const PROVIDER_BRANDS={openrouter:{key:'openrouter',name:'OpenRouter'},openai:{key:'openai',name:'OpenAI'},deepseek:{key:'deepseek',name:'DeepSeek'},gemini:{key:'gemini',name:'Google Gemini'},siliconflow:{key:'siliconflow',name:'SiliconFlow'},lmstudio:{key:'lmstudio',name:'LM Studio'}};
function modelBrand(provider,model){const identity=String(model||'');return MODEL_BRANDS.find(brand=>brand.pattern.test(identity))||PROVIDER_BRANDS[String(provider||'').toLowerCase()]||{key:'generic',name:String(provider||'AI')}}
function modelBadge(provider,model){if(!provider&&!model)return null;const brand=modelBrand(provider,model),badge=el('span',undefined,'model-logo model-logo-'+brand.key),label='Provider: '+(provider||'—')+'\nModel: '+(model||'—');badge.dataset.label=label;badge.title=label.replace('\n',' · ');badge.tabIndex=0;badge.setAttribute('aria-label',label.replace('\n',', '));if(brand.key==='generic'){badge.textContent=(brand.name||'AI').slice(0,2).toUpperCase()}else{const image=document.createElement('img');image.src='/static/brands/'+brand.key+(brand.key==='siliconflow'?'.png':'.svg');image.alt=brand.name;image.onerror=()=>{image.remove();badge.textContent=(brand.name||'AI').slice(0,2).toUpperCase()};badge.append(image)}return badge}
function eventKind(kind,resultFailed=false){
  const isTool=kind.startsWith('tool_'),key=isTool?'tool':({user:'user',assistant:'agent',context:'context',question:'question',reply:'reply',control:'user-control',lifecycle:'run',settings_applied:'settings',settings_error:'settings',file_uploaded:'file'}[kind]||'event');
  const label=isTool?_(kind==='tool_error'?'eventToolError':'eventTool'):({user:_('eventUser'),assistant:_('eventAgent'),context:_('eventContext'),question:_('eventQuestion'),reply:_('eventReply'),control:_('eventControl'),lifecycle:_('eventRun'),settings_applied:_('eventModelUpdated'),settings_error:_('eventModelError'),file_uploaded:_('eventWorkspace')}[kind]||kind);
  return eventBadge(key,label,kind==='tool_error'||kind==='settings_error'||resultFailed);
}
function renderPromptAdded(e,feed,scope='search'){
  const message=e.payload?.message||{},role=message.role||'user',card=el('article',undefined,'event '+(role==='system'?'system_prompt':'data_user'));card.dataset.started=e.timestamp;
  const meta=el('div',undefined,'meta'),label=role==='system'?_('systemPrompt'):_('eventUser');meta.append(eventBadge(role==='system'?'settings':'user',label),el('span',new Date(Number(e.timestamp)*1000).toLocaleTimeString(currentLocale),'meta-time'));card.append(meta);previewBlock(card,message.content||'','message-preview-block');
  const next=[...feed.querySelectorAll(':scope > .event')].find(item=>Number(item.dataset.started)>Number(e.timestamp));feed.insertBefore(card,next||null);feed.hidden=false;
}
function interactionStateLabel(state){return _({idle:'interactionIdle',running:'interactionRunning',pausing:'interactionPausing',interrupting:'interactionInterrupting',paused:'interactionPaused'}[state]||state)}
function compactEventContent(e){const p=e.payload||{};if(e.kind==='search_position_changed')return ['R'+p.R,'C'+p.C,'L'+p.L].join(' · ');if(e.kind==='topk_updated')return _('eventTopkUpdated',{count:Array.isArray(p.records)?p.records.length:0});if(e.kind==='state_changed')return _('interactionStateChanged',{previous:interactionStateLabel(p.previous),current:interactionStateLabel(p.current)});if(e.kind==='command_received')return p.error||{pause:_('safeStopNotice'),force_pause:_('forceStopNotice')}[p.action]||p.action;return p.message||p.error||p}
function eventContent(card,meta,metaTime,value){const text=typeof value==='string'?value.trim():pretty(value);if(text&&!text.includes('\n')&&text.length<=160){card.classList.add('compact-event');metaTime.before(el('span',text,'meta-event-text'));return}previewBlock(card,value,'message-preview-block')}
function renderGenericEventCard(e,feed){const card=el('article',undefined,'event '+e.kind);card.dataset.started=e.timestamp;const meta=el('div',undefined,'meta'),stateChanged=e.kind==='state_changed',metaTime=el('span',new Date(Number(e.timestamp)*1000).toLocaleTimeString(currentLocale),'meta-time');meta.append(eventBadge(stateChanged?'run':'event',stateChanged?_('eventRun'):e.kind),metaTime);card.append(meta);eventContent(card,meta,metaTime,compactEventContent(e));feed.append(card);feed.hidden=false}
function scopedTimelineEvent(e,prefix=''){
  const names={context:'context',assistant_started:'assistant_start',assistant_delta:'assistant_delta',assistant_completed:'assistant',assistant_failed:'assistant_error',tool_started:'tool_start',tool_completed:'tool_result',execution_completed:'complete',execution_failed:'error'};
  const name=names[e.kind];return name?{...e,kind:prefix?prefix+'_'+name:name}:e;
}
async function responseError(response,fallback='Request failed'){
  const text=await response.text();if(!text)return fallback;
  try{const body=JSON.parse(text);return body.detail||body.message||text}catch{return text}
}
function conversationHeaders(headers={}){return selectedConversationId?{...headers,'X-SR-Harness-Conversation':selectedConversationId}:headers}
async function api(url,data,method='POST') {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try {
    const headers=conversationHeaders(data===undefined?{}:{'Content-Type':'application/json'});
    const options={signal:controller.signal,headers,...(data===undefined?{}:{method,body:JSON.stringify(data)})};
    let response=await fetch(url,options);
    // The server rejects excess work before execution; honor its retry delay on startup bursts.
    for(let retry=0;response.status===429&&retry<2;retry++){
      const delay=Number(response.headers.get('Retry-After'));
      if(!Number.isFinite(delay)||delay<=0||delay>3)break;
      await new Promise(resolve=>setTimeout(resolve,delay*1000));
      response=await fetch(url,options);
    }
    if(!response.ok)throw Error(await responseError(response));
    return await response.json();
  } catch(error) {if(error.name==='AbortError')throw Error(_('requestTimeout'));throw error} finally {clearTimeout(timer)}
}

const CONVERSATION_STORAGE_KEY='sr-harness-conversation';
let selectedConversationId=sessionStorage.getItem(CONVERSATION_STORAGE_KEY)||'',conversationState=null,conversationReady=Promise.resolve(),workspacePanelName='workspace';
function setConversationSelection(conversationId){selectedConversationId=String(conversationId||'');if(selectedConversationId)sessionStorage.setItem(CONVERSATION_STORAGE_KEY,selectedConversationId);else sessionStorage.removeItem(CONVERSATION_STORAGE_KEY)}
function conversationUrl(url,conversationId=selectedConversationId){if(!conversationId)return url;const value=new URL(url,location.origin);value.searchParams.set('conversation',conversationId);return value.pathname+value.search+value.hash}
function renderConversationLanguage(){
  const pairs=[['conversations-panel-tab','conversations'],['workspace-panel-tab','workspacePanel']];for(const [id,key] of pairs)if($(id))$(id).textContent=_(key);
  for(const [id,key] of [['new-conversation','newConversation'],['refresh-conversations','refreshConversations']]){const button=$(id);if(!button)continue;const label=_(key);button.title=label;button.setAttribute('aria-label',label)}
  if($('conversation-title')){$('conversation-title').title=_('renameConversation');$('conversation-title').setAttribute('aria-label',_('renameConversation'))}
  if($('conversation-title-input'))$('conversation-title-input').placeholder=_('conversationNamePlaceholder');renderConversationList();
}
function updateConversation(item,updated){Object.assign(item,updated);if(item.id===conversationState.selected&&$('conversation-title'))$('conversation-title').textContent=item.name}
async function loadAppVersion(){const result=await api('/api/version');$('app-version').textContent='v'+result.version;$('app-version').title='ASTRAL '+result.version}
function beginConversationListRename(item,row,button){
  const form=el('form',undefined,'conversation-inline-editor'),input=el('input');input.value=item.name;input.placeholder=_('conversationNamePlaceholder');input.setAttribute('aria-label',_('renameConversation'));form.append(input);button.hidden=true;row.insertBefore(form,row.querySelector('.conversation-item-actions'));
  let saving=false;const close=()=>{form.remove();button.hidden=false},save=async()=>{if(saving)return;saving=true;const name=input.value.trim();if(!name||name===item.name){close();return}try{const updated=await api('/api/conversations/'+encodeURIComponent(item.id),{name},'PATCH');updateConversation(item,updated);renderConversationList()}catch(error){close();notice(error)}};
  form.onsubmit=event=>{event.preventDefault();input.blur()};input.onblur=save;input.onkeydown=event=>{if(event.key==='Escape'){event.preventDefault();input.onblur=null;close()}};requestAnimationFrame(()=>{input.focus();input.select()});
}
function renderConversationList(){
  const host=$('conversations');if(!host||!conversationState)return;host.replaceChildren();const readOnly=Boolean(conversationState.read_only),items=[...(conversationState.conversations||[])].sort((a,b)=>String(b.updated_at).localeCompare(String(a.updated_at)));
  if(!items.length){host.append(el('p',_('conversationEmpty'),'conversation-empty'));return}
  for(const item of items){
    const active=item.id===conversationState.selected,row=el('div',undefined,'conversation-row'+(active?' active':'')),button=el('button',undefined,'conversation-item'+(active?' active':'')),icon=el('span','◌','conversation-item-icon'),copy=el('span',undefined,'conversation-item-copy'),name=el('span',item.name,'conversation-item-name'),time=el('span',new Date(item.updated_at).toLocaleString(currentLocale,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}),'conversation-item-time'),actions=el('details',undefined,'conversation-item-actions'),summary=el('summary','⋯'),menu=el('div',undefined,'conversation-item-menu'),exportLink=el('a',_('exportConversation')),rename=el('button',_('renameConversation')),archive=el('button',_('archiveConversation'),'conversation-archive-action');
    button.type='button';button.dataset.conversationId=item.id;button.setAttribute('aria-current',active?'page':'false');copy.append(name,time);button.append(icon,copy);button.onclick=guard(async()=>{if(active)return;const result=await api('/api/conversations/'+encodeURIComponent(item.id)+'/select',{});setConversationSelection(result.selected);location.reload()});summary.title=_('conversationMore');summary.setAttribute('aria-label',_('conversationMore'));actions.ontoggle=()=>{if(actions.open)for(const other of document.querySelectorAll('.conversation-item-actions[open]'))if(other!==actions)other.open=false};exportLink.href=conversationUrl('/api/conversations/'+encodeURIComponent(item.id)+'/export',item.id);exportLink.download='conversation-'+item.id+'.zip';exportLink.onclick=event=>{event.stopPropagation();actions.open=false};rename.type='button';rename.onclick=event=>{event.stopPropagation();actions.open=false;beginConversationListRename(item,row,button)};archive.type='button';archive.onclick=guard(async event=>{event.stopPropagation();actions.open=false;const result=await api('/api/conversations/'+encodeURIComponent(item.id),{},'DELETE');if(active||result.selected!==conversationState.selected){setConversationSelection(result.selected);location.reload();return}conversationState.conversations=conversationState.conversations.filter(entry=>entry.id!==item.id);renderConversationList()});menu.append(exportLink);if(!readOnly)menu.append(rename,archive);actions.append(summary,menu);row.append(button,actions);host.append(row);
  }
  const selected=items.find(item=>item.id===conversationState.selected);if(selected&&$('conversation-title'))$('conversation-title').textContent=selected.name;
}
async function loadConversations(){const requestedSelection=selectedConversationId,response=await api('/api/conversations',undefined,'GET');if(selectedConversationId!==requestedSelection)return conversationState;conversationState=response;setConversationSelection(response.selected);if(conversationState.read_only){$('new-conversation').hidden=true;$('conversation-title').disabled=true;$('conversation-title').title='Read-only'}renderConversationList();return conversationState}
let readOnlyConversationRefreshPending=false;
setInterval(async()=>{
  if(!conversationState?.read_only||document.hidden||readOnlyConversationRefreshPending)return;
  readOnlyConversationRefreshPending=true;
  try{await loadConversations()}catch(error){console.warn('Conversation refresh failed',error)}
  finally{readOnlyConversationRefreshPending=false}
},30000);
function setWorkspacePanel(name){workspacePanelName=name;const conversations=name==='conversations';$('conversations').hidden=!conversations;$('files').hidden=conversations;$('drop').hidden=conversations;$('workspace-name-editor').hidden=true;document.querySelector('#workspace>.bar>.workspace-actions:not(.conversation-actions)').hidden=conversations;$('conversation-actions').hidden=!conversations;$('conversations-panel-tab').classList.toggle('active',conversations);$('workspace-panel-tab').classList.toggle('active',!conversations);if(conversations)loadConversations().catch(notice)}
function mountConversationUI(){
  const workspace=$('workspace'),bar=workspace.querySelector(':scope>.bar'),existingActions=bar.querySelector('.workspace-actions'),tabs=el('div',undefined,'workspace-panel-tabs'),conversationTab=el('button',undefined),workspaceTab=el('button',undefined),conversationActions=el('div',undefined,'workspace-actions conversation-actions'),createButton=el('button',undefined,'icon-button'),refreshButton=el('button',undefined,'icon-button'),list=el('div',undefined,'conversation-list');
  conversationTab.id='conversations-panel-tab';conversationTab.type='button';workspaceTab.id='workspace-panel-tab';workspaceTab.type='button';workspaceTab.classList.add('active');tabs.append(conversationTab,workspaceTab);$('workspace-title').replaceWith(tabs);conversationActions.id='conversation-actions';conversationActions.hidden=true;createButton.id='new-conversation';createButton.type='button';createButton.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 3.5h11v8h-6l-3 2v-2h-2zM8 5.5v4M6 7.5h4"/></svg>';refreshButton.id='refresh-conversations';refreshButton.type='button';refreshButton.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M12.7 6.2A5 5 0 1 0 13 9M12.7 3.5v2.8H9.9"/></svg>';conversationActions.append(createButton,refreshButton);existingActions.before(conversationActions);list.id='conversations';list.hidden=true;bar.after(list);
  const title=el('button','…','conversation-title'),editor=el('form',undefined,'conversation-title-editor'),input=el('input');title.id='conversation-title';title.type='button';editor.id='conversation-title-editor';editor.hidden=true;input.id='conversation-title-input';editor.append(input);document.querySelector('header .brand').after(title,editor);
  let titleSaving=false;const saveTitle=async()=>{if(editor.hidden||titleSaving)return;titleSaving=true;const name=input.value.trim(),item=conversationState?.conversations?.find(entry=>entry.id===conversationState.selected);editor.hidden=true;title.hidden=false;if(!item||!name||name===item.name){if(item)title.textContent=item.name;titleSaving=false;return}try{const updated=await api('/api/conversations/'+encodeURIComponent(item.id),{name},'PATCH');updateConversation(item,updated);renderConversationList()}catch(error){title.textContent=item.name;notice(error)}finally{titleSaving=false}};
  conversationTab.onclick=()=>setWorkspacePanel('conversations');workspaceTab.onclick=()=>setWorkspacePanel('workspace');createButton.onclick=guard(async()=>{const created=await api('/api/conversations',{});setConversationSelection(created.id);location.reload()});refreshButton.onclick=guard(loadConversations);title.onclick=()=>{input.value=title.textContent;title.hidden=true;editor.hidden=false;input.focus();input.select()};input.onblur=saveTitle;input.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();input.blur()}else if(event.key==='Escape'){event.preventDefault();const item=conversationState?.conversations?.find(entry=>entry.id===conversationState.selected);input.value=item?.name||title.textContent;input.blur()}};editor.onsubmit=event=>{event.preventDefault();input.blur()};
  renderConversationLanguage();conversationReady=loadConversations().catch(error=>{notice(error);throw error});loadAppVersion().catch(()=>{});
}

let noticeTimer;
function notice(error){const message=error?.message||error||'',host=$('toast-stack');clearTimeout(noticeTimer);host.replaceChildren();if(!message)return;const toast=el('div',undefined,'toast'),text=el('span',message),close=el('button','×');close.type='button';close.title=_('closeNotice');close.onclick=()=>{clearTimeout(noticeTimer);host.replaceChildren()};toast.append(text,close);host.append(toast);requestAnimationFrame(()=>toast.classList.add('show'));noticeTimer=setTimeout(()=>host.replaceChildren(),6000)}
function guard(fn){return async(...args)=>{try{notice('');await fn(...args)}catch(e){notice(e)}}}
function dataNote(message,error=false){if(error)notice(message);else notice('')}
function dataGuard(fn){return async(...args)=>{try{dataNote('');await fn(...args)}catch(error){dataNote(error?.message||error,true)}}}
function appendColumnLabel(host,column){host.append(document.createTextNode(column));if(dataPreview?.columnKinds?.[column]==='axis')host.append(el('span',_('axisKind'),'column-kind'))}
function dataPreviewGroupLabel(group){
  const variables=group.kind==='axis'?group.variables.join(', '):group.variable;
  return `${variables} (axis=${group.axes.join('×')})`;
}
function renderDataNumberFormatControls(){
  const mode=$('data-number-format-mode'),digits=$('data-number-format-digits');$('data-number-format-label').textContent=_('numberFormat');mode.options[0].textContent=_('decimalFormat');mode.options[1].textContent=_('scientificFormat');mode.value=dataNumberFormatMode;digits.value=String(dataNumberFormatDigits);$('data-number-digits-label').textContent=_('decimalPlaces');mode.setAttribute('aria-label',_('numberFormat'));digits.setAttribute('aria-label',_('decimalPlaces'));
  mode.onchange=()=>{dataNumberFormatMode=mode.value;localStorage.setItem('sr-harness-data-number-format',dataNumberFormatMode);renderDataTable()};digits.oninput=()=>{const parsed=Number.parseInt(digits.value,10);if(!Number.isFinite(parsed))return;dataNumberFormatDigits=Math.max(0,Math.min(12,parsed));digits.value=String(dataNumberFormatDigits);localStorage.setItem('sr-harness-data-number-digits',String(dataNumberFormatDigits));renderDataTable()};
}
function renderDataPreviewGroupPicker(){
  const select=$('data-preview-group');select.replaceChildren();$('data-preview-group-label').textContent=_('dataPreviewGroup');select.setAttribute('aria-label',_('dataPreviewGroup'));
  const visibleGroups=plotMode==='structure'?dataPreviewGroups.filter(group=>group.kind==='relation'):dataPreviewGroups;for(const group of visibleGroups){const option=el('option',dataPreviewGroupLabel(group));option.value=group.id;select.append(option)}
  if(!visibleGroups.length){const option=el('option',_(plotMode==='structure'?'structureSelectRelation':'contextDataEmpty'));option.value='';select.append(option);select.disabled=true;selectedDataPreviewGroup=''}else{select.disabled=false;if(!visibleGroups.some(group=>group.id===selectedDataPreviewGroup))selectedDataPreviewGroup=visibleGroups[0].id;select.value=selectedDataPreviewGroup}
  select.onchange=()=>loadDataPreviewGroup(select.value).catch(error=>dataNote(error?.message||error,true));
}
function formatDataPreviewValue(value){if(value===null||value===undefined)return'—';if(typeof value==='number'&&Number.isFinite(value))return dataNumberFormatMode==='scientific'?value.toExponential(dataNumberFormatDigits):value.toFixed(dataNumberFormatDigits);if(typeof value==='object')return JSON.stringify(value);const text=String(value);return text.length>80?text.slice(0,79)+'…':text}
function appendTensorMetadata(host,preview){
  const metadata=el('div',undefined,'tensor-metadata'),axes=el('div',undefined,'tensor-meta-item'),dtype=el('div',undefined,'tensor-meta-item'),range=el('div',undefined,'tensor-meta-item'),samples=el('div',undefined,'tensor-meta-item tensor-samples'),shown=(preview.sample_values||[]).slice(0,4);
  axes.append(el('span',_('tensorAxes')),el('b',preview.shape.map((size,index)=>`${size} (${preview.axes[index]||'?'})`).join(' × ')));dtype.append(el('span',_('previewDtype',{value:''}).trim()),el('b',preview.dtype));range.append(el('span',_('tensorRange')),el('b',preview.value_range?.map(formatDataPreviewValue).join(' – ')||'—'));samples.append(el('span',_('tensorSamples')),el('b',shown.length?shown.map(formatDataPreviewValue).join(', ')+((preview.sample_values?.length||0)>shown.length?' …':''):'—'));metadata.append(axes,dtype,range,samples);host.append(metadata);
}
function renderTensorCube(host,preview){
  const stage=el('div',undefined,'tensor-cube-stage'),svg=svgNode('svg',{viewBox:'0 0 370 220',class:'tensor-cube-svg',role:'img','aria-label':`${preview.variable}: ${preview.shape.join(' × ')}`}),defs=svgNode('defs');
  for(const [id,stops] of [['tensor-top',[['0%','#d8ebe7'],['100%','#9ac8c0']]],['tensor-front',[['0%','#78b9ae'],['100%','#426ca8']]],['tensor-side',[['0%','#4a8e84'],['100%','#306d64']]]]){const gradient=svgNode('linearGradient',{id,x1:'0',y1:'0',x2:'1',y2:'1'});for(const [offset,color] of stops)gradient.append(svgNode('stop',{offset,'stop-color':color}));defs.append(gradient)}svg.append(defs);
  const dimensions=preview.shape.slice(0,3).map(size=>Math.max(1,Number(size)||1)),largest=Math.max(...dimensions),scale=dimensions.map(size=>.3+.7*size/largest),width=165*scale[0],height=110*scale[1],depth=76*scale[2],offsetX=depth*.72,offsetY=-depth*.44,left=(370-width-offsetX)/2,top=38-offsetY,right=left+width,bottom=top+height,backRight=right+offsetX,backTop=top+offsetY;
  const points=values=>values.map(point=>point.join(',')).join(' '),front=[[left,top],[right,top],[right,bottom],[left,bottom]],topFace=[[left,top],[left+offsetX,backTop],[backRight,backTop],[right,top]],side=[[right,top],[backRight,backTop],[backRight,bottom+offsetY],[right,bottom]];
  svg.append(svgNode('polygon',{points:points(topFace),class:'tensor-cube-face tensor-cube-top'}),svgNode('polygon',{points:points(front),class:'tensor-cube-face tensor-cube-front'}),svgNode('polygon',{points:points(side),class:'tensor-cube-face tensor-cube-side'}));
  const grid=[];for(const ratio of [1/3,2/3]){grid.push(`M${left} ${top+height*ratio}H${right}`,`M${left+width*ratio} ${top}V${bottom}`,`M${right} ${top+height*ratio}L${backRight} ${backTop+height*ratio}`,`M${right+offsetX*ratio} ${top+offsetY*ratio}V${bottom+offsetY*ratio}`,`M${left+offsetX*ratio} ${top+offsetY*ratio}H${right+offsetX*ratio}`,`M${left+width*ratio} ${top}L${left+width*ratio+offsetX} ${backTop}`)}svg.append(svgNode('path',{d:grid.join(''),class:'tensor-cube-grid'}));
  const projectedDepth=Math.hypot(offsetX,offsetY),labels=[['top',0,left+width/2,bottom+18],['front',1,left-12,top+height/2],['side',2,left+offsetX/2+offsetY/projectedDepth*30,top+offsetY/2-offsetX/projectedDepth*30]];for(const [kind,index,x,y] of labels){const group=svgNode('g',{class:`tensor-cube-label tensor-cube-label-${kind}`}),axis=svgNode('text',{x,y:y-5,class:'tensor-cube-axis'}),size=svgNode('text',{x,y:y+14,class:'tensor-cube-size'});axis.textContent=preview.axes[index]||'';size.textContent=String(preview.shape[index]??'');group.append(axis,size);svg.append(group)}
  stage.append(svg);host.append(stage);appendTensorMetadata(host,preview);
}
function enableRelationViewport(stage,svg,viewport,width,height){
  let scale=1,translateX=0,translateY=0,drag=null;const minScale=.82,maxScale=5,minimumVisible=54;
  function contentBounds(){try{return viewport.getBBox()}catch{return{x:20,y:20,width:width-40,height:height-40}}}
  function clampView(){const box=contentBounds(),minimumX=minimumVisible-(box.x+box.width)*scale,maximumX=width-minimumVisible-box.x*scale,minimumY=minimumVisible-(box.y+box.height)*scale,maximumY=height-minimumVisible-box.y*scale;translateX=Math.max(Math.min(translateX,Math.max(minimumX,maximumX)),Math.min(minimumX,maximumX));translateY=Math.max(Math.min(translateY,Math.max(minimumY,maximumY)),Math.min(minimumY,maximumY))}
  function applyView(){clampView();viewport.setAttribute('transform',`translate(${translateX} ${translateY}) scale(${scale})`)}
  function svgPoint(event){const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;return point.matrixTransform(svg.getScreenCTM().inverse())}
  stage.addEventListener('wheel',event=>{event.preventDefault();const point=svgPoint(event),next=Math.max(minScale,Math.min(maxScale,scale*Math.exp(-event.deltaY*.0015))),ratio=next/scale;translateX=point.x-(point.x-translateX)*ratio;translateY=point.y-(point.y-translateY)*ratio;scale=next;applyView()},{passive:false});
  stage.addEventListener('pointerdown',event=>{if(event.button!==0)return;drag={pointerId:event.pointerId,point:svgPoint(event)};stage.setPointerCapture(event.pointerId);stage.classList.add('dragging')});
  stage.addEventListener('pointermove',event=>{if(!drag||drag.pointerId!==event.pointerId)return;const point=svgPoint(event);translateX+=point.x-drag.point.x;translateY+=point.y-drag.point.y;drag.point=point;applyView()});
  function endDrag(event){if(!drag||drag.pointerId!==event.pointerId)return;drag=null;stage.classList.remove('dragging');if(stage.hasPointerCapture(event.pointerId))stage.releasePointerCapture(event.pointerId)}
  stage.addEventListener('pointerup',endDrag);stage.addEventListener('pointercancel',endDrag);stage.addEventListener('dblclick',()=>{scale=1;translateX=0;translateY=0;applyView()});applyView();
}
function renderRelationGraph(host,preview){
  const width=640,height=390,nodeRadius=11,stage=el('div',undefined,'relation-preview-stage'),svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':preview.endpoint_count===3?_('hypergraphPreview'):_('graphPreview')}),defs=svgNode('defs'),marker=svgNode('marker',{id:'relation-arrow',viewBox:'0 0 8 8',refX:'7',refY:'4',markerWidth:'6',markerHeight:'6',orient:'auto-start-reverse'}),viewport=svgNode('g',{class:'relation-viewport'});marker.append(svgNode('path',{d:'M0 0L8 4L0 8Z',fill:'#426ca8'}));defs.append(marker);svg.append(defs,viewport);
  const nodes=preview.nodes||[],coordinates=preview.coordinates||[],positions=new Map(),centerX=width/2,centerY=height/2-3,radius=Math.min(width,height)*.38;
  nodes.forEach((node,index)=>{const angle=-Math.PI/2+2*Math.PI*index/Math.max(nodes.length,1),layer=nodes.length>36?.48+.52*Math.sqrt((index+1)/nodes.length):1;positions.set(Number(node.id),{x:centerX+Math.cos(angle)*radius*layer,y:centerY+Math.sin(angle)*radius*layer})});
  function lineBetween(source,target,className='relation-edge',arrow=true,startRadius=nodeRadius,endRadius=nodeRadius){const dx=target.x-source.x,dy=target.y-source.y,length=Math.hypot(dx,dy)||1,start=startRadius/length,end=(endRadius+(arrow?5:0))/length;return svgNode('line',{x1:source.x+dx*start,y1:source.y+dy*start,x2:target.x-dx*end,y2:target.y-dy*end,class:className,...(arrow?{'marker-end':'url(#relation-arrow)'}:{})})}
  function hyperStar(vertices){
    const byPosition=new Map();for(const vertex of vertices){const key=`${vertex.point.x}:${vertex.point.y}`,existing=byPosition.get(key);if(!existing||vertex.role==='target')byPosition.set(key,vertex)}const unique=[...byPosition.values()],center={x:unique.reduce((sum,vertex)=>sum+vertex.point.x,0)/unique.length,y:unique.reduce((sum,vertex)=>sum+vertex.point.y,0)/unique.length},tips=unique.map(vertex=>({role:vertex.role,label:vertex.label,x:vertex.point.x,y:vertex.point.y})).sort((left,right)=>Math.atan2(left.y-center.y,left.x-center.x)-Math.atan2(right.y-center.y,right.x-center.x));
    if(tips.length===1)return{d:`M${tips[0].x-18} ${tips[0].y}a18 18 0 1 0 36 0a18 18 0 1 0-36 0`,degenerate:true,tips,center};if(tips.length===2)return{d:`M${tips[0].x} ${tips[0].y}L${tips[1].x} ${tips[1].y}`,degenerate:true,tips,center};const unit=(dx,dy)=>{const length=Math.hypot(dx,dy)||1;return{x:dx/length,y:dy/length}},rotate=(vector,angle)=>({x:vector.x*Math.cos(angle)-vector.y*Math.sin(angle),y:vector.x*Math.sin(angle)+vector.y*Math.cos(angle)});
    for(let index=0;index<tips.length;index+=1){const tip=tips[index],previous=tips[(index+tips.length-1)%tips.length],next=tips[(index+1)%tips.length],inward=unit(center.x-tip.x,center.y-tip.y),halfAngle=(tip.role==='target'?4:12)*Math.PI/360,first=rotate(inward,-halfAngle),second=rotate(inward,halfAngle),towardNext=unit(next.x-tip.x,next.y-tip.y);if(first.x*towardNext.x+first.y*towardNext.y>second.x*towardNext.x+second.y*towardNext.y){tip.outgoing=first;tip.incoming=second}else{tip.outgoing=second;tip.incoming=first}tip.handle=Math.min(Math.hypot(next.x-tip.x,next.y-tip.y),Math.hypot(previous.x-tip.x,previous.y-tip.y))*.18}
    function segments(scales){return tips.map((current,index)=>{const next=tips[(index+1)%tips.length],length=Math.hypot(next.x-current.x,next.y-current.y),sourcePair=current.role==='source'&&next.role==='source',scale=scales[index]??1,cap=length*.82,currentHandle=Math.min(current.handle*scale,cap),nextHandle=Math.min(next.handle*scale,cap);return{sourcePair,p0:current,p1:{x:current.x+current.outgoing.x*currentHandle,y:current.y+current.outgoing.y*currentHandle},p2:{x:next.x+next.incoming.x*nextHandle,y:next.y+next.incoming.y*nextHandle},p3:next}})}
    const cubicPoint=(segment,t)=>{const u=1-t,a=u*u*u,b=3*u*u*t,c=3*u*t*t,d=t*t*t;return{x:a*segment.p0.x+b*segment.p1.x+c*segment.p2.x+d*segment.p3.x,y:a*segment.p0.y+b*segment.p1.y+c*segment.p2.y+d*segment.p3.y}};
    function curveHasClearance(curveIndex,scale,scales){const trial=[...scales];trial[curveIndex]=scale;const curves=segments(trial),subject=curves[curveIndex],others=curves.filter((_,index)=>index!==curveIndex),clearance=7,samples=28;for(let subjectStep=6;subjectStep<=samples-6;subjectStep+=1){const point=cubicPoint(subject,subjectStep/samples);for(const other of others)for(let otherStep=4;otherStep<=samples-4;otherStep+=1){const candidate=cubicPoint(other,otherStep/samples);if(Math.hypot(point.x-candidate.x,point.y-candidate.y)<clearance)return false}}return true}
    const scales=tips.map(()=>1),sourceSource=tips.findIndex((tip,index)=>tip.role==='source'&&tips[(index+1)%tips.length].role==='source'),curveOrder=[sourceSource,...tips.map((_,index)=>index).filter(index=>index!==sourceSource)];for(const curveIndex of curveOrder){if(curveIndex<0)continue;let lowerScale=scales[curveIndex],upperScale=10;if(curveHasClearance(curveIndex,upperScale,scales))lowerScale=upperScale;else for(let iteration=0;iteration<14;iteration+=1){const candidate=(lowerScale+upperScale)/2;if(curveHasClearance(curveIndex,candidate,scales))lowerScale=candidate;else upperScale=candidate}scales[curveIndex]=lowerScale}const curves=segments(scales);let d=`M${curves[0].p0.x} ${curves[0].p0.y}`;for(const curve of curves)d+=`C${curve.p1.x} ${curve.p1.y},${curve.p2.x} ${curve.p2.y},${curve.p3.x} ${curve.p3.y}`;return{d:d+'Z',degenerate:false,tips,center};
  }
  if(preview.endpoint_count===2){
    coordinates.forEach((edge,index)=>{const target=positions.get(Number(edge[0])),source=positions.get(Number(edge[1]));if(!source||!target)return;if(source===target){const loop=svgNode('path',{d:`M${source.x-5} ${source.y-8}C${source.x-28} ${source.y-35},${source.x+28} ${source.y-35},${source.x+5} ${source.y-8}`,class:'relation-edge','marker-end':'url(#relation-arrow)'});loop.append(svgNode('title'));loop.firstChild.textContent=`${edge[1]} → ${edge[0]}`;viewport.append(loop);return}const line=lineBetween(source,target);const title=svgNode('title');title.textContent=`${edge[1]} → ${edge[0]}`;line.append(title);viewport.append(line)})
  }else{
    coordinates.forEach(edge=>{const target=positions.get(Number(edge[0])),source1=positions.get(Number(edge[1])),source2=positions.get(Number(edge[2]));if(!target||!source1||!source2)return;const star=hyperStar([{point:target,role:'target',label:'T'},{point:source1,role:'source',label:'S1'},{point:source2,role:'source',label:'S2'}]),group=svgNode('g',{class:'relation-hyperedge'}),path=svgNode('path',{d:star.d,class:`relation-hyper-star${star.degenerate?' relation-hyper-degenerate':''}`}),title=svgNode('title');title.textContent=`(${edge[1]}, ${edge[2]}) → ${edge[0]}`;path.append(title);group.append(path);for(const tip of star.tips){const direction=(()=>{const dx=star.center.x-tip.x,dy=star.center.y-tip.y,length=Math.hypot(dx,dy)||1;return{x:dx/length,y:dy/length}})(),badge=svgNode('g',{class:'relation-hyper-role',transform:`translate(${tip.x+direction.x*18} ${tip.y+direction.y*18})`}),circle=svgNode('circle',{r:'10'}),text=svgNode('text',{x:'0',y:'.5'});text.textContent=tip.label;badge.append(circle,text);group.append(badge)}group.addEventListener('pointerenter',()=>{viewport.classList.add('hyperedge-active');group.classList.add('active')});group.addEventListener('pointerleave',()=>{group.classList.remove('active');if(!viewport.querySelector('.relation-hyperedge.active'))viewport.classList.remove('hyperedge-active')});viewport.append(group)})
  }
  for(const node of nodes){const position=positions.get(Number(node.id)),group=svgNode('g',{class:'relation-node'}),circle=svgNode('circle',{cx:position.x,cy:position.y,r:nodeRadius}),label=svgNode('text',{x:position.x,y:position.y+nodeRadius+12}),title=svgNode('title');const text=String(node.label);label.textContent=text.length>16?text.slice(0,15)+'…':text;title.textContent=text;group.append(circle,label,title);viewport.append(group)}
  stage.append(svg);host.append(stage);enableRelationViewport(stage,svg,viewport,width,height);const legend=el('div',undefined,'relation-legend'),count=el('span',_('relationPreviewCount',{nodes:nodes.length,relations:coordinates.length}));legend.append(count);if(preview.endpoint_count===3){const meaning=el('span');meaning.append(el('i',undefined,'hyper'),document.createTextNode(_('hyperedgeRoles')));legend.append(meaning)}host.append(legend);if(preview.truncated)host.append(el('p',_('relationPreviewTruncated'),'data-preview-note'));
}
function renderDataTable(){
  const host=$('data-table'),tensor=$('tensor-preview');host.replaceChildren();tensor.replaceChildren();
  if(plotMode!=='table'&&plotMode!=='structure')return
  if(!dataPreviewGroups.length||!dataGroupPreview)return
  const preview=dataGroupPreview;
  if(preview.kind==='relation'&&plotMode==='structure'){renderRelationGraph(tensor,preview);return}
  if(plotMode==='structure'){tensor.append(el('p',_('structureSelectRelation'),'data-preview-note'));return}
  if(preview.kind==='axis'){
    const table=el('table',undefined,'data-table'),head=document.createElement('thead'),headRow=document.createElement('tr');for(const column of preview.columns){const cell=el('th');cell.append(document.createTextNode(column));if(preview.column_kinds[column]==='axis')cell.append(el('span',_('axisKind'),'column-kind'));headRow.append(cell)}head.append(headRow);table.append(head);const body=document.createElement('tbody');for(const record of preview.data){const row=document.createElement('tr');for(const column of preview.columns)row.append(el('td',formatDataPreviewValue(record[column])));body.append(row)}table.append(body);host.append(table);if(preview.truncated)tensor.append(el('p',_('previewTruncated'),'data-preview-note'));return
  }
  if(preview.shape.length===2){
    const values=preview.values||preview.coordinates||[],[rowAxis='row',columnAxis='column']=preview.axes,rows=preview.axis_values?.[rowAxis]||values.map((_,index)=>index),columns=preview.axis_values?.[columnAxis]||Array.from({length:values[0]?.length||0},(_,index)=>index),table=el('table',undefined,'data-table tensor-table'),head=document.createElement('thead'),headRow=document.createElement('tr');const corner=el('th',undefined,'tensor-corner'),firstColumnCharacters=Math.max(rowAxis.length,columnAxis.length,...rows.map(value=>formatDataPreviewValue(value).length));corner.style.width=`${firstColumnCharacters+3}ch`;corner.style.minWidth=`${firstColumnCharacters+3}ch`;corner.append(el('span',rowAxis,'tensor-row-axis'),el('span',columnAxis,'tensor-column-axis'));headRow.append(corner);for(const value of columns)headRow.append(el('th',formatDataPreviewValue(value)));head.append(headRow);table.append(head);const body=document.createElement('tbody');for(let index=0;index<values.length;index+=1){const row=document.createElement('tr');row.append(el('th',formatDataPreviewValue(rows[index]??index)));for(const value of values[index])row.append(el('td',formatDataPreviewValue(value)));body.append(row)}table.append(body);host.append(table);if(Array.isArray(preview.truncated)&&preview.truncated.some(Boolean))tensor.append(el('p',_('previewTruncated'),'data-preview-note'));return
  }
  if(preview.shape.length===3){renderTensorCube(tensor,preview);return}
  appendTensorMetadata(tensor,preview);
}
async function loadDataPreviewGroup(group){
  selectedDataPreviewGroup=group;dataGroupPreview=null;renderDataTable();if(!group)return;const token=++dataGroupPreviewToken,result=await api('/api/data/context/preview?group='+encodeURIComponent(group),undefined,'GET');if(token!==dataGroupPreviewToken)return;dataGroupPreview=result;renderDataTable();
}
function selectedFeatures(){return variableOrder.filter(column=>variableRoles[column]==='feature')}
function targetVariable(){return variableOrder.find(column=>variableRoles[column]==='target')||''}
function variableRole(column){return variableRoles[column]||'unused'}
function describedVariables(){return Object.fromEntries(Object.entries(variableDescriptions).filter(([,description])=>description.trim()))}
function promptRegenerateButton(id){const button=el('button',undefined,'composer-settings-button prompt-regenerate');button.id=id;button.type='button';button.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M12.8 6.3A5 5 0 1 0 13 9M12.8 3.4v3h-3"/></svg><span></span>';return button}
function renderRequestedControlsLanguage(){
  for(const id of ['composer-purpose-regenerate','system-prompt-regenerate']){const button=$(id);if(!button)continue;const label=_('regeneratePrompt');button.querySelector('span').textContent=label;button.title=label;button.setAttribute('aria-label',label)}
  const dataInsightsRefresh=$('data-insights-refresh');if(dataInsightsRefresh){const label=_('refreshData');$('data-insights-refresh-label').textContent=label;dataInsightsRefresh.title=label;dataInsightsRefresh.setAttribute('aria-label',label)}
  const evaluatorToggle=$('evaluator-agent-toggle');if(evaluatorToggle){const label=_('evaluatorAgentToggle');evaluatorToggle.querySelector('span').textContent=label;evaluatorToggle.title=label;evaluatorToggle.setAttribute('aria-label',label)}
  for(const hint of document.querySelectorAll('.composer-keyboard-hint'))hint.textContent=_('composerEnterHint');
}
function mountRequestedLayout(){
  mountWorkflowNextControls();
  $('data-insights-note')?.remove();
  const dataInsightsRefresh=el('button',undefined,'data-refresh-button');dataInsightsRefresh.id='data-insights-refresh';dataInsightsRefresh.type='button';dataInsightsRefresh.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M12.7 6.2A5 5 0 1 0 13 9M12.7 3.5v2.8H9.9"/></svg><span id="data-insights-refresh-label"></span>';document.querySelector('#data-insights>.bar').append(dataInsightsRefresh);dataInsightsRefresh.onclick=dataGuard(reloadCommittedContext);
  const purpose=$('composer-purpose'),userRegenerate=promptRegenerateButton('composer-purpose-regenerate');purpose.append(el('span',undefined,'spacer'),userRegenerate);userRegenerate.onclick=guard(()=>regeneratePrompt('user'));
  const note=document.querySelector('.initial-prompt-note'),noteCopy=el('div',undefined,'initial-prompt-note-copy'),systemRegenerate=promptRegenerateButton('system-prompt-regenerate');noteCopy.append($('system-prompt-confirm-title'),$('system-prompt-confirm-help'));note.replaceChildren(noteCopy,systemRegenerate);systemRegenerate.onclick=guard(()=>regeneratePrompt('system'));
  const evaluatorAgent=document.querySelector('.evaluator-agent'),evaluatorToggle=el('button',undefined,'evaluator-agent-toggle');evaluatorToggle.id='evaluator-agent-toggle';evaluatorToggle.type='button';evaluatorToggle.setAttribute('aria-expanded','false');evaluatorToggle.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3.5 6 4.5 4 4.5-4"/></svg><span></span>';evaluatorAgent.before(evaluatorToggle);evaluatorAgent.hidden=true;evaluatorToggle.onclick=()=>{const open=evaluatorAgent.hidden;evaluatorAgent.hidden=!open;evaluatorToggle.setAttribute('aria-expanded',String(open))};
  const evaluatorSend=$('evaluator-agent-send'),evaluatorState=el('span','', 'small muted composer-status-center');evaluatorState.id='evaluator-agent-state';evaluatorSend.before(evaluatorState,composerKeyboardHint('evaluator-agent-keyboard-hint'));
  renderRequestedControlsLanguage();
}
function applyPromptPreview(preview,systemOnly=false){
  if(systemOnly){promptDefaults={...promptDefaults,system_prompt:preview.system_prompt||''};if(!promptEdited.system)$('system-prompt').value=promptDefaults.system_prompt;return}
  promptDefaults=preview;if(!promptEdited.system)$('system-prompt').value=preview.system_prompt||'';
  if(!promptEdited.user)$('prompt').value=preview.user_prompt||'';
}
async function refreshPromptPreview(force=''){
  const hasPreparedData=useCommittedContext;
  const token=++promptRefreshToken,payload={};
  const problemDescription=researchProblemDescription();if(problemDescription)payload.problem_description=problemDescription;
  payload.variable_descriptions=describedVariables();
  if(useCommittedContext){payload.target=targetVariable();payload.features=selectedFeatures();if(!payload.target)return}
  const preview=await api('/api/data/prompts',payload);if(token!==promptRefreshToken)return;if(force==='user'){promptDefaults=preview;$('prompt').value=preview.user_prompt||'';promptEdited.user=false;return}if(force==='system'){promptDefaults={...promptDefaults,system_prompt:preview.system_prompt||''};$('system-prompt').value=preview.system_prompt||'';promptEdited.system=false;return}applyPromptPreview(preview,!hasPreparedData);
}
async function regeneratePrompt(kind){const button=$(kind==='user'?'composer-purpose-regenerate':'system-prompt-regenerate');button.disabled=true;try{await refreshPromptPreview(kind)}finally{button.disabled=false}}
function schedulePromptPreview(){clearTimeout(promptRefreshTimer);promptRefreshTimer=setTimeout(()=>refreshPromptPreview().catch(error=>dataNote(error.message,true)),150)}
function fitProblemDescription(){
  const input=$('problem-description'),style=getComputedStyle(input),maximum=parseFloat(style.maxHeight)||Infinity;
  input.style.height='auto';const height=Math.min(input.scrollHeight,maximum);input.style.height=height+'px';input.style.overflowY=input.scrollHeight>maximum?'auto':'hidden';
}
function researchProblemDescription(){return $('problem-description').value.trim()||promptDefaults.problem_description||''}
function syncResearchProblem(value){promptDefaults.problem_description=value;schedulePromptPreview()}
function scheduleDataSelectionSave(){selectionSaveVersion+=1;clearTimeout(selectionSaveTimer);selectionSaveTimer=setTimeout(flushDataSelectionSave,400)}
async function flushDataSelectionSave(){
  if(selectionSaveInFlight||selectionSavedVersion===selectionSaveVersion)return;
  const version=selectionSaveVersion,target=targetVariable(),features=selectedFeatures();
  selectionSaveInFlight=true;
  try{
    const result=target
      ?await api('/api/data/selection',{target,features,variable_descriptions:{...variableDescriptions}},'PUT')
      :await api('/api/data/descriptions',{variable_descriptions:{...variableDescriptions}},'PUT');selectionSavedVersion=version;
    renderedDataRevision=result.revision||renderedDataRevision;if(dataPreview){dataPreview.target=target;dataPreview.features=[...features]}renderVariableRolePreview();
  }catch(error){selectionSavedVersion=version;dataNote(error?.message||error,true)}finally{selectionSaveInFlight=false;if(selectionSavedVersion<selectionSaveVersion){clearTimeout(selectionSaveTimer);selectionSaveTimer=setTimeout(flushDataSelectionSave,200)}}
}
function setVariableRole(column,role){
  if(!dataPreview?.columns.includes(column)||!['feature','target','unused'].includes(role))return;
  const previousTarget=targetVariable();if(role==='target'&&previousTarget&&previousTarget!==column)variableRoles[previousTarget]='feature';variableRoles[column]=role;
  $('target').value=targetVariable();renderVariableRoleTable();renderPlotVariablePalette();syncPlotChannelsToVariableConfiguration();renderPlotSlots();loadActivePlotPreview();schedulePromptPreview();scheduleDataSelectionSave();renderWorkflowNextControls();
}
function reorderVariable(column,before=''){
  if(!variableOrder.includes(column)||before===column)return;variableOrder=variableOrder.filter(name=>name!==column);const index=before?variableOrder.indexOf(before):-1;if(index>=0)variableOrder.splice(index,0,column);else variableOrder.push(column);renderVariableRoleTable();syncPlotChannelsToVariableConfiguration();renderPlotSlots();loadActivePlotPreview();schedulePromptPreview();scheduleDataSelectionSave();
}
function localizeVariableRoleTable(){
  const roleLabels={feature:_('feature'),target:_('target'),unused:_('unused')};
  for(const row of document.querySelectorAll('#variable-role-body .variable-row')){
    const column=row.dataset.column,role=variableRole(column),picker=row.querySelector('.role-picker'),summary=picker?.querySelector('summary');if(summary){summary.title=_('currentRole',{role:roleLabels[role]});summary.setAttribute('aria-label',summary.title)}
    for(const option of row.querySelectorAll('.role-option')){const value=option.dataset.role;option.querySelector('.role-option-label').textContent=roleLabels[value];if(value==='target')option.title=_('targetOnly')}
    const handle=row.querySelector('.variable-handle'),description=row.querySelector('.variable-description');if(handle)handle.title=_('dragReorder');if(description){description.placeholder=_('descriptionPlaceholder');description.setAttribute('aria-label',_('descriptionOf',{column}))}
  }
  const empty=document.querySelector('#variable-role-body .variable-table-empty');if(empty)empty.textContent=_('variableEmpty');
}
function resizeVariableDescription(description){description.style.height='auto';description.style.height=description.scrollHeight+'px'}
function renderVariableRoleTable(){
  const body=$('variable-role-body');body.replaceChildren();
  const roleLabels={feature:_('feature'),target:_('target'),unused:_('unused')};
  for(const column of variableOrder){
    const role=variableRole(column),row=el('div',undefined,'variable-row');row.dataset.column=column;
    const picker=el('details',undefined,'role-picker '+role),summary=el('summary',undefined,'role-color');summary.title=_('currentRole',{role:roleLabels[role]});summary.setAttribute('aria-label',summary.title);const menu=el('div',undefined,'role-menu');picker.ontoggle=()=>{if(picker.open)for(const other of document.querySelectorAll('.role-picker[open]'))if(other!==picker)other.open=false};
    for(const value of ['feature','target','unused']){const option=el('button',undefined,'role-option '+value+(value===role?' active':''));option.type='button';option.dataset.role=value;if(value==='target')option.title=_('targetOnly');option.append(el('span','', 'role-dot'),el('span',roleLabels[value],'role-option-label'),el('span',value===role?'✓':'','role-check'));option.onclick=event=>{event.preventDefault();event.stopPropagation();picker.open=false;setVariableRole(column,value)};menu.append(option)}picker.append(summary,menu);
    const handle=el('button','⠿','variable-handle');handle.type='button';handle.title=_('dragReorder');handle.draggable=true;handle.ondragstart=event=>{event.stopPropagation();event.dataTransfer.setData('application/x-srh-order-variable',column);event.dataTransfer.effectAllowed='move'};
    const pill=el('span',undefined,'variable-pill '+role);appendColumnLabel(pill,column);
    const description=document.createElement('textarea');description.className='variable-description';description.rows=1;description.value=variableDescriptions[column]||'';description.placeholder=_('descriptionPlaceholder');description.setAttribute('aria-label',_('descriptionOf',{column}));description.oninput=()=>{resizeVariableDescription(description);variableDescriptions[column]=description.value;renderVariableRolePreview();schedulePromptPreview();scheduleDataSelectionSave()};
    row.append(handle,picker,pill,description);body.append(row);resizeVariableDescription(description);
  }
  if(!body.children.length)body.append(el('div',_('variableEmpty'),'variable-table-empty'));
  body.ondragover=event=>{if(!event.dataTransfer.types.includes('application/x-srh-order-variable'))return;event.preventDefault();body.classList.add('dragover');const rows=[...body.querySelectorAll('.variable-row')],before=rows.find(row=>event.clientY<row.getBoundingClientRect().top+row.offsetHeight/2);for(const row of rows)row.classList.toggle('drop-before',row===before)};
  body.ondragleave=event=>{if(!body.contains(event.relatedTarget)){body.classList.remove('dragover');for(const row of body.querySelectorAll('.variable-row'))row.classList.remove('drop-before')}};
  body.ondrop=event=>{const column=event.dataTransfer.getData('application/x-srh-order-variable');if(!column)return;event.preventDefault();const before=[...body.querySelectorAll('.variable-row')].find(row=>event.clientY<row.getBoundingClientRect().top+row.offsetHeight/2)?.dataset.column||'';body.classList.remove('dragover');reorderVariable(column,before)};
  renderVariableRolePreview();
}
function renderVariableRolePreview(){
  const body=$('run-variable-role-body');if(!body)return;body.replaceChildren();
  const roleLabels={feature:_('feature'),target:_('target')},visibleColumns=variableOrder.filter(column=>variableRole(column)!=='unused');
  for(const column of visibleColumns){
    const role=variableRole(column),row=el('div',undefined,'variable-row variable-preview-row'),pill=el('span',undefined,'variable-pill '+role+' variable-preview-name'),description=el('span',variableDescriptions[column]||'—','variable-description-preview');
    appendColumnLabel(pill,column);if(role==='target')pill.append(el('span',roleLabels.target,'column-kind target-kind'));row.append(pill,description);body.append(row);
  }
  if(!body.children.length)body.append(el('div',_('variableEmpty'),'variable-table-empty'));
}
function plotColumnAxes(column){if(dataPreview?.columnKinds?.[column]==='axis')return[column];return dataPreview?.variableAxes?.[column]||[]}
function previewColumnsByRole(target){return['feature','unused'].flatMap(role=>variableOrder.filter(column=>column!==target&&variableRole(column)===role))}
function syncPlotChannelsToVariableConfiguration(){
  const target=targetVariable(),ordered=previewColumnsByRole(target);dataChannels={x:ordered[0]||'',y:target,hue:ordered[1]||'',size:ordered[2]||''};
  distributionChannels={x:target||ordered[0]||'',y:''};
  if(!target)return;const axes=plotColumnAxes(target);if(axes.length===2||axes.length===3){heatmapChannels={row:[axes[0]],column:[axes[1]],color:target,z:axes[2]||''};heatmapZIndex=0;return}
  if(axes.length===1){const axis=axes[0],aligned=[target,...ordered].filter((column,index,columns)=>columns.indexOf(column)===index&&dataPreview?.columnKinds?.[column]==='variable'&&plotColumnAxes(column).length===1&&plotColumnAxes(column)[0]===axis);heatmapChannels={row:[axis],column:aligned,color:'',z:''};heatmapZIndex=0}
}
function plotChannelItems(channel){if(plotMode==='scatter')return dataChannels[channel]?[dataChannels[channel]]:[];if(plotMode==='distribution')return distributionChannels[channel]?[distributionChannels[channel]]:[];const value=heatmapChannels[channel];return Array.isArray(value)?value:(value?[value]:[])}
function plotChannelHas(channel,column){return plotChannelItems(channel).includes(column)}
function renderPlotVariablePalette(){
  const host=$('plot-variable-palette');host.replaceChildren();
  if(!dataPreview?.columns?.length){host.append(el('span',_('noPlotVariables'),'plot-palette-empty'));return}
  for(const column of dataPreview.columns){const pill=el('span',undefined,'plot-palette-pill '+variableRole(column));appendColumnLabel(pill,column);pill.draggable=true;const axes=plotColumnAxes(column);pill.title=axes.length?_('plotVariableAxes',{axes:axes.join(' × ')}):_('dragRelationship');pill.ondragstart=event=>{plotDragAccepted=true;event.dataTransfer.setData('application/x-srh-plot-variable',column);event.dataTransfer.setData('text/plain',column);event.dataTransfer.effectAllowed='copy'};host.append(pill)}
  host.ondragover=event=>{if(!event.dataTransfer.types.includes('application/x-srh-slot-channel'))return;event.preventDefault();event.dataTransfer.dropEffect='move'};host.ondrop=event=>{const source=event.dataTransfer.getData('application/x-srh-slot-channel'),column=event.dataTransfer.getData('application/x-srh-plot-variable');if(!source||!column)return;event.preventDefault();plotDragAccepted=true;removePlotChannelItem(source,column)};
}
function renderPlotSlots(){
  const definitions=plotMode==='heatmap'?[['row','ROW'],['column','COL'],['color','MAP'],['z','Z']]:plotMode==='distribution'?[['x','X'],['y','Y']]:[['x','X'],['y','Y'],['hue','HUE'],['size','SIZE']];
  const fields=document.querySelector('.plot-fields'),slots=[...document.querySelectorAll('.plot-slot')];fields.style.gridTemplateColumns=plotMode==='distribution'?'repeat(2,minmax(0,1fr))':'';slots.forEach((slot,index)=>slot.hidden=index>=definitions.length);definitions.forEach(([channel,label],index)=>{const slot=slots[index],host=slot.querySelector('.plot-slot-value');slot.dataset.channel=channel;slot.querySelector('b').textContent=label;host.replaceChildren();for(const column of plotChannelItems(channel)){const pill=el('span',undefined,'plot-variable-pill '+variableRole(column));appendColumnLabel(pill,column);pill.draggable=true;pill.title=_('movePlotVariable');pill.ondragstart=event=>{event.stopPropagation();plotDragAccepted=false;event.dataTransfer.setData('application/x-srh-plot-variable',column);event.dataTransfer.setData('application/x-srh-slot-channel',channel);event.dataTransfer.effectAllowed='move'};pill.ondragend=()=>{if(!plotDragAccepted&&plotChannelHas(channel,column))removePlotChannelItem(channel,column);plotDragAccepted=false};host.append(pill)}});
}
function removePlotChannelItem(channel,column){
  if(plotMode==='scatter'){if(dataChannels[channel]===column)dataChannels={...dataChannels,[channel]:''}}
  else if(plotMode==='distribution'){if(distributionChannels[channel]===column)distributionChannels={...distributionChannels,[channel]:''}}
  else if(Array.isArray(heatmapChannels[channel]))heatmapChannels={...heatmapChannels,[channel]:heatmapChannels[channel].filter(item=>item!==column)};
  else if(heatmapChannels[channel]===column)heatmapChannels={...heatmapChannels,[channel]:''};
  renderPlotSlots();loadActivePlotPreview();
}
function setPlotChannel(channel,column,sourceChannel=''){
  if(!column)return;
  if(plotMode==='scatter'){
    const next={...dataChannels},replaced=next[channel];next[channel]=column;if(sourceChannel&&sourceChannel!==channel)next[sourceChannel]=replaced||'';dataChannels=next;
  }else if(plotMode==='distribution'){
    const next={...distributionChannels},replaced=next[channel];next[channel]=column;if(sourceChannel&&sourceChannel!==channel)next[sourceChannel]=replaced||'';distributionChannels=next;
  }else{
    if(channel==='color'||channel==='z')heatmapZIndex=0;
    const next={...heatmapChannels,row:[...heatmapChannels.row],column:[...heatmapChannels.column]};
    if(sourceChannel&&sourceChannel!==channel){if(Array.isArray(next[sourceChannel]))next[sourceChannel]=next[sourceChannel].filter(item=>item!==column);else if(next[sourceChannel]===column)next[sourceChannel]=''}
    if(channel==='row'||channel==='column'){
      const isAxis=dataPreview?.columnKinds?.[column]==='axis',existing=next[channel];
      if(isAxis)next[channel]=[column];else if(existing.every(item=>dataPreview?.columnKinds?.[item]!=='axis')&&!existing.includes(column))next[channel]=[...existing,column];else if(!existing.includes(column))next[channel]=[column];
    }else{next[channel]=column;if(channel==='color'){const axes=plotColumnAxes(column);if(axes.length===2||axes.length===3){next.row=[axes[0]];next.column=[axes[1]];next.z=axes[2]||''}}}
    heatmapChannels=next;
  }
  renderPlotSlots();loadActivePlotPreview();dataNote(_('plotAdjusted'));
}
function loadActivePlotPreview(){
  renderPlotModeSurface();if(plotMode==='table'||plotMode==='structure')return;
  if(plotMode==='heatmap')loadHeatmapPreview().catch(error=>{heatmapPreview=null;renderHeatmap(error?.message||error)});
  else if(plotMode==='distribution')loadDistributionPreview().catch(error=>{plotPreview=null;renderDistribution(error?.message||error)});
  else loadPlotPreview().catch(error=>{plotPreview=null;renderScatter(error?.message||error)});
}
function renderPlotModeSurface(){const dataTable=plotMode==='table'||plotMode==='structure';$('data-table-preview').hidden=!dataTable;document.querySelector('#data-insights>.relationship-preview-scroll').hidden=dataTable;document.querySelector('.data-number-format').hidden=plotMode==='structure';$('relationship-preview-title').textContent=_('dataInsightsTitle');if(dataTable)renderDataTable()}
function renderActivePlot(){renderPlotModeSurface();if(plotMode==='table'||plotMode==='structure')return;if(plotMode==='heatmap')renderHeatmap();else if(plotMode==='distribution')renderDistribution();else renderScatter()}
function renderPlotModeLanguage(){if(!['table','structure','scatter','distribution','heatmap'].includes(plotMode))plotMode='table';const select=$('relationship-preview-mode'),labels={table:'tablePreview',structure:'structurePreview',scatter:'scatterPlot',distribution:'distributionPlot',heatmap:'heatmapPlot'};for(const option of select.options)option.textContent=_(labels[option.value]);select.value=plotMode;select.setAttribute('aria-label',_('relationshipPreviewMode'));$('distribution-bin-label').textContent=_('distributionBins');renderPlotModeSurface()}
function svgNode(tag,attributes={}){const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attributes))node.setAttribute(key,value);return node}
async function loadPlotPreview(){
  const token=++plotPreviewToken;plotPreview=null;renderScatter();if(!dataPreview||!dataChannels.x||!dataChannels.y)return;
  const query=new URLSearchParams({x:dataChannels.x,y:dataChannels.y,limit:'2000'});if(dataChannels.hue)query.set('hue',dataChannels.hue);if(dataChannels.size)query.set('size',dataChannels.size);
  const result=await api('/api/data/context/plot?'+query.toString(),undefined,'GET');if(token!==plotPreviewToken)return;plotPreview=result;renderScatter();
}
async function loadDistributionPreview(){
  const token=++plotPreviewToken;plotPreview=null;renderDistribution();if(!dataPreview||!distributionChannels.x)return;const query=new URLSearchParams({x:distributionChannels.x,y:distributionChannels.y||distributionChannels.x,limit:'5000'}),result=await api('/api/data/context/plot?'+query.toString(),undefined,'GET');if(token!==plotPreviewToken)return;plotPreview=result;renderDistribution();
}
function plotDimension(column){
  const numeric=plotPreview.numeric[column],raw=plotPreview.values[column]||[];if(numeric){const values=raw.map(Number).filter(Number.isFinite),actualMin=Math.min(...values),actualMax=Math.max(...values),min=actualMin===actualMax?actualMin-1:actualMin,max=actualMin===actualMax?actualMax+1:actualMax;return{numeric,values:raw.map(Number),min,max,ticks:Array.from({length:5},(_,index)=>{const value=min+index/4*(max-min);return[value,Number(value.toPrecision(3)).toString()]})}}
  const categories=[...new Set(raw.map(value=>String(value??'—')))],index=new Map(categories.map((value,position)=>[value,position])),max=Math.max(1,categories.length-1),step=Math.max(1,Math.ceil(categories.length/8));return{numeric,values:raw.map(value=>index.get(String(value??'—'))),min:0,max,categories,ticks:categories.map((value,position)=>[position,value.length>14?value.slice(0,13)+'…':value]).filter((_,position)=>position%step===0)};
}
function plotShapeLabel(axes,shape){return shape.length?shape.map((size,index)=>`${size} (${axes[index]||'?'})`).join(' × '):`1 (${_('scalarAxes')})`}
function renderScatter(error=''){
  const svg=$('scatter'),stage=$('plot-stage'),info=$('plot-broadcast-info'),zControl=$('heatmap-z-control');stage.insertBefore(info,svg);svg.replaceChildren();info.hidden=true;zControl.hidden=true;$('distribution-bin-control').hidden=true;if(typeof error==='string'&&error){$('plot-empty').hidden=false;$('plot-empty').textContent=error;return}if(!dataPreview||!dataChannels.x||!dataChannels.y||stage.clientWidth<80){$('plot-empty').hidden=false;$('plot-empty').textContent=_('dropVariable');return}if(!plotPreview){$('plot-empty').hidden=false;$('plot-empty').textContent=_('plotLoading');return}
  const shape=plotShapeLabel(plotPreview.axes,plotPreview.shape);info.textContent=_(plotPreview.truncated?'plotShapeTruncated':'plotShape',{shape});info.hidden=false;
  const xDimension=plotDimension(dataChannels.x),yDimension=plotDimension(dataChannels.y),points=Array.from({length:plotPreview.count},(_,index)=>({index,x:xDimension.values[index],y:yDimension.values[index]})).filter(point=>Number.isFinite(point.x)&&Number.isFinite(point.y));if(!points.length){$('plot-empty').hidden=false;$('plot-empty').textContent=_('plotNoFinitePoints');return}$('plot-empty').hidden=true;
  const width=Math.max(320,svg.clientWidth||stage.clientWidth),height=Math.max(220,svg.clientHeight||stage.clientHeight),margin={left:yDimension.numeric?43:84,right:16,top:14,bottom:xDimension.numeric?34:48},innerW=width-margin.left-margin.right,innerH=height-margin.top-margin.bottom;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);const sx=value=>margin.left+(value-xDimension.min)/(xDimension.max-xDimension.min||1)*innerW,sy=value=>margin.top+innerH-(value-yDimension.min)/(yDimension.max-yDimension.min||1)*innerH;
  svg.append(svgNode('path',{d:`M${margin.left} ${margin.top}V${margin.top+innerH}H${margin.left+innerW}`,fill:'none',stroke:'#cbd3d8','stroke-width':'1'}));
  for(const [value,label] of xDimension.ticks){const tick=svgNode('text',{x:sx(value),y:height-15,'text-anchor':'middle',fill:'#8995a1','font-size':'9'});tick.textContent=label;svg.append(tick)}for(const [value,label] of yDimension.ticks){const tick=svgNode('text',{x:margin.left-7,y:sy(value)+3,'text-anchor':'end',fill:'#8995a1','font-size':'9'});tick.textContent=label;svg.append(tick)}
  const hue=dataChannels.hue,hueValues=hue?points.map(point=>plotPreview.values[hue][point.index]):[],numericHue=hue&&plotPreview.numeric[hue],numericHueValues=numericHue?hueValues.map(Number).filter(Number.isFinite):[],hmin=numericHueValues.length?Math.min(...numericHueValues):0,hmax=numericHueValues.length?Math.max(...numericHueValues):1,categories=[...new Set(hueValues.map(String))],palette=['#25877c','#c47b4c','#6f79aa','#a25f83','#7f9948','#4c8caf'];
  const size=dataChannels.size,numericSize=size&&plotPreview.numeric[size],sizeValues=numericSize?points.map(point=>Number(plotPreview.values[size][point.index])).filter(Number.isFinite):[],sizeCategories=size&&!numericSize?[...new Set(points.map(point=>String(plotPreview.values[size][point.index])))]:[],smin=sizeValues.length?Math.min(...sizeValues):0,smax=sizeValues.length?Math.max(...sizeValues):1;
  const shownColumns=[...new Set(Object.values(dataChannels).filter(Boolean))];for(const point of points){let color='#287f76';if(hue){const raw=plotPreview.values[hue][point.index];if(numericHue){const value=Number(raw),ratio=Number.isFinite(value)?(value-hmin)/(hmax-hmin||1):.5;color=`rgb(${Math.round(48+ratio*163)},${Math.round(137-ratio*38)},${Math.round(128-ratio*60)})`}else color=palette[Math.max(0,categories.indexOf(String(raw)))%palette.length]}let radius=4;if(size){const raw=plotPreview.values[size][point.index];if(numericSize){const value=Number(raw);if(Number.isFinite(value))radius=3+6*(value-smin)/(smax-smin||1)}else radius=3+6*Math.max(0,sizeCategories.indexOf(String(raw)))/(sizeCategories.length-1||1)}const circle=svgNode('circle',{cx:sx(point.x),cy:sy(point.y),r:radius,fill:color,'fill-opacity':'.72',stroke:'#fff','stroke-width':'.7'}),title=svgNode('title');title.textContent=shownColumns.map(column=>`${column}: ${plotPreview.values[column][point.index]}`).join('\n');circle.append(title);svg.append(circle)}
  const xLabel=svgNode('text',{x:margin.left+innerW/2,y:height-1,'text-anchor':'middle',fill:'#52616f','font-size':'10'});xLabel.textContent=dataChannels.x;svg.append(xLabel);const yLabel=svgNode('text',{x:10,y:margin.top+innerH/2,'text-anchor':'middle',fill:'#52616f','font-size':'10',transform:`rotate(-90 10 ${margin.top+innerH/2})`});yLabel.textContent=dataChannels.y;svg.append(yLabel);
}
function distributionBinner(column){
  const raw=plotPreview.values[column]||[],numeric=plotPreview.numeric[column];if(numeric){const finite=raw.map(Number).filter(Number.isFinite);if(!finite.length)return{count:1,position:()=>-1,label:()=> '—'};const minimum=Math.min(...finite),maximum=Math.max(...finite),count=minimum===maximum?1:Math.min(distributionBins,Math.max(2,finite.length)),position=value=>{const number=Number(value);if(!Number.isFinite(number))return-1;return Math.min(count-1,Math.max(0,Math.floor((number-minimum)/(maximum-minimum||1)*count)))};return{count,position,label:index=>count===1?Number(minimum.toPrecision(3)).toString():Number((minimum+(index+.5)/count*(maximum-minimum)).toPrecision(3)).toString()}}
  const categories=[...new Set(raw.map(value=>String(value??'—')))].slice(0,50),index=new Map(categories.map((value,position)=>[value,position]));return{count:Math.max(1,categories.length),position:value=>index.get(String(value??'—'))??-1,label:position=>categories[position]||'—'};
}
function renderDistribution(error=''){
  const svg=$('scatter'),stage=$('plot-stage'),info=$('plot-broadcast-info'),control=$('distribution-bin-control');stage.insertBefore(info,svg);svg.replaceChildren();info.hidden=true;$('heatmap-z-control').hidden=true;control.hidden=false;if(typeof error==='string'&&error){$('plot-empty').hidden=false;$('plot-empty').textContent=error;return}if(!dataPreview||!distributionChannels.x||stage.clientWidth<80){$('plot-empty').hidden=false;$('plot-empty').textContent=_('distributionDropX');return}if(!plotPreview){$('plot-empty').hidden=false;$('plot-empty').textContent=_('plotLoading');return}$('plot-empty').hidden=true;
  const shape=plotShapeLabel(plotPreview.axes,plotPreview.shape);info.textContent=_(plotPreview.truncated?'plotShapeTruncated':'plotShape',{shape});info.hidden=false;const width=Math.max(320,svg.clientWidth||stage.clientWidth),height=Math.max(220,svg.clientHeight||stage.clientHeight),margin={left:44,right:14,top:14,bottom:38},innerW=width-margin.left-margin.right,innerH=height-margin.top-margin.bottom,xName=distributionChannels.x,yName=distributionChannels.y,xBin=distributionBinner(xName),xRaw=plotPreview.values[xName]||[];svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  if(!yName){const counts=Array(xBin.count).fill(0);for(const value of xRaw){const index=xBin.position(value);if(index>=0)counts[index]+=1}const maximum=Math.max(1,...counts),barWidth=innerW/Math.max(1,counts.length);for(let index=0;index<counts.length;index+=1){const barHeight=counts[index]/maximum*innerH,bar=svgNode('rect',{x:margin.left+index*barWidth+1,y:margin.top+innerH-barHeight,width:Math.max(1,barWidth-2),height:barHeight,class:'histogram-bar'}),title=svgNode('title');title.textContent=`${xBin.label(index)}: ${counts[index]}`;bar.append(title);svg.append(bar)}const step=Math.max(1,Math.ceil(counts.length/7));for(let index=0;index<counts.length;index+=step){const tick=svgNode('text',{x:margin.left+(index+.5)*barWidth,y:height-17,'text-anchor':'middle',fill:'#8995a1','font-size':'8'});tick.textContent=xBin.label(index).slice(0,12);svg.append(tick)}const label=svgNode('text',{x:margin.left+innerW/2,y:height-2,'text-anchor':'middle',fill:'#52616f','font-size':'10'});label.textContent=xName;svg.append(label);return}
  const yBin=distributionBinner(yName),yRaw=plotPreview.values[yName]||[],counts=Array.from({length:yBin.count},()=>Array(xBin.count).fill(0));for(let index=0;index<Math.min(xRaw.length,yRaw.length);index+=1){const x=xBin.position(xRaw[index]),y=yBin.position(yRaw[index]);if(x>=0&&y>=0)counts[y][x]+=1}const maximum=Math.max(1,...counts.flat()),cellW=innerW/xBin.count,cellH=innerH/yBin.count;for(let row=0;row<yBin.count;row+=1)for(let column=0;column<xBin.count;column+=1){const value=counts[row][column],ratio=value/maximum,cell=svgNode('rect',{x:margin.left+column*cellW,y:margin.top+(yBin.count-row-1)*cellH,width:cellW+.2,height:cellH+.2,fill:`rgb(${Math.round(232-154*ratio)},${Math.round(244-94*ratio)},${Math.round(241-103*ratio)})`,class:'histogram-cell'}),title=svgNode('title');title.textContent=`${xName}: ${xBin.label(column)}\n${yName}: ${yBin.label(row)}\n${value}`;cell.append(title);svg.append(cell)}const xStep=Math.max(1,Math.ceil(xBin.count/6)),yStep=Math.max(1,Math.ceil(yBin.count/6));for(let index=0;index<xBin.count;index+=xStep){const tick=svgNode('text',{x:margin.left+(index+.5)*cellW,y:height-17,'text-anchor':'middle',fill:'#8995a1','font-size':'8'});tick.textContent=xBin.label(index).slice(0,10);svg.append(tick)}for(let index=0;index<yBin.count;index+=yStep){const tick=svgNode('text',{x:margin.left-5,y:margin.top+(yBin.count-index-.5)*cellH+3,'text-anchor':'end',fill:'#8995a1','font-size':'8'});tick.textContent=yBin.label(index).slice(0,10);svg.append(tick)}for(const [name,x,y,transform] of [[xName,margin.left+innerW/2,height-2,''],[yName,11,margin.top+innerH/2,`rotate(-90 11 ${margin.top+innerH/2})`]]){const label=svgNode('text',{x,y,'text-anchor':'middle',fill:'#52616f','font-size':'10',...(transform?{transform}:{})});label.textContent=name;svg.append(label)}
}
async function loadHeatmapPreview(preserve=false){
  const token=++heatmapPreviewToken;if(!preserve){heatmapPreview=null;renderHeatmap()}const configured=heatmapChannels.row.length&&heatmapChannels.column.length;if(!dataPreview||!configured)return;
  const result=await api('/api/data/context/heatmap',{...heatmapChannels,z_index:heatmapZIndex});if(token!==heatmapPreviewToken)return;heatmapPreview=result;renderHeatmap();
}
function renderHeatmapZControl(preview){
  const host=$('heatmap-z-control');if(!preview.z_size){host.replaceChildren();host.hidden=true;return}
  const signature=`${preview.z_axis}:${preview.z_size}`;if(host.dataset.signature!==signature){const label=el('span'),slider=el('input'),output=el('output');slider.type='range';slider.min='0';slider.oninput=()=>{heatmapZIndex=Number(slider.value);output.textContent='…';loadHeatmapPreview(true).catch(error=>renderHeatmap(error?.message||error))};host.replaceChildren(label,slider,output);host.dataset.signature=signature}
  const [label,slider,output]=host.children;label.textContent=preview.z_axis;slider.setAttribute('aria-label',preview.z_axis);slider.max=String(preview.z_size-1);slider.value=String(preview.z_index);output.textContent=String(preview.z_value??'—');host.hidden=false;
}
function renderHeatmap(error=''){
  const svg=$('scatter'),stage=$('plot-stage'),info=$('plot-broadcast-info'),zControl=$('heatmap-z-control');svg.after(info);svg.replaceChildren();info.hidden=true;zControl.hidden=true;$('distribution-bin-control').hidden=true;if(typeof error==='string'&&error){$('plot-empty').hidden=false;$('plot-empty').textContent=error;return}if(!heatmapChannels.row.length||!heatmapChannels.column.length||stage.clientWidth<80){$('plot-empty').hidden=false;$('plot-empty').textContent=_('heatmapDropVariables');return}if(!heatmapPreview){$('plot-empty').hidden=false;$('plot-empty').textContent=_('plotLoading');return}$('plot-empty').hidden=true;
  const preview=heatmapPreview,shape=plotShapeLabel([preview.row_axis,preview.column_axis],preview.shape);info.textContent=_(preview.truncated?'heatmapShapeTruncated':'heatmapShape',{shape});info.hidden=false;
  const rows=preview.row_labels||[],columns=preview.column_labels||[],values=preview.values||[],width=Math.max(320,svg.clientWidth||stage.clientWidth),height=Math.max(240,svg.clientHeight||stage.clientHeight),rowChars=Math.max(3,...rows.map(value=>String(value).length)),left=Math.min(105,28+rowChars*5.2),margin={left,right:12,top:70,bottom:14},innerW=width-margin.left-margin.right,innerH=height-margin.top-margin.bottom,cellW=innerW/Math.max(columns.length,1),cellH=innerH/Math.max(rows.length,1),flat=values.flat(),numericValues=preview.numeric?flat.map(Number).filter(Number.isFinite):[],min=numericValues.length?Math.min(...numericValues):0,max=numericValues.length?Math.max(...numericValues):1,categories=preview.numeric?[]:[...new Set(flat.map(value=>String(value??'—')))],palette=['#e8f3f0','#8bc2b9','#426ca8','#cf8a6c','#ad5f65','#66507b'];svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  function cellColor(value){if(preview.numeric){const number=Number(value);if(!Number.isFinite(number))return'#dfe5e4';const ratio=(number-min)/(max-min||1),red=Math.round(232+(181-232)*ratio),green=Math.round(244+(91-244)*ratio),blue=Math.round(241+(101-241)*ratio);return`rgb(${red},${green},${blue})`}return palette[Math.max(0,categories.indexOf(String(value??'—')))%palette.length]}
  for(let row=0;row<rows.length;row+=1)for(let column=0;column<columns.length;column+=1){const value=values[row]?.[column],rect=svgNode('rect',{x:margin.left+column*cellW,y:margin.top+row*cellH,width:cellW+.2,height:cellH+.2,fill:cellColor(value),class:'heatmap-cell'}),title=svgNode('title');title.textContent=`${preview.row_axis}: ${rows[row]}\n${preview.column_axis}: ${columns[column]}\n${heatmapChannels.color||_('value')}: ${value}`;rect.append(title);svg.append(rect)}
  const rowStep=Math.max(1,Math.ceil(rows.length/14)),columnStep=Math.max(1,Math.ceil(columns.length/12));for(let row=0;row<rows.length;row+=rowStep){const label=svgNode('text',{x:margin.left-6,y:margin.top+(row+.5)*cellH+3,'text-anchor':'end',class:'heatmap-axis-label'});label.textContent=String(rows[row]).slice(0,18);svg.append(label)}for(let column=0;column<columns.length;column+=columnStep){const x=margin.left+(column+.5)*cellW,y=margin.top-8,label=svgNode('text',{x,y,'text-anchor':'start',class:'heatmap-axis-label',transform:`rotate(-35 ${x} ${y})`});label.textContent=String(columns[column]).slice(0,18);svg.append(label)}
  const rowTitle=svgNode('text',{x:10,y:margin.top+innerH/2,'text-anchor':'middle',class:'heatmap-axis-title',transform:`rotate(-90 10 ${margin.top+innerH/2})`});rowTitle.textContent=preview.row_axis;svg.append(rowTitle);const columnTitle=svgNode('text',{x:margin.left+innerW/2,y:35,'text-anchor':'middle',class:'heatmap-axis-title'});columnTitle.textContent=preview.column_axis;svg.append(columnTitle);
  renderHeatmapZControl(preview);
}
function configureDataPreview(){
  const columns=dataPreview.columns,numeric=dataPreview.previewColumns.filter(column=>dataPreview.numeric[column]),variables=columns.filter(column=>dataPreview.columnKinds[column]==='variable'),preferred=dataPreview.target||$('target').value,target=columns.includes(preferred)?preferred:useCommittedContext?'':(variables.includes('y')?'y':variables.at(-1)||''),configuredFeatures=(dataPreview.features||[]).filter(column=>columns.includes(column)&&column!==target),features=Array.isArray(dataPreview.features)?new Set(configuredFeatures):new Set(variables.filter(column=>column!==target));
  $('target').value=target;variableDescriptions=Object.fromEntries(columns.map(column=>[column,variableDescriptions[column]||'']));variableOrder=[...columns];variableRoles=Object.fromEntries(columns.map(column=>[column,column===target?'target':features.has(column)?'feature':'unused']));
  renderVariableRoleTable();renderPlotVariablePalette();heatmapChannels={row:[],column:[],color:'',z:''};syncPlotChannelsToVariableConfiguration();renderPlotSlots();renderDataPreviewGroupPicker();loadDataPreviewGroup(selectedDataPreviewGroup).catch(error=>dataNote(error?.message||error,true));requestAnimationFrame(loadActivePlotPreview);
  schedulePromptPreview();
}
async function startPreparedRun(userPrompt=''){
  if(startRequestPending)return;if(session&&session.state!=='idle'){selectCenterTab('timeline');return}startRequestPending=true;initialPromptSent=true;$('composer-purpose-help').hidden=true;$('send').disabled=true;
  try{
    await ensureCapabilities();if(!$('tool-options').children.length)await syncSettingsForm();await saveProviderCredential();if(evaluatorDirty)await saveEvaluatorConfiguration();
    const target=targetVariable(),features=selectedFeatures();
    if(!useCommittedContext)throw Error(_('contextDataRequired'));if(!userPrompt.trim())throw Error(_('inputRequired'));
    const payload={problem_description:researchProblemDescription(),user_prompt:userPrompt,variable_descriptions:describedVariables(),...(target?{target,features}:{}),...settingsPayload()};if(promptEdited.system)payload.system_prompt=$('system-prompt').value.trim();
    dataNote(_('startingRun'));const started=await api('/api/session/start',payload);syncSession(started);$('prompt').value='';selectCenterTab('timeline');
  } finally {startRequestPending=false;$('send').disabled=Boolean(session&&session.state!=='idle'&&!['starting','running'].includes(session.state))}
}
function disclosure(parent,title,value,open=false){if(value===undefined||value===null||value==='')return;const d=el('details');d.open=open;d.append(el('summary',title),el('pre',pretty(value)));parent.append(d)}
function layoutPreview(block){
  if(!block.isConnected)return;
  const content=block.querySelector('.reasoning-content'),topToggle=block.querySelector('.reasoning-toggle-top'),bottomToggle=block.querySelector('.reasoning-toggle-bottom'),expanded=block.classList.contains('expanded');
  // Measure the current layout; toggling display while observing width caused reflow during streaming.
  const lineHeight=parseFloat(getComputedStyle(content).lineHeight)||20;
  const needsDisclosure=expanded||content.scrollWidth>content.clientWidth+1||content.scrollHeight>lineHeight+2;
  topToggle.hidden=!needsDisclosure;bottomToggle.hidden=!expanded;content.classList.toggle('truncated',needsDisclosure&&!expanded);
  topToggle.textContent=expanded?'↑':'⌄';topToggle.title=_(expanded?'collapse':'expand');topToggle.setAttribute('aria-expanded',String(expanded));bottomToggle.setAttribute('aria-expanded',String(expanded));
}
const previewWidths=new WeakMap(),previewObserver=new ResizeObserver(entries=>{for(const entry of entries){const width=entry.contentRect.width;if(previewWidths.get(entry.target)===width)continue;previewWidths.set(entry.target,width);layoutPreview(entry.target)}});
function previewBlock(parent,value,extraClass='',agentOutput=false){
  if(!value)return;
  const block=el('div',undefined,'reasoning-block'+(extraClass?' '+extraClass:'')),content=el('div',undefined,'reasoning-content'),topToggle=el('button','⌄','reasoning-toggle reasoning-toggle-top'),bottomToggle=el('button',_('collapse')+' ↑','reasoning-toggle reasoning-toggle-bottom');if(agentOutput)renderAgentOutput(content,value);else content.textContent=pretty(value);
  for(const toggle of [topToggle,bottomToggle]){toggle.type='button';toggle.title=_(toggle===topToggle?'expand':'collapse');toggle.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.onclick=()=>{block.classList.toggle('expanded');layoutPreview(block)}}
  block.append(content,topToggle,bottomToggle);parent.append(block);previewObserver.observe(block);requestAnimationFrame(()=>layoutPreview(block));
}
function reasoningBlock(parent,value){previewBlock(parent,value,'',true)}
function unobservePreviewBlocks(parent){for(const block of parent.querySelectorAll('.reasoning-block'))previewObserver.unobserve(block)}
function parseToolParams(call){
  const value=call.params??call.function?.arguments??{};
  if(typeof value!=='string')return value;
  try{return JSON.parse(value)}catch{return {value}}
}
function parameterValue(value){
  const node=el('div',undefined,'param-value');
  if(value===null||value===undefined){node.append(el('span','null','param-null'));return node}
  if(Array.isArray(value)){
    const list=el('div',undefined,'param-list');
    if(!value.length)list.append(el('span',_('emptyList'),'param-null'));
    for(const entry of value){
      if(entry&&typeof entry==='object')list.append(parameterValue(entry));
      else list.append(el('span',String(entry),'param-chip'));
    }
    node.append(list);return node;
  }
  if(typeof value==='object'){
    const object=el('div',undefined,'param-object');
    for(const [key,entry] of Object.entries(value)){
      const row=el('div',undefined,'param-object-row');
      row.append(el('span',key,'param-object-key'),parameterValue(entry));object.append(row);
    }
    if(!Object.keys(value).length)object.append(el('span',_('emptyObject'),'param-null'));
    node.append(object);return node;
  }
  node.textContent=String(value);return node;
}
function parameterPreview(value){
  const text=typeof value==='string'?value:JSON.stringify(value);
  return String(text??'null').trim().split(/\r?\n/,1)[0]||_('viewParameters');
}
function collapseLongParameter(row,valueNode,value){
  requestAnimationFrame(()=>{
    if(!valueNode.isConnected)return;
    const lineHeight=parseFloat(getComputedStyle(valueNode).lineHeight)||18;
    if(valueNode.scrollHeight<=lineHeight*1.5)return;
    const block=el('div',undefined,'reasoning-block param-disclosure'),preview=el('span',parameterPreview(value),'reasoning-content truncated'),topToggle=el('button','⌄','reasoning-toggle reasoning-toggle-top'),expanded=el('div',undefined,'param-expanded'),bottomToggle=el('button',_('collapse')+' ↑','reasoning-toggle reasoning-toggle-bottom');
    const setExpanded=expandedState=>{block.classList.toggle('expanded',expandedState);preview.classList.toggle('truncated',!expandedState);topToggle.textContent=expandedState?'↑':'⌄';topToggle.title=_(expandedState?'collapse':'expand');topToggle.setAttribute('aria-expanded',String(expandedState));bottomToggle.setAttribute('aria-expanded',String(expandedState));bottomToggle.hidden=!expandedState};
    for(const toggle of [topToggle,bottomToggle]){toggle.type='button';toggle.onclick=()=>setExpanded(!block.classList.contains('expanded'))}
    topToggle.title=_('expand');topToggle.setAttribute('aria-expanded','false');bottomToggle.title=_('collapse');bottomToggle.hidden=true;block.append(preview,topToggle,expanded,bottomToggle);
    if(row.isConnected){row.replaceChild(block,valueNode);expanded.append(valueNode)}
  });
}
function toolParameters(params,schema,collapseLong=false){
  const entries=params&&typeof params==='object'&&!Array.isArray(params)?Object.entries(params):[['value',params]];
  if(!entries.length)return el('div',_('noParameters'),'no-params');
  const normalized=schema?.function?.parameters||schema?.parameters||schema||{};
  const list=el('div',undefined,'tool-params'),properties=normalized.properties||{},required=new Set(normalized.required||[]);
  for(const [name,value] of entries){
    const row=el('div',undefined,'tool-param'),description=properties[name]?.description;
    const label=el('span',name,'param-name'+(description?' has-description':''));
    if(description){
      row.classList.add('has-description');label.dataset.description=description;label.tabIndex=0;label.setAttribute('aria-label',`${name}：${description}`);
    }
    if(required.has(name))label.append(el('span','*','param-required'));
    const valueNode=parameterValue(value);row.append(label,valueNode);list.append(row);
    if(collapseLong)collapseLongParameter(row,valueNode,value);
  }
  return list;
}
function toolCallsBlock(parent,calls,schemas){
  if(!calls?.length)return;
  const group=el('div',undefined,'tool-calls');
  calls.forEach(call=>{
    const item=el('details',undefined,'tool-call'),summary=el('summary'),body=el('div',undefined,'tool-call-body');
    const name=call.name||call.function?.name||'unknown_tool',schema=schemas?.[name];summary.append(describe(el('span',name,'tool-name'),schema?.description));
    body.append(el('div',_('callParameters'),'tool-caption'),toolParameters(parseToolParams(call),schema));
    const raw=call.raw??call.raw_str??call,rawBlock=el('details',undefined,'raw-json');rawBlock.append(el('summary',_('rawJson')),el('pre',pretty(raw)));body.append(rawBlock);
    item.append(summary,body);group.append(item);
  });
  parent.append(group);
}
function usageTotal(values){return Object.values(values||{}).reduce((total,value)=>total+(Number(value)||0),0)}
function formatMagnitude(value){
  const [scale,suffix]=value>=1e6?[1e6,'M']:value>=1e3?[1e3,'K']:[1,''];
  return new Intl.NumberFormat(currentLocale,{maximumFractionDigits:2}).format(value/scale)+suffix;
}
function formatTokens(value){return formatMagnitude(value)+' tokens'}
function formatMoney(value){return '$'+(value===0?'0':value<.01?value.toPrecision(3):value.toFixed(3))}
function usageSummary(step,total){
  const stepTokens=usageTotal(step?.token),totalTokens=usageTotal(total?.token);
  const stepMoney=usageTotal(step?.price),totalMoney=usageTotal(total?.price);
  if(!stepTokens&&!totalTokens&&!stepMoney&&!totalMoney)return '';
  return _('usageSummary',{stepTokens:formatTokens(stepTokens),stepMoney:formatMoney(stepMoney),totalTokens:formatTokens(totalTokens),totalMoney:formatMoney(totalMoney)});
}
function cumulativeUsage(payload){
  const supplied=payload.cumulative_usage,step=payload.usage||{};
  if(supplied&&usageTotal(supplied.token)>=usageTotal(step.token)&&usageTotal(supplied.price)>=usageTotal(step.price)){
    observedUsage=supplied;return observedUsage;
  }
  const coord=payload.coord||{},key=[coord.R,coord.C,coord.L].join(':');
  if(!seenUsageSteps.has(key)){
    seenUsageSteps.add(key);
    for(const kind of ['token','price'])for(const [name,value] of Object.entries(payload.usage?.[kind]||{}))observedUsage[kind][name]=(observedUsage[kind][name]||0)+(Number(value)||0);
  }
  return observedUsage;
}
function cumulativeDataUsage(payload){
  const key=String(payload.turn??seenDataUsageTurns.size+1);
  if(!seenDataUsageTurns.has(key)){
    seenDataUsageTurns.add(key);
    for(const kind of ['token','price'])for(const [name,value] of Object.entries(payload.usage?.[kind]||{}))observedDataUsage[kind][name]=(observedDataUsage[kind][name]||0)+(Number(value)||0);
  }
  return observedDataUsage;
}
function rclCoord(coord){return coord&&coord.R!==undefined&&coord.C!==undefined&&coord.L!==undefined?{R:coord.R,C:coord.C,L:coord.L}:null}
function contextKey(coord){const value=rclCoord(coord);return value?[value.R,value.C,value.L].join(':'):''}
function contextLink(text,coord,nodeId='',runId=''){
  const link=el('span',text,'meta-coord context-link');link.tabIndex=0;link.setAttribute('role','button');link.title=_('contextLinkTitle');
  const open=()=>showContextAt(coord,nodeId,runId);link.onclick=open;link.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open()}};return link;
}
function dataContextKey(turn){return 'data:'+String(turn)}
function dataContextLink(turn){
  const link=el('span',_('dataAgentTurn',{count:turn}),'meta-coord context-link');link.tabIndex=0;link.setAttribute('role','button');link.title=_('contextLinkTitle');
  const open=()=>showDataContextAt(turn);link.onclick=open;link.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open()}};return link;
}
function contextPayloadStats(payload){
  const messages=Array.isArray(payload?.messages)?payload.messages:[],characters=messages.reduce((total,message)=>{const content=message?.content;return total+(typeof content==='string'?content.length:pretty(content??'').length)},0);
  return _('contextStats',{count:messages.length,characters:formatMagnitude(characters)});
}
function renderDataContextEventCard(e,feed){
  const p=e.payload||{},card=el('article',undefined,'event data_context'),meta=el('div',undefined,'meta'),time=el('span',new Date(Number(e.timestamp)*1000).toLocaleTimeString(currentLocale),'meta-time');card.dataset.started=e.timestamp;
  meta.append(eventBadge('context',_('eventContext')));if(p.turn)meta.append(dataContextLink(p.turn));meta.append(el('span',contextPayloadStats(p),'context-size'),time);card.append(meta);feed.append(card);feed.hidden=false;
}
function evaluatorContextKey(turn){return 'evaluator:'+String(turn)}
function evaluatorContextLink(turn){
  const link=el('span',_('dataAgentTurn',{count:turn}),'meta-coord context-link');link.tabIndex=0;link.setAttribute('role','button');link.title=_('contextLinkTitle');
  const open=()=>showEvaluatorContextAt(turn);link.onclick=open;link.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open()}};return link;
}
async function showContextAt(coord,nodeId='',runId=''){
  const normalized=rclCoord(coord),key=contextKey(normalized);if(!key)return;
  selectedContextKey=key;selectCenterTab('context');let payload=contextHistory.get(key);
  if(!payload&&nodeId){
    try{const record=await api('/api/runs/'+encodeURIComponent(runId||treeRun)+'/records/'+encodeURIComponent(nodeId));if(Array.isArray(record.detail?.prompt)){payload={coord:normalized,messages:record.detail.prompt};contextHistory.set(key,payload)}}catch(error){notice(_('contextLoadFailed',{message:error.message}))}
  }
  if(payload)renderContext(payload);else notice(_('contextNotFound',normalized));
}
function showDataContextAt(turn){
  const key=dataContextKey(turn),payload=contextHistory.get(key);selectedContextKey=key;selectCenterTab('context');
  if(payload)renderContext(payload);else notice(_('dataContextNotFound',{count:turn}));
}
function showEvaluatorContextAt(turn){
  const key=evaluatorContextKey(turn),payload=contextHistory.get(key);selectedContextKey=key;selectCenterTab('context');
  if(payload)renderContext(payload);else notice(_('evaluatorContextNotFound',{count:turn}));
}
function updateStreamProgress(node){
  const now=performance.now()/1000,started=Number(node.dataset.started)||now,status=_(node.dataset.status||'modelWaiting'),duration=formatDuration(now-started);
  const label=node.querySelector('.stream-progress-label');if(label)label.textContent=_('modelProgress',{status,duration});
}
function streamProgress(started,status='modelWaiting'){
  const progress=el('div',undefined,'stream-progress');progress.dataset.started=started;progress.dataset.status=status;progress.append(el('span',undefined,'stream-spinner'),el('span','', 'stream-progress-label'));updateStreamProgress(progress);return progress;
}
setInterval(()=>document.querySelectorAll('.stream-progress').forEach(updateStreamProgress),500);
function appendTruncationNotice(card,payload){
  if(!['length','max_tokens','max_output_tokens','MAX_TOKENS'].includes(payload.finish_reason)||card.querySelector('.truncation-notice'))return;
  card.append(el('div',currentLocale.startsWith('zh')?'本轮输出达到上限，已保留已有内容。可发送“继续”，或在设置中调整输出上限后继续。':'Output limit reached. Partial output is preserved. Send “continue”, or adjust the output limit in settings before continuing.','truncation-notice'));
}
function settleAssistantCards(cards,error){
  for(const [responseId,card] of cards){card.querySelector('.stream-progress')?.remove();if(error&&!card.querySelector('.stream-error'))card.append(el('pre',error,'stream-error'));assistantStreamStates.delete(responseId)}
  cards.clear();
}
function renderAssistantStreamEvent(e,{feed,cards,dataMode=false,contextScope='data'}){
  const p=e.payload||{},responseId=p.response_id;if(!responseId)return;
  const follow=feed.scrollHeight-feed.scrollTop-feed.clientHeight<100;
  if(feed.querySelector('p.muted'))feed.replaceChildren();if(!dataMode)$('welcome')?.remove();
  let state=assistantStreamStates.get(responseId)||{started:e.timestamp,statusStarted:performance.now()/1000,content:'',reasoning:'',tool_calls:[],tool_schemas:p.tool_schemas||{},coord:p.coord,turn:p.turn,provider:p.provider,model:p.model,status:'modelWaiting'};
  const nextStatus=p.type==='retry'?'modelRetrying':p.type==='delta'||p.type==='complete'?'modelStreaming':state.status;if(nextStatus!==state.status){state.status=nextStatus;state.statusStarted=performance.now()/1000}
  for(const key of ['content','reasoning','tool_calls','tool_schemas','coord','turn','provider','model'])if(p[key]!==undefined)state[key]=p[key];
  if(p.message&&!state.reasoning){const m=p.message;state.reasoning=m.reasoning||m.reasoning_content||(m.reasoning_details||[]).map(item=>item?.text||'').join('')}
  assistantStreamStates.set(responseId,state);
  let card=cards.get(responseId);
  if(!card){
    card=el('article',undefined,'event assistant '+e.kind);card.dataset.started=state.started;cards.set(responseId,card);feed.append(card);
    const meta=el('div',undefined,'meta'),metaTime=el('span',new Date(Number(state.started)*1000).toLocaleTimeString(currentLocale),'meta-time');meta.append(eventBadge('agent',_('eventAgent')));
    if(dataMode&&state.turn)meta.append(contextScope==='evaluator'?evaluatorContextLink(state.turn):dataContextLink(state.turn));
    else if(state.coord)meta.append(el('span',Object.entries(state.coord).map(([key,value])=>key+value).join(' · '),'meta-coord'));
    const badge=modelBadge(state.provider,state.model);if(badge)meta.append(badge);meta.append(metaTime);card.append(meta,streamProgress(state.statusStarted,state.status),agentOutputBlock('','stream-reasoning'),agentOutputBlock('','stream-content'),el('div',undefined,'stream-tool-calls'));
  }
  // Keep the same nodes and scroll positions across deltas; never replace the whole card.
  for(const key of ['reasoning','content']){const node=card.querySelector('.stream-'+key);node.hidden=!state[key];renderAgentOutput(node,state[key]||'')}
  const holder=card.querySelector('.stream-tool-calls'),signature=JSON.stringify([state.tool_calls,state.tool_schemas]);
  if(holder.dataset.signature!==signature){holder.dataset.signature=signature;holder.replaceChildren();if(state.tool_calls?.length)toolCallsBlock(holder,state.tool_calls,state.tool_schemas)}
  const failed=e.kind.endsWith('_error')||p.type==='failed',terminal=e.kind.endsWith('_error')||['assistant','data_assistant','evaluator_assistant'].includes(e.kind);
  const progress=card.querySelector('.stream-progress');
  if(failed||terminal){progress?.remove();if(failed){card.classList.add('tool_error');if(!card.querySelector('.stream-error'))card.append(el('pre',p.error||_('failed'),'stream-error'))}appendTruncationNotice(card,p);if(terminal){cards.delete(responseId);assistantStreamStates.delete(responseId)}}
  else if(progress){progress.dataset.status=state.status;progress.dataset.started=state.statusStarted;updateStreamProgress(progress)}
  if(follow)feed.scrollTop=feed.scrollHeight;else if(!dataMode)$('follow').hidden=false;
}
function trackActivity(e) {
  const p=e.payload||{};
  if(p.coord)lastCoord=p.coord
  const phases={context:'model',assistant:'processing',tool_start:'tool',tool_result:'processing',tool_error:'processing',topk:'processing'};
  if(e.kind==='activity')inferredActivity={...p,since:e.timestamp};
  else if(phases[e.kind])inferredActivity={phase:phases[e.kind],tool:p.call?.name,since:e.timestamp};
  if(e.kind==='context'){latestContext=p;const key=contextKey(p.coord);if(key)contextHistory.set(key,p)}
}
function renderEventPreviewNotice(event,feed,scope){
  if(!event.transport?.truncated||feed.querySelector('[data-preview-sequence="'+event.seq+'"]'))return;
  const card=el('article',undefined,'event event_generic'),meta=el('div',undefined,'meta'),link=el('a',currentLocale==='en'?'Download full event':'下载完整事件','context-link');
  card.dataset.previewSequence=String(event.seq);meta.append(el('span',currentLocale==='en'?'Large event: showing a limited preview.':'该事件较大，当前显示受限预览。','small muted'));
  const routes={search:'/api/control/events/',data:'/api/data/agent/events/',evaluator:'/api/evaluator/agent/events/'};
  link.href=conversationUrl(routes[scope]+encodeURIComponent(event.seq));link.download=scope+'-event-'+event.seq+'.json';meta.append(link);card.append(meta);feed.hidden=false;feed.append(card);
}
function previewAwareContextEvent(event,scope){
  return event.kind==='context'&&event.transport?.truncated?{...event,payload:{...event.payload,timeline_preview:{sequence:event.seq,scope}}}:event;
}
function renderEvent(e) {
  renderEventPreviewNotice(e,$('feed'),'search');e=previewAwareContextEvent(e,'search');
  if(['execution_completed','execution_failed'].includes(e.kind))settleAssistantCards(assistantCards,e.kind==='execution_failed'?(e.payload?.error||e.payload?.result?.error||_('failed')):null);
  if(e.kind==='prompt_added'){renderPromptAdded(e,$('feed'));return}
  if(e.kind==='state_changed')e={...e,kind:'lifecycle',payload:{state:e.payload?.current}};
  else if(e.kind==='command_received')e={...e,kind:'control',payload:e.payload};
  else if(e.kind==='execution_completed'||e.kind==='execution_failed')e={...e,kind:'lifecycle',payload:{state:e.payload?.status||(e.kind==='execution_failed'?'failed':'completed'),result:e.payload?.result||e.payload}};
  else e=scopedTimelineEvent(e);
  if(['assistant_start','assistant_delta','assistant_error'].includes(e.kind)){
    renderAssistantStreamEvent(e,{feed:$('feed'),cards:assistantCards});return;
  }
  const p=e.payload||{};trackActivity(e);
  if(e.kind==='topk_updated')renderTopk(p.records||[]);
  const feed=$('feed'),follow=feed.scrollHeight-feed.scrollTop-feed.clientHeight<100;
  $('welcome')?.remove();
  const key=p.call?.id||p.call?.name;
  let card=e.kind==='tool_result'||e.kind==='tool_error'?toolCards.get(key):e.kind==='assistant'&&p.response_id?assistantCards.get(p.response_id):null;
  const updating=Boolean(card);
  if(!card){card=el('article',undefined,'event '+e.kind);card.dataset.started=e.timestamp}
  card.className='event '+e.kind;
  card.replaceChildren();
  const meta=el('div',undefined,'meta'),metaTime=el('span',new Date(Number(card.dataset.started)*1000).toLocaleTimeString(currentLocale),'meta-time');
  meta.append(eventKind(e.kind,p.result?.ok===false),metaTime);card.append(meta);
  if(e.kind==='user') {
    previewBlock(card,p.content||'','message-preview-block');
  } else if(e.kind==='context') {
    const coord=Object.entries(p.coord||{}).map(([k,v])=>k+v).join(' · '),messages=Array.isArray(p.messages)?p.messages:[],characters=messages.reduce((total,message)=>{const content=message?.content;return total+(typeof content==='string'?content.length:pretty(content??'').length)},0),size=messages.length?_('contextStats',{count:messages.length,characters:formatMagnitude(characters)}):'';
    const status=[coord,size,_('contextWaiting')].filter(Boolean).join(' · '),link=contextLink(status,p.coord);
    metaTime.before(markContextStatus(link,coord,messages.length,formatMagnitude(characters)));
  } else if(e.kind==='assistant') {
    if(p.coord)metaTime.before(contextLink(Object.entries(p.coord).map(([k,v])=>k+v).join(' · '),p.coord));const badge=modelBadge(p.provider,p.model);if(badge)metaTime.before(badge);
    const m=p.message||{},details=Array.isArray(m.reasoning_details)?m.reasoning_details:[];
    const reasoning=m.reasoning||m.reasoning_content||details.map(x=>x?.text||'').join('');
    reasoningBlock(card,reasoning);
    if(p.content)card.append(agentOutputBlock(p.content,'message-preview-block'));
    toolCallsBlock(card,p.tool_calls,p.tool_schemas);appendTruncationNotice(card,p);
    const cumulative=cumulativeUsage(p),usage=usageSummary(p.usage,cumulative);if(usage)card.append(el('div',usage,'usage-line'));
    if(p.response_id){assistantCards.delete(p.response_id);assistantStreamStates.delete(p.response_id)}
  } else if(e.kind.startsWith('tool_')) {
    const failed=e.kind==='tool_error';
    const pending=e.kind==='tool_start';
    const duration=p.duration_seconds??Math.max(0,e.timestamp-Number(card.dataset.started));
    metaTime.before(describe(el('span',p.call?.name||'Tool','tool-event-name'),p.tool_schema?.description),timelineToolState(pending,failed,duration));
    card.append(el('div',_('callParameters'),'tool-caption'));
    const parameters=toolParameters(parseToolParams(p.call||{}),p.tool_schema,true);parameters.classList.add('tool-event-params');card.append(parameters);
    if(!pending){
      const resultText=p.result?.result_str||p.error||_('toolNoText');card.append(el('div',_(failed?'errorInfo':'result'),'tool-caption'));previewBlock(card,resultText,'tool-result-block');
      if(p.result?.result!==undefined){const raw=el('details',undefined,'raw-json tool-result-raw');raw.append(el('summary',_('rawJson')),el('pre',pretty(p.result.result)));card.append(raw)}
    }
    if(pending)toolCards.set(key,card);else toolCards.delete(key);
  } else if(e.kind==='lifecycle') {
    metaTime.before(el('span',_(p.state),'meta-coord'));
    const bestIndex=p.result?.best_candidate,bestCandidate=Number.isInteger(bestIndex)?p.result?.candidates?.[bestIndex]:null;
    if(bestCandidate?.formula)card.append(el('div',bestCandidate.formula,'formula'));
    if(p.result?.error)card.append(el('pre',p.result.error));disclosure(card,_('fullRunResult'),p.result);
  } else if(e.kind==='control') {
    const actionLabel={pause:_('safeStopNotice'),force_pause:_('forceStopNotice'),next_c:_('controlNextC'),next_r:_('controlNextR')}[p.action]||p.action||_('controlAction');
    metaTime.before(el('span',actionLabel,'meta-coord'));if(p.message||p.error)previewBlock(card,p.message||p.error,'control-message');
  } else {eventContent(card,meta,metaTime,compactEventContent(e))}
  if(!updating)feed.append(card);
  while(feed.children.length>1000)feed.firstChild.remove();
  if(follow)feed.scrollTop=feed.scrollHeight;else $('follow').hidden=false;
}
function renderDataEvent(e){
  renderEventPreviewNotice(e,$('data-agent-feed'),'data');e=previewAwareContextEvent(e,'data');
  if(e.kind==='prompt_added'){renderPromptAdded(e,$('data-agent-feed'),'data');return}
  if(['state_changed','command_received','workspace_changed','settings_applied','settings_failed'].includes(e.kind)){renderGenericEventCard(e,$('data-agent-feed'));return}
  e=scopedTimelineEvent(e,'data');
  const p=e.payload||{},feed=$('data-agent-feed'),follow=feed.scrollHeight-feed.scrollTop-feed.clientHeight<100;
  if(e.kind==='data_context'){
    if(p.turn){const payload={...p,agent_scope:'data'};contextHistory.set(dataContextKey(p.turn),payload);latestContext=payload}
    renderDataContextEventCard(e,feed);
    return;
  }
  if(e.kind==='data_error')settleAssistantCards(dataAssistantCards,p.error||_('failed'));
  if(e.kind==='data_complete'){
    if(p.status==='stopped')for(const card of dataAssistantCards.values())card.append(el('div',_('dataAgentStopped'),'small muted'));
    settleAssistantCards(dataAssistantCards);
    return;
  }
  feed.hidden=false;
  if(['data_assistant_start','data_assistant_delta','data_assistant_error'].includes(e.kind)){
    renderAssistantStreamEvent(e,{feed,cards:dataAssistantCards,dataMode:true});return;
  }
  const isTool=['data_tool_start','data_tool_result','data_tool_error'].includes(e.kind),failed=e.kind==='data_error'||e.kind==='data_tool_error',resultFailed=p.result?.ok===false,key=p.call?.id||p.call?.name;
  let card=['data_tool_result','data_tool_error'].includes(e.kind)?dataToolCards.get(key):e.kind==='data_assistant'&&p.response_id?dataAssistantCards.get(p.response_id):null;
  const updating=Boolean(card);
  if(!card){card=el('article');card.dataset.started=e.timestamp}
  card.className='event '+(e.kind==='data_assistant'?'assistant ':e.kind==='data_user'?'data_user ':isTool?(failed?'tool_error ':e.kind==='data_tool_start'?'tool_start ':'tool_result '):'event_generic ')+e.kind;
  unobservePreviewBlocks(card);card.replaceChildren();
  const meta=el('div',undefined,'meta'),metaTime=el('span',new Date(Number(card.dataset.started)*1000).toLocaleTimeString(currentLocale),'meta-time');
  if(e.kind==='data_user')meta.append(eventBadge('user',_('eventUser')),metaTime);
  else if(e.kind==='data_assistant'){
    meta.append(eventBadge('agent',_('eventAgent')));
    if(p.turn)meta.append(dataContextLink(p.turn));
    const badge=modelBadge(p.provider,p.model);if(badge)meta.append(badge);meta.append(metaTime);
  } else if(isTool){
    meta.append(eventBadge('tool',_(failed?'eventToolError':'eventTool'),failed||resultFailed));
    const duration=Math.max(0,e.timestamp-Number(card.dataset.started)),pending=e.kind==='data_tool_start';
    meta.append(describe(el('span',p.call?.name||'Tool','tool-event-name'),p.tool_schema?.description),timelineToolState(pending,failed,duration),metaTime);
  } else meta.append(eventBadge('event',e.kind),metaTime);
  card.append(meta);
  if(e.kind==='data_user')previewBlock(card,p.content||'','message-preview-block');
  else if(e.kind==='data_assistant'){
    const message=p.message||{},details=Array.isArray(message.reasoning_details)?message.reasoning_details:[],reasoning=message.reasoning||message.reasoning_content||details.map(item=>item?.text||'').join('');
    reasoningBlock(card,reasoning);if(p.content)previewBlock(card,p.content,'message-preview-block',true);toolCallsBlock(card,p.tool_calls,p.tool_schemas);appendTruncationNotice(card,p);
    const usage=usageSummary(p.usage,cumulativeDataUsage(p));if(usage)card.append(el('div',usage,'usage-line'));
    if(p.response_id){dataAssistantCards.delete(p.response_id);assistantStreamStates.delete(p.response_id)}
  } else if(isTool){
    card.append(el('div',_('callParameters'),'tool-caption'));const parameters=toolParameters(parseToolParams(p.call||{}),p.tool_schema,true);parameters.classList.add('tool-event-params');card.append(parameters);
    if(e.kind==='data_tool_result'||e.kind==='data_tool_error'){
      card.append(el('div',_(failed?'errorInfo':'result'),'tool-caption'));previewBlock(card,p.result?.result_str||_('toolNoText'),'tool-result-block');
      if(p.result?.result!==undefined){const raw=el('details',undefined,'raw-json tool-result-raw');raw.append(el('summary',_('rawJson')),el('pre',pretty(p.result.result)));card.append(raw)}
    }
    if(e.kind==='data_tool_start')dataToolCards.set(key,card);else dataToolCards.delete(key);
  } else previewBlock(card,p.error||pretty(p),'message-preview-block');
  if(!updating)feed.append(card);if(follow)feed.scrollTop=feed.scrollHeight;
}
function renderEvaluatorEvent(e){
  renderEventPreviewNotice(e,$('evaluator-agent-feed'),'evaluator');e=previewAwareContextEvent(e,'evaluator');
  if(e.kind==='prompt_added'){renderPromptAdded(e,$('evaluator-agent-feed'),'evaluator');return}
  if(['state_changed','command_received','workspace_changed','settings_applied','settings_failed'].includes(e.kind)){renderGenericEventCard(e,$('evaluator-agent-feed'));return}
  e=scopedTimelineEvent(e,'evaluator');
  const p=e.payload||{},feed=$('evaluator-agent-feed');feed.hidden=false;
  if(e.kind==='evaluator_context'){
    if(p.turn){const payload={...p,agent_scope:'evaluator'};contextHistory.set(evaluatorContextKey(p.turn),payload);latestContext=payload}
    renderGenericEventCard(e,feed);
    return;
  }
  if(e.kind==='evaluator_user'){appendEvaluatorAgentEvent('user',p,e.timestamp);return}
  if(e.kind==='evaluator_error'){settleAssistantCards(evaluatorAssistantCards,p.error||_('failed'));renderGenericEventCard(e,feed);return}
  if(e.kind==='evaluator_complete'){
    settleAssistantCards(evaluatorAssistantCards);
    if(p.status==='stopped')feed.append(el('div',_('evaluatorAgentStopped'),'small muted'));return;
  }
  if(['evaluator_assistant_start','evaluator_assistant_delta','evaluator_assistant_error'].includes(e.kind)){
    renderAssistantStreamEvent(e,{feed,cards:evaluatorAssistantCards,dataMode:true,contextScope:'evaluator'});return;
  }
  if(e.kind==='evaluator_assistant'){
    renderAssistantStreamEvent(e,{feed,cards:evaluatorAssistantCards,dataMode:true,contextScope:'evaluator'});
    return;
  }
  if(e.kind==='evaluator_tool_start')appendEvaluatorAgentEvent('tool_start',p,e.timestamp);
  if(e.kind==='evaluator_tool_result')appendEvaluatorAgentEvent('tool_result',p,e.timestamp);
  if(e.kind==='evaluator_tool_error')appendEvaluatorAgentEvent('tool_error',p,e.timestamp);
}
async function loadCommittedContext(context=null){
  const generation=serverSessionGeneration,selectionVersion=selectionSaveVersion;
  context=context||await api('/api/data/context');
  // A slow snapshot must not replace role edits or a newer committed selection.
  if(generation!==serverSessionGeneration||selectionVersion!==selectionSaveVersion||selectionSaveInFlight||selectionSavedVersion<selectionSaveVersion)return;
  if(useCommittedContext&&(context.revision||0)<=renderedDataRevision)return;
  renderedDataRevision=context.revision||0;
  if(!context.columns?.length){useCommittedContext=false;dataPreview=null;dataPreviewGroups=[];selectedDataPreviewGroup='';dataGroupPreview=null;plotPreview=null;plotPreviewToken+=1;variableOrder=[];variableRoles={};variableDescriptions={};dataChannels={x:'',y:'',hue:'',size:''};distributionChannels={x:'',y:''};heatmapChannels={row:[],column:[],color:'',z:''};heatmapPreview=null;heatmapPreviewToken+=1;$('target').value='';renderVariableRoleTable();renderPlotVariablePalette();renderPlotSlots();renderActivePlot();renderDataPreviewGroupPicker();renderDataTable();renderWorkflowNextControls();return}
  useCommittedContext=true;variableDescriptions={...(context.variable_descriptions||{})};$('target').value=context.target||'';
  const previewColumns=context.preview_columns||context.columns,numeric=Object.fromEntries(previewColumns.map(column=>[column,context.data.every(row=>row[column]===null||Number.isFinite(Number(row[column])))]));
  dataPreviewGroups=context.preview_groups||[];dataGroupPreview=null;dataPreview={columns:context.columns,previewColumns,columnKinds:context.column_kinds||{},variableAxes:Object.fromEntries(Object.entries(context.variables||{}).map(([name,spec])=>[name,spec.axes||[]])),numeric,rows:context.data,truncated:context.truncated,target:context.target||'',features:context.features||[],path:''};configureDataPreview();
  renderWorkflowNextControls();
}
async function hydrateCommittedContext(){
  if(contextHydrationPromise)return contextHydrationPromise;
  const generation=serverSessionGeneration,promise=(async()=>{
    let context=await api('/api/data/context',undefined,'GET');
    if(!context.columns?.length){
      try{await api('/api/data/context/reload',{})}
      catch(error){if(!String(error?.message||error).includes('context.data/manifest.json does not exist'))throw error}
      context=await api('/api/data/context',undefined,'GET');
    }
    if(generation!==serverSessionGeneration)return;
    await loadCommittedContext(context);
  })();
  contextHydrationPromise=promise;try{return await promise}finally{if(contextHydrationPromise===promise)contextHydrationPromise=null}
}
async function refreshCommittedContext(){
  const button=$('data-refresh'),label=$('data-refresh-label');button.disabled=true;label.textContent=_('refreshingData');
  try{await loadCommittedContext()}finally{button.disabled=false;label.textContent=_('refreshData')}
}
async function reloadCommittedContext(){
  const button=$('data-insights-refresh'),label=$('data-insights-refresh-label');button.disabled=true;label.textContent=_('refreshingData');
  try{await api('/api/data/context/reload',{});await loadCommittedContext()}finally{button.disabled=false;label.textContent=_('refreshData')}
}
function formatDuration(seconds){seconds=Math.floor(Math.max(0,seconds));return seconds<60?_('seconds',{count:seconds}):_('minutesSeconds',{minutes:Math.floor(seconds/60),seconds:seconds%60})}
function renderActivity() {
  if(!session)return;
  const stale=Date.now()-lastStatusAt>12000;
  $('connection').textContent=_(stale?'connectionLost':'connected');
  $('connection').title=_('lastSync',{time:lastStatusAt?new Date(lastStatusAt).toLocaleTimeString(currentLocale):_('neverConnected')});
  if(lastEventsAt&&Date.now()-lastEventsAt>15000&&lastStatusAt&&!stale)$('connection').textContent=_('connectionDelayed');
}

function renderContext(p){
  const sig=JSON.stringify(p);if(sig===contextSignature)return;contextSignature=sig;const host=$('context');for(const block of host.querySelectorAll('.reasoning-block'))previewObserver.unobserve(block);host.replaceChildren();
  if(p.timeline_preview)renderEventPreviewNotice({seq:p.timeline_preview.sequence,transport:{truncated:true}},host,p.timeline_preview.scope);
  const messages=Array.isArray(p.messages)?p.messages:[],characters=messages.reduce((total,message)=>{const content=message?.content;return total+(typeof content==='string'?content.length:pretty(content??'').length)},0),coord=Object.entries(p.coord||{}).map(([key,value])=>key+value).join(' · '),location=p.agent_scope==='data'?_('dataAgentTitle')+' · '+_('dataAgentTurn',{count:p.turn}):coord;
  const overview=el('div',undefined,'context-overview');overview.append(el('strong',_('sentContext')));if(location)overview.append(el('span',location));overview.append(el('span',_('contextStats',{count:messages.length,characters:formatMagnitude(characters)}),'context-size'));host.append(overview);
  const roleInfo={system:['settings',_('systemPrompt')],developer:['settings',_('developerPrompt')],user:['user',_('userPrompt')],assistant:['agent',_('agent')],tool:['tool',_('toolResult')]};
  messages.forEach((message,index)=>{
    const role=String(message.role||'message').toLowerCase(),info=roleInfo[role]||['event',_('message')],card=el('article',undefined,'event context-message '+role),meta=el('div',undefined,'meta'),label=[info[1],message.name].filter(Boolean).join(' · ');
    meta.append(eventBadge(info[0],label),el('span',label,'meta-coord'),el('span','#'+String(index+1).padStart(2,'0'),'meta-time'));card.append(meta);
    if(message.content!==undefined&&message.content!==null&&message.content!=='')previewBlock(card,pretty(message.content),'context-message-body');
    toolCallsBlock(card,message.tool_calls);
    const raw=el('details',undefined,'raw-json context-raw');raw.append(el('summary',_('rawMessage')),el('pre',pretty(message)));card.append(raw);host.append(card);
  });
  if(!messages.length)host.append(el('p',_('contextEmpty'),'muted small'));
}
function candidateObjectives(record){const numeric=value=>typeof value==='number'&&Number.isFinite(value)?value:NaN,complexity=numeric(record.complexity),mse=numeric(record.mse),rmse=numeric(record.rmse),r2=numeric(record.r2),error=Number.isFinite(mse)?mse:Number.isFinite(rmse)?rmse**2:Number.isFinite(r2)?-r2:NaN;return{complexity,error}}
function paretoFront(records){const valid=records.filter(record=>{const value=candidateObjectives(record);return Number.isFinite(value.complexity)&&Number.isFinite(value.error)});return valid.filter(record=>{const value=candidateObjectives(record);return !valid.some(other=>{if(other===record)return false;const candidate=candidateObjectives(other);return candidate.complexity<=value.complexity&&candidate.error<=value.error&&(candidate.complexity<value.complexity||candidate.error<value.error)})})}
function tokenizeCandidateFormula(source){
  const tokens=[];let index=0;
  while(index<source.length){
    if(/\s/.test(source[index])){index+=1;continue}
    const number=source.slice(index).match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/);if(number){tokens.push({type:'number',value:number[0]});index+=number[0].length;continue}
    const identifier=source.slice(index).match(/^[A-Za-z_]\w*/);if(identifier){tokens.push({type:'identifier',value:identifier[0]});index+=identifier[0].length;continue}
    if(source[index]==="'"||source[index]==='"'){const quote=source[index++];let value='';while(index<source.length&&source[index]!==quote){if(source[index]==='\\'&&index+1<source.length)index+=1;value+=source[index++]}if(source[index]!==quote)throw Error('Unclosed string');index+=1;tokens.push({type:'string',value});continue}
    const operator=source.startsWith('**',index)?'**':source[index];if(!'+-*/(),[]='.includes(operator)&&operator!=='**')throw Error('Unsupported token');tokens.push({type:'operator',value:operator});index+=operator.length;
  }
  return tokens;
}
function parseCandidateFormula(source){
  const tokens=tokenizeCandidateFormula(source);let position=0;const peek=(offset=0)=>tokens[position+offset],take=()=>tokens[position++],expect=value=>{if(peek()?.value!==value)throw Error('Expected '+value);return take()};
  const primary=()=>{
    if(peek()?.value==='+'||peek()?.value==='-'){const operator=take().value;return{kind:'unary',operator,value:primary()}}
    const token=take();if(!token)throw Error('Expected expression');let node;
    if(token.value==='('){node={kind:'group',value:expression()};expect(')')}
    else if(['number','identifier','string'].includes(token.type))node={kind:token.type,value:token.value};
    else throw Error('Expected value');
    while(peek()?.value==='['||peek()?.value==='('){
      if(peek().value==='['){take();const indices=[];if(peek()?.value!==']')do{indices.push(expression())}while(peek()?.value===','&&take());expect(']');node={kind:'index',value:node,indices};continue}
      take();const args=[],keywords={};if(peek()?.value!==')')do{if(peek()?.type==='identifier'&&peek(1)?.value==='='){const name=take().value;take();keywords[name]=expression()}else args.push(expression())}while(peek()?.value===','&&take());expect(')');node={kind:'call',callee:node,args,keywords};
    }
    return node;
  };
  const precedence={'+':10,'-':10,'*':20,'/':20,'**':30};
  const expression=(minimum=0)=>{let left=primary();while(precedence[peek()?.value]>=minimum){const operator=take().value,level=precedence[operator],right=expression(operator==='**'?level:level+1);left={kind:'binary',operator,left,right}}return left};
  const tree=expression();if(position!==tokens.length)throw Error('Unexpected token');return tree;
}
function candidateLatexIdentifier(value){const greek={alpha:'\\alpha',beta:'\\beta',gamma:'\\gamma',delta:'\\delta',theta:'\\theta',lambda:'\\lambda',mu:'\\mu',pi:'\\pi',rho:'\\rho',sigma:'\\sigma',phi:'\\phi',omega:'\\omega'};if(greek[value])return greek[value];if(/^[A-Za-z]$/.test(value))return value;return '\\mathrm{'+value.replace(/_/g,'\\_')+'}'}
function candidateLatexNumber(value){const number=Number(value);if(!Number.isFinite(number))return value;if(/^\d+$/.test(value))return value;const text=candidateFormulaNumberMode==='scientific'?number.toExponential(candidateFormulaDigits):number.toFixed(candidateFormulaDigits),scientific=text.match(/^(.+?)e([+-]?\d+)$/i);return scientific?scientific[1]+' \\times 10^{'+Number(scientific[2])+'}':text}
function candidateAstLatex(node,parentPrecedence=0){
  if(node.kind==='number')return candidateLatexNumber(node.value);
  if(node.kind==='identifier')return candidateLatexIdentifier(node.value);
  if(node.kind==='string')return '\\text{'+node.value.replace(/[{}]/g,'')+'}';
  if(node.kind==='group')return '\\left('+candidateAstLatex(node.value)+'\\right)';
  if(node.kind==='index')return candidateAstLatex(node.value)+'_{'+node.indices.map(item=>candidateAstLatex(item)).join(',')+'}';
  if(node.kind==='unary'){const rendered=node.operator+candidateAstLatex(node.value,25);return parentPrecedence>25?'\\left('+rendered+'\\right)':rendered}
  if(node.kind==='call'){
    const calleeName=node.callee.kind==='identifier'?node.callee.value:'';
    if(calleeName==='param'){const value=node.keywords.value||node.args[1];if(value)return candidateAstLatex(value);const name=node.args[0];return name?.kind==='string'?candidateLatexIdentifier(name.value):'\\operatorname{param}'}
    if(calleeName==='grouped_param'){const name=node.keywords.name,group=node.args[0];return (name?.kind==='string'?candidateLatexIdentifier(name.value):'\\operatorname{grouped\\_param}')+(group?'_{'+candidateAstLatex(group)+'}':'')}
    if(node.callee.kind==='index'&&node.callee.value.kind==='identifier'&&node.callee.value.value==='sum'){const subscript=node.callee.indices.map(item=>candidateAstLatex(item)).join(','),relation=node.args[0]?candidateAstLatex(node.args[0]):'',body=node.args[1]?candidateAstLatex(node.args[1]):'';return '\\sum_{'+subscript+'} '+relation+(body?'\\,\\left('+body+'\\right)':'')}
    const functions={sin:'\\sin',cos:'\\cos',tan:'\\tan',asin:'\\arcsin',arcsin:'\\arcsin',acos:'\\arccos',arccos:'\\arccos',atan:'\\arctan',arctan:'\\arctan',exp:'\\exp',ln:'\\ln',log:'\\ln',lg:'\\log_{10}',log10:'\\log_{10}',log2:'\\log_{2}'};
    if(calleeName==='sqrt'&&node.args[0])return '\\sqrt{'+candidateAstLatex(node.args[0])+'}';
    if(calleeName==='abs'&&node.args[0])return '\\left|'+candidateAstLatex(node.args[0])+'\\right|';
    const callee=functions[calleeName]||'\\operatorname{'+(calleeName||'f').replace(/_/g,'\\_')+'}',argumentsLatex=[...node.args.map(item=>candidateAstLatex(item)),...Object.entries(node.keywords).map(([key,value])=>candidateLatexIdentifier(key)+'='+candidateAstLatex(value))].join(', ');return callee+'\\left('+argumentsLatex+'\\right)';
  }
  if(node.kind==='binary'){
    const level={'+':10,'-':10,'*':20,'/':20,'**':30}[node.operator],left=candidateAstLatex(node.left,level),right=candidateAstLatex(node.right,node.operator==='**'?level:level+1);let rendered;
    if(node.operator==='**')rendered='{'+left+'}^{'+candidateAstLatex(node.right)+'}';
    else if(node.operator==='/')rendered='\\frac{'+candidateAstLatex(node.left)+'}{'+candidateAstLatex(node.right)+'}';
    else if(node.operator==='*')rendered=left+' \\cdot '+right;
    else if(node.operator==='+'&&node.right.kind==='unary'&&node.right.operator==='-')rendered=left+' - '+candidateAstLatex(node.right.value,level+1);
    else rendered=left+' '+node.operator+' '+right;
    return level<parentPrecedence?'\\left('+rendered+'\\right)':rendered;
  }
  throw Error('Unsupported expression');
}
function candidateFormulaLatex(source){try{return candidateAstLatex(parseCandidateFormula(source))}catch{return null}}
function candidateFormulaNode(value){const source=value||_('noFormula'),node=el('div',undefined,'formula');if(candidateFormulaMode==='raw'){node.textContent=source;return node}const latex=candidateFormulaLatex(source);if(!latex){node.textContent=source;return node}if(candidateFormulaMode==='latex'){node.classList.add('latex-source');node.textContent=latex;return node}node.classList.add('formatted');node.title=source;node.append(texMath(latex,true));return node}
function renderCandidateNumberFormatControls(){const details=$('candidate-number-format');if(!details)return;details.hidden=candidateFormulaMode==='raw';if(details.hidden)details.open=false;const mode=$('candidate-number-mode'),digits=$('candidate-number-digits'),summary=$('candidate-number-summary');mode.options[0].textContent=_('decimalFormat');mode.options[1].textContent=_('scientificFormat');mode.value=candidateFormulaNumberMode;digits.value=String(candidateFormulaDigits);mode.setAttribute('aria-label',_('candidateNumberFormat'));digits.setAttribute('aria-label',_('candidateNumberDigits'));summary.textContent=candidateFormulaNumberMode==='scientific'?'1e':'0.'+('0'.repeat(Math.min(3,candidateFormulaDigits))||'0');summary.title=_('candidateNumberFormat')}
function renderCandidateFormulaMode(){const group=$('candidate-format');if(!group)return;group.setAttribute('aria-label',_('candidateFormulaDisplay'));for(const button of group.querySelectorAll('button')){const active=button.dataset.mode===candidateFormulaMode;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));button.textContent=_({raw:'candidateFormulaRaw',pretty:'candidateFormulaPretty',latex:'candidateFormulaLatex'}[button.dataset.mode])}renderCandidateNumberFormatControls()}
function mountCandidateFormulaControl(){const bar=document.querySelector('.candidate-bar'),group=el('div',undefined,'candidate-format');group.id='candidate-format';group.setAttribute('role','group');for(const mode of ['raw','pretty','latex']){const button=el('button');button.type='button';button.dataset.mode=mode;button.onclick=()=>{candidateFormulaMode=mode;localStorage.setItem('sr-harness-candidate-formula-mode',mode);renderTopk()};group.append(button)}const details=el('details',undefined,'candidate-number-format');details.id='candidate-number-format';const summary=el('summary','0.000');summary.id='candidate-number-summary';const panel=el('div',undefined,'candidate-number-format-panel'),modeLabel=el('label'),mode=el('select'),digitsLabel=el('label'),digits=document.createElement('input');mode.id='candidate-number-mode';for(const value of ['decimal','scientific']){const option=el('option');option.value=value;mode.append(option)}digits.id='candidate-number-digits';digits.type='number';digits.min='0';digits.max='12';digits.step='1';modeLabel.append(el('span',_('numberFormat')),mode);digitsLabel.append(el('span',_('candidateNumberDigits')),digits);panel.append(modeLabel,digitsLabel);details.append(summary,panel);mode.onchange=()=>{candidateFormulaNumberMode=mode.value;localStorage.setItem('sr-harness-candidate-number-mode',candidateFormulaNumberMode);renderTopk()};digits.oninput=()=>{const parsed=Number.parseInt(digits.value,10);if(!Number.isFinite(parsed))return;candidateFormulaDigits=Math.max(0,Math.min(12,parsed));digits.value=String(candidateFormulaDigits);localStorage.setItem('sr-harness-candidate-number-digits',String(candidateFormulaDigits));renderTopk()};bar.append(group,details);renderCandidateFormulaMode()}
function renderTopk(records=candidateRecords){
  candidateRecords=records;const shown=candidateMode==='pareto'?paretoFront(records):records,total=records.length;renderCandidateFormulaMode();$('candidate-topk').classList.toggle('active',candidateMode==='topk');$('candidate-pareto').classList.toggle('active',candidateMode==='pareto');$('count').textContent=(candidateMode==='pareto'?shown.length+'/'+total:total)+' '+_('records');
  const sig=JSON.stringify([candidateMode,candidateFormulaMode,candidateFormulaNumberMode,candidateFormulaDigits,currentLocale,records]);if($('topk').dataset.sig===sig)return;$('topk').dataset.sig=sig;$('topk').replaceChildren();if(!shown.length){$('topk').append(el('p',candidateMode==='pareto'&&records.length?_('paretoEmpty'):_('emptyCandidates'),'muted small'));return}
  shown.forEach((record,index)=>{const card=el('div',undefined,'candidate');card.append(el('div','#'+String(index+1).padStart(2,'0'),'eyebrow'),candidateFormulaNode(record.formula));const metrics=el('div',undefined,'metrics');for(const key of ['mse','r2','rmse','mae','complexity']){if(record[key]===undefined)continue;const item=el('div',key==='r2'?'R²':key.toUpperCase(),'metric');item.append(el('b',record[key]===null?'—':typeof record[key]==='number'?Number(record[key].toPrecision(5)).toString():String(record[key])));metrics.append(item)}card.append(metrics);disclosure(card,_('allMetrics'),record);$('topk').append(card)});
}
const WORKSPACE_DRAG_TYPE='application/x-srh-workspace-path';
function workspaceJoin(...parts){return parts.filter(Boolean).join('/')}
function workspaceNameIsValid(name){return Boolean(name)&&name!=='.'&&name!=='..'&&!/[\\/]/.test(name)}
function remapExpandedDirectories(source,destination){for(const path of [...expandedDirectories]){if(path!==source&&!path.startsWith(source+'/'))continue;expandedDirectories.delete(path);expandedDirectories.add(destination+path.slice(source.length))}}
async function moveWorkspaceItem(source,destination){
  if(!source||source===destination)return;
  await api('/api/workspace',{source,destination},'PATCH');remapExpandedDirectories(source,destination);filesSignature='';await refreshFiles()
}
async function moveIntoDirectory(source,directory){const name=source.split('/').pop();await moveWorkspaceItem(source,workspaceJoin(directory,name))}
async function deleteWorkspaceItem(path){await api('/api/workspace?path='+encodeURIComponent(path),{},'DELETE');for(const expanded of [...expandedDirectories])if(expanded===path||expanded.startsWith(path+'/'))expandedDirectories.delete(expanded);filesSignature='';await refreshFiles()}
async function setWorkspaceItemLocked(path,locked){await api('/api/workspace/lock',{path,locked},'PUT');filesSignature='';await refreshFiles()}
function workspaceItemIcon(item){
  const icon=el('span',undefined,'workspace-item-icon');
  if(item.directory){icon.innerHTML='<svg viewBox="0 0 18 16" aria-hidden="true"><path d="M1.8 3.6h5l1.5 1.7h7.9v8.2H1.8z"/></svg>';return icon}
  const extension=item.name.split('.').pop().toLowerCase();
  if(extension==='csv'){icon.classList.add('type-csv');icon.textContent='CSV';return icon}
  if(extension==='xls'||extension==='xlsx'){icon.classList.add('type-xls');icon.textContent='XLS';return icon}
  if(extension==='npy'){icon.classList.add('type-npy');icon.innerHTML='<svg viewBox="0 0 18 18" aria-hidden="true"><path d="M3 1.5h7l4 4v11H3z"/><path d="M10 1.5v4h4" fill="none"/><rect class="npy-cell" x="5" y="8" width="2.3" height="2.3" rx=".35"/><rect class="npy-cell" x="8.1" y="8" width="2.3" height="2.3" rx=".35"/><rect class="npy-cell" x="11.2" y="8" width="1.3" height="2.3" rx=".35"/><rect class="npy-cell" x="5" y="11.1" width="2.3" height="2.3" rx=".35"/><rect class="npy-cell" x="8.1" y="11.1" width="2.3" height="2.3" rx=".35"/><rect class="npy-cell" x="11.2" y="11.1" width="1.3" height="2.3" rx=".35"/></svg>';return icon}
  icon.classList.add('file-icon');icon.innerHTML='<svg viewBox="0 0 16 18" aria-hidden="true"><path d="M3 1.5h6l4 4v11H3z"/><path d="M9 1.5v4h4" fill="none"/></svg>';return icon
}
function workspaceReadonlyBadge(item){const mounted=Boolean(item.mounted),badge=el('span',undefined,'workspace-readonly '+(mounted?'workspace-mounted':'workspace-locked')),label=_(mounted?'readOnlyItem':'lockedItem');badge.innerHTML=mounted?'<svg viewBox="0 0 14 14" aria-hidden="true"><path d="m5.25 8.75-1.1 1.1a2.15 2.15 0 0 1-3.05-3.04l1.55-1.55a2.15 2.15 0 0 1 3.04 0"/><path d="m8.75 5.25 1.1-1.1a2.15 2.15 0 0 1 3.05 3.04l-1.55 1.55a2.15 2.15 0 0 1-3.04 0"/><path d="m4.75 7 4.5 0"/></svg>':'<svg viewBox="0 0 14 14" aria-hidden="true"><rect x="2.5" y="6" width="9" height="6.5" rx="1.5"/><path d="M4.5 6V4.5a2.5 2.5 0 0 1 5 0V6"/></svg>';badge.title=label;badge.setAttribute('aria-label',label);return badge}
function updateWorkspaceEditorIcon(){const item=workspaceEditItem?{...workspaceEditItem,name:$('workspace-name-input').value||workspaceEditItem.name}:{directory:true,name:''},source=workspaceItemIcon(item),target=$('workspace-editor-icon');target.className='workspace-editor-icon '+[...source.classList].join(' ');target.innerHTML=source.innerHTML}
function closeWorkspaceNameEditor(){workspaceEditItem=null;$('workspace-name-editor').hidden=true;$('workspace-name-input').value=''}
function openWorkspaceNameEditor(item=null){workspaceEditItem=item;$('workspace-name-input').value=item?.name||'';$('workspace-name-input').placeholder=_(item?'renamePrompt':'newFolderPrompt');updateWorkspaceEditorIcon();$('workspace-name-editor').hidden=false;requestAnimationFrame(()=>{$('workspace-name-input').focus();$('workspace-name-input').select()})}
function formatFileSize(bytes){const value=Number(bytes)||0,units=['B','KB','MB','GB','TB'];let size=value,index=0;while(size>=1024&&index<units.length-1){size/=1024;index++}const precision=index===0?0:size<10?2:size<100?1:0;return size.toFixed(precision)+units[index]}
function workspaceItemMenu(item){
  const actions=el('details',undefined,'file-actions'),summary=el('summary','⋯'),menu=el('div',undefined,'file-action-menu');summary.title=_('fileActions');summary.setAttribute('aria-label',_('fileActions'));
  const download=el('a');download.href='/api/workspace/download?path='+encodeURIComponent(item.path);download.download=item.name+(item.directory?'.zip':'');download.onclick=event=>{event.stopPropagation();actions.open=false};
  if(item.directory){const loading=el('span',undefined,'download-size-loading');loading.title=_('calculatingSize');loading.setAttribute('aria-label',_('calculatingSize'));download.append(document.createTextNode(_('downloadZip')+' ('),loading,document.createTextNode(')'));let sizeRequested=false;actions.ontoggle=()=>{if(!actions.open||sizeRequested)return;sizeRequested=true;api('/api/workspace/size?path='+encodeURIComponent(item.path),undefined,'GET').then(result=>{item.size=result.size;download.textContent=_('downloadZipSize',{size:formatFileSize(result.size)})}).catch(error=>{download.textContent=_('downloadZip')+' ('+_('sizeUnavailable')+')';download.title=error.message})}}else download.textContent=_('downloadSize',{size:formatFileSize(item.size)});menu.append(download)
  if(!item.mounted){const lock=el('button',_(item.locked?'unlockItem':'lockItem'));lock.type='button';lock.onclick=guard(async event=>{event.stopPropagation();actions.open=false;await setWorkspaceItemLocked(item.path,!item.locked)});menu.append(lock)}if(!item.read_only){const rename=el('button',_('rename')),remove=el('button',_('deleteItem'),'delete-action');rename.type=remove.type='button';rename.onclick=event=>{event.stopPropagation();actions.open=false;openWorkspaceNameEditor(item)};remove.onclick=guard(async event=>{event.stopPropagation();actions.open=false;if(!confirm(_('deleteConfirm',{name:item.name})))return;await deleteWorkspaceItem(item.path)});menu.append(rename,remove)}
  if(!menu.children.length)return null;actions.append(summary,menu);return actions
}
function setDirectoryExpanded(item,node,children,expanded){
  if(expanded)expandedDirectories.add(item.path);else expandedDirectories.delete(item.path);node.setAttribute('aria-expanded',String(expanded));children.hidden=!expanded;const toggle=node.querySelector('.tree-toggle'),label=(currentLocale==='en'?(expanded?'Collapse ':'Expand '):(expanded?'折叠':'展开'))+item.name;toggle.classList.toggle('expanded',expanded);toggle.title=label;toggle.setAttribute('aria-label',label)
}
async function loadWorkspaceChildren(item,node,children){
  if(node.dataset.childrenLoaded==='true'||node.dataset.childrenLoading==='true')return;node.dataset.childrenLoading='true';
  try{const data=await api('/api/workspace?path='+encodeURIComponent(item.path));item.children=data.entries;children.replaceChildren();for(const path of collectDirectoryPaths(data.entries))expandedDirectories.add(path);renderWorkspaceEntries(data.entries,children);node.dataset.childrenLoaded='true'}finally{delete node.dataset.childrenLoading}
}
function renderWorkspaceEntries(entries,host){
  for(const item of entries){
    const node=el('div',undefined,'file-node'),row=el('div',undefined,'file'),toggle=el('button',undefined,'tree-toggle'),button=el('button',item.name,'name');node.setAttribute('role','treeitem');row.dataset.path=item.path;row.draggable=!item.read_only;button.title=item.name;toggle.type='button';toggle.innerHTML='<svg viewBox="0 0 12 12" aria-hidden="true"><path d="m4 2.5 3.5 3.5L4 9.5"/></svg>';
    if(!item.directory)toggle.classList.add('file-spacer');
    const openFile=guard(async()=>{const value=await api('/api/workspace/preview?path='+encodeURIComponent(item.path));$('preview-title').textContent=item.name;const meta=$('preview-meta');meta.replaceChildren();if(value.kind==='npy'){const shape=value.shape.length?'('+value.shape.join(', ')+(value.shape.length===1?',':'')+')':'()';meta.append(el('span',_('previewShape',{value:shape})),el('span',_('previewDtype',{value:value.dtype})),el('span',_('previewElements',{value:value.size})))}$('preview-text').textContent=value.text+(value.truncated?'\n… '+_('previewTruncated'):'');$('preview').showModal()});
    row.ondragstart=event=>{event.dataTransfer.effectAllowed='copyMove';event.dataTransfer.setData(WORKSPACE_DRAG_TYPE,item.path);if(!item.directory){const href='/api/workspace/download?path='+encodeURIComponent(item.path);event.dataTransfer.setData('DownloadURL','application/octet-stream:'+item.name+':'+new URL(href,location.href).href);event.dataTransfer.setData('text/uri-list',href)}};
    row.append(toggle,workspaceItemIcon(item),button);if(item.read_only)row.append(workspaceReadonlyBadge(item));const itemMenu=workspaceItemMenu(item);if(itemMenu)row.append(itemMenu);node.append(row);
    if(item.directory){
      const children=el('div',undefined,'file-children');children.setAttribute('role','group');node.dataset.childrenLoaded=String(Array.isArray(item.children)&&item.children.length>0);node.append(children);renderWorkspaceEntries(item.children||[],children);const toggleDirectory=guard(async()=>{const expanded=!expandedDirectories.has(item.path);setDirectoryExpanded(item,node,children,expanded);if(expanded)await loadWorkspaceChildren(item,node,children)});toggle.onclick=event=>{event.stopPropagation();toggleDirectory()};button.onclick=toggleDirectory;const expanded=expandedDirectories.has(item.path);setDirectoryExpanded(item,node,children,expanded);if(expanded&&node.dataset.childrenLoaded!=='true')loadWorkspaceChildren(item,node,children).catch(notice);
      row.ondragover=event=>{if(!event.dataTransfer.types.includes(WORKSPACE_DRAG_TYPE))return;event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect='move';row.classList.add('drop-target')};
      row.ondragleave=event=>{if(!row.contains(event.relatedTarget))row.classList.remove('drop-target')};
      row.ondrop=guard(async event=>{const source=event.dataTransfer.getData(WORKSPACE_DRAG_TYPE);if(!source)return;event.preventDefault();event.stopPropagation();row.classList.remove('drop-target');expandedDirectories.add(item.path);await moveIntoDirectory(source,item.path)});
    }else button.onclick=openFile;
    host.append(node)
  }
}
function collectDirectoryPaths(entries){const paths=[];for(const item of entries)if(item.directory){paths.push(item.path,...collectDirectoryPaths(item.children||[]))}return paths}
async function refreshFiles(){
  const data=await api('/api/workspace?recursive=true'),sig=JSON.stringify(data);if(sig===filesSignature)return;filesSignature=sig;if(!workspaceExpansionInitialized){for(const path of collectDirectoryPaths(data.entries))expandedDirectories.add(path);workspaceExpansionInitialized=true}$('files').replaceChildren();renderWorkspaceEntries(data.entries,$('files'));if(!data.entries.length)$('files').append(el('p',_('workspaceEmpty'),'muted small'))
}
async function uploadFiles(files){for(const file of files){notice(_('uploading',{name:file.name}));const path=file.webkitRelativePath||file.name;const response=await fetch('/api/workspace/upload?path='+encodeURIComponent(path),{method:'PUT',headers:conversationHeaders(),body:file});if(!response.ok)throw Error(file.name+': '+await responseError(response,_('uploadFailed')))}notice('');filesSignature='';await refreshFiles()}
function dataAgentControlState(){
  const state=session?.state||'idle',interaction=session?.data_interaction_state||'idle',active=ACTIVE_INTERACTION_STATES.has(interaction),canStart=state==='idle'||(state==='running'&&session?.interaction_state==='paused');
  return agentComposerControlState({hasInput:Boolean($('data-agent-input').value.trim()),interaction,startAction:canStart?'message':null,canMessage:active,canControl:active});
}
function renderDataAgentControl(){
  renderAgentComposerButton($('data-agent-send'),dataAgentControlState(),{sendLabel:_('dataAgentSend'),pauseLabel:_('dataAgentStop'),stoppingLabel:_('dataAgentStopping')});
}
function renderTimelineSurface(){
  renderRequestedControlsLanguage();const visible=$('timeline-tab').classList.contains('active'),active=(session?.state||'idle')!=='idle';$('run-setup').hidden=!visible||active;$('feed').hidden=!visible||!active;$('initial-prompt-toggle').hidden=active;if(active)setInitialPromptOpen(false);$('composer-purpose').hidden=active;$('composer-purpose-title').textContent=_('composerPurposeTitle');$('composer-purpose-help').textContent=_('composerPurposeHelp');$('composer-purpose-help').hidden=initialPromptSent;$('prompt').placeholder=_(active?'promptPlaceholder':'initialUserPromptPlaceholder');
}
function composerControlState(){
  const state=session?.state||'idle',interaction=session?.interaction_state||'idle',running=['starting','running'].includes(state);
  return agentComposerControlState({hasInput:Boolean($('prompt').value.trim()),interaction,startAction:state==='idle'?'start':null,canMessage:running,canControl:running,blocked:startRequestPending});
}
function renderComposerControl(){
  const button=$('send'),control=composerControlState();
  button.classList.add('send-icon');
  renderAgentComposerButton(button,control,{sendLabel:_((session?.state||'idle')==='idle'?'startExploring':'insertRound'),pauseLabel:_('pause'),stoppingLabel:_('interactionInterrupting')});
}
function resetForServerSession(){
  serverSessionGeneration+=1;clearTimeout(promptRefreshTimer);promptRefreshToken+=1;credentialRequestToken+=1;dataCredentialRequestToken+=1;seq=0;dataSeq=0;evaluatorSeq=0;treeRun=null;filesSignature='';contextSignature='';workspaceExpansionInitialized=false;renderedDataRevision=0;useCommittedContext=false;dataPreview=null;dataPreviewGroups=[];selectedDataPreviewGroup='';dataGroupPreview=null;dataGroupPreviewToken+=1;plotPreview=null;plotPreviewToken+=1;dataChannels={x:'',y:'',hue:'',size:''};distributionChannels={x:'',y:''};heatmapChannels={row:[],column:[],color:'',z:''};heatmapPreview=null;heatmapPreviewToken+=1;variableOrder=[];variableRoles={};variableDescriptions={};latestContext=null;selectedContextKey=null;contextHydrationPromise=null;capabilities=null;dataCapabilities=null;evaluatorCapabilities=null;evaluatorConfiguration=null;evaluatorDirty=false;evaluatorResultSignature='';promptDefaults={problem_description:DEFAULT_PROBLEM_DESCRIPTION,system_prompt:'',user_prompt:''};promptEdited={user:false,system:false};initialPromptSent=false;initialized=false;
  setTreeStatus('treeIdle');
  for(const collection of [toolCards,dataToolCards,assistantCards,dataAssistantCards,evaluatorAssistantCards,assistantStreamStates,seenUsageSteps,seenDataUsageTurns,contextHistory])collection.clear();observedUsage={token:{},price:{}};observedDataUsage={token:{},price:{}};candidateRecords=[];expandedDirectories.clear();shownSessionErrors.clear();
  const welcome=$('welcome');$('feed').replaceChildren(welcome);$('data-agent-feed').replaceChildren();$('data-agent-feed').hidden=true;$('evaluator-agent-feed').replaceChildren();$('evaluator-agent-feed').hidden=true;$('context').replaceChildren();$('data-table').replaceChildren();$('tensor-preview').replaceChildren();renderDataPreviewGroupPicker();$('target').value='';
}
function syncSession(s){
  const serverSessionChanged=Boolean(session?.run_id&&s.run_id&&session.run_id!==s.run_id);if(serverSessionChanged)resetForServerSession();session=s;const running=['starting','running'].includes(s.state);renderHeaderControls();renderTimelineWelcome();
  renderComposerControl();$('data-agent-state').textContent=_(s.data_state==='stopping'?'dataAgentStopping':s.data_state==='running'?'dataAgentRunning':s.data_state==='stopped'?'dataAgentStopped':'dataAgentReady');renderDataAgentControl();renderTimelineSurface();renderEvaluatorAvailability();applyEvaluatorAgentResult();
  $('pending').textContent=s.pending_transition?_(s.pending_transition==='next_r'?'nextRQueued':'nextCQueued'):s.pending_settings?_('modelQueued'):s.pending_messages?_('promptsQueued',{count:s.pending_messages}):'';for(const id of ['next-c','next-r']){$(id).hidden=!running;$(id).disabled=!running}const settingsEditable=sessionSettingsEditable(s);$('apply').disabled=!settingsEditable;$('data-settings-apply').disabled=!settingsEditable;$('evaluator-agent-settings-apply').disabled=!settingsEditable;renderTopk(s.topk_records||[]);
  if(!initialized){
    if(s.discovery_task?.prompts)applyDiscoveryPrompts(s.discovery_task.prompts);
    if(s.initial_prompt){$('problem-description').value=s.initial_prompt;promptDefaults.problem_description=s.initial_prompt;requestAnimationFrame(fitProblemDescription)}
    ensureCapabilities().then(syncSettingsForm).catch(notice);syncDataAgentSettingsForm().catch(notice);if(!evaluatorConfiguration)loadEvaluatorConfiguration().catch(notice);initialized=true;hydrateCommittedContext().then(()=>{if(s.state==='idle')return refreshPromptPreview()}).catch(error=>dataNote(error.message,true));if(s.state!=='idle')selectCenterTab('timeline');
  }
  if((s.data_context?.revision||0)>renderedDataRevision){loadCommittedContext().then(renderTimelineSurface).catch(error=>notice(error))}const sessionError=s.result?.error;if(sessionError){const errorKey=JSON.stringify([s.run_id||'',sessionError]);if(!shownSessionErrors.has(errorKey)){shownSessionErrors.add(errorKey);notice(sessionError)}}if(s.state!=='idle'&&treeRun!==s.run_id){treeRun=s.run_id;const url=conversationUrl('/viewer?embed=1&run='+encodeURIComponent(s.run_id));setTreeStatus('treeLoading');$('tree').src=url;$('full-tree').href=conversationUrl('/viewer?run='+encodeURIComponent(s.run_id))}
}
async function pollStatus(){try{await conversationReady;const s=await api('/api/session');lastStatusAt=Date.now();syncSession(s);renderActivity()}catch(error){$('connection').textContent=_('connectionError');$('connection').title=error.message}finally{setTimeout(pollStatus,1500)}}
function compactStreamEventBatch(events){
  const terminal=new Set(),latestDelta=new Map();
  for(const event of events){const responseId=event.payload?.response_id;if(!responseId)continue;if(['assistant_completed','assistant_failed'].includes(event.kind))terminal.add(responseId);else if(event.kind==='assistant_delta')latestDelta.set(responseId,event)}
  return events.filter(event=>{const responseId=event.payload?.response_id;if(!responseId)return true;if(terminal.has(responseId)&&['assistant_started','assistant_delta'].includes(event.kind))return false;if(event.kind==='assistant_delta')return latestDelta.get(responseId)===event;return true})
}
async function pollEvents(){let pollDelay=1500;try{
  await conversationReady;
  const [searchEvents,dataEvents,evaluatorEvents]=await Promise.all([api('/api/control/events?after_seq='+seq),api('/api/data/agent/events?after_seq='+dataSeq),api('/api/evaluator/agent/events?after_seq='+evaluatorSeq)]);lastEventsAt=Date.now();
  if([searchEvents,dataEvents,evaluatorEvents].some(batch=>batch.has_more))pollDelay=50;
  if((searchEvents.truncated&&seq)||(dataEvents.truncated&&dataSeq)||(evaluatorEvents.truncated&&evaluatorSeq))notice(_('eventBufferGap'));
  for(const [batch,render] of [[searchEvents,renderEvent],[dataEvents,renderDataEvent],[evaluatorEvents,renderEvaluatorEvent]])for(const e of compactStreamEventBatch(batch.events)){try{render(e)}catch(error){notice(_('eventRenderFailed',{seq:e.seq,message:error.message}))}}
  if(searchEvents.cursor_reset)seq=0;if(dataEvents.cursor_reset)dataSeq=0;if(evaluatorEvents.cursor_reset)evaluatorSeq=0;seq=Math.max(seq,...searchEvents.events.map(event=>event.seq));dataSeq=Math.max(dataSeq,...dataEvents.events.map(event=>event.seq));evaluatorSeq=Math.max(evaluatorSeq,...evaluatorEvents.events.map(event=>event.seq));
  const visibleContext=selectedContextKey?contextHistory.get(selectedContextKey):latestContext;if(visibleContext)renderContext(visibleContext);renderActivity();
}catch(error){pollDelay=1500;$('connection').title=_('eventSync',{message:error.message})}finally{setTimeout(pollEvents,pollDelay)}}
async function pollFiles(){try{await conversationReady;await refreshFiles()}catch(error){$('files').title=error.message}finally{setTimeout(pollFiles,5000)}}
$('follow').onclick=()=>{$('feed').scrollTop=$('feed').scrollHeight;$('follow').hidden=true};
$('feed').addEventListener('scroll',()=>{$('follow').hidden=$('feed').scrollHeight-$('feed').scrollTop-$('feed').clientHeight<100});
for(const mode of ['latest','fit'])$('tree-'+mode).onclick=()=>{$('tree').contentWindow.postMessage({type:'sr-tree-view',mode},location.origin)};
$('tree-retry').onclick=()=>{if(treeRun){setTreeStatus('treeReconnecting');$('tree').src='/viewer?embed=1&run='+encodeURIComponent(treeRun)}};
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.source!==$('tree').contentWindow)return;if(event.data?.type==='sr-tree-status'){if(event.data.key)setTreeStatus(event.data.key,event.data.values||{});else{$('tree-status').textContent=event.data.message;treeStatusKey='';treeStatusValues={}}}else if(event.data?.type==='sr-tree-node-selected')showContextAt(event.data.coord,event.data.nodeId,event.data.runId)});

const mainLayout=document.querySelector('main'),panelWidths={left:Math.max(150,$('workspace').getBoundingClientRect().width),right:Math.max(150,$('insights-panel').getBoundingClientRect().width)};
try{const saved=JSON.parse(localStorage.getItem('sr-harness-panel-layout')||'{}');if(Number(saved.left)>0)panelWidths.left=Number(saved.left);if(Number(saved.right)>0)panelWidths.right=Number(saved.right);if(saved.leftCollapsed)mainLayout.classList.add('left-collapsed');if(saved.rightCollapsed)mainLayout.classList.add('right-collapsed')}catch{}
function savePanelLayout(){try{localStorage.setItem('sr-harness-panel-layout',JSON.stringify({left:panelWidths.left,right:panelWidths.right,leftCollapsed:mainLayout.classList.contains('left-collapsed'),rightCollapsed:mainLayout.classList.contains('right-collapsed')}))}catch{}}
function applyPanelLayout(){if(window.innerWidth>850){let available=Math.max(300,mainLayout.clientWidth-374),visible=[];if(!mainLayout.classList.contains('left-collapsed'))visible.push('left');if(!mainLayout.classList.contains('right-collapsed'))visible.push('right');for(const side of visible){const others=visible.filter(name=>name!==side).reduce((sum,name)=>sum+panelWidths[name],0);panelWidths[side]=Math.min(panelWidths[side],Math.max(150,available-others))}}mainLayout.style.setProperty('--left-width',panelWidths.left+'px');mainLayout.style.setProperty('--right-width',panelWidths.right+'px');for(const side of ['left','right']){const collapsed=mainLayout.classList.contains(side+'-collapsed'),resizer=$(side+'-resizer'),toggle=resizer.querySelector('.panel-toggle'),name=_(side==='left'?'workspace':'searchResults'),action=_(collapsed?'expandPanel':'collapsePanel',{name});resizer.setAttribute('aria-expanded',String(!collapsed));resizer.title=_('resizePanel');toggle.textContent=side==='left'?(collapsed?'›':'‹'):(collapsed?'‹':'›');toggle.setAttribute('aria-label',action);toggle.title=action}}
function setPanelCollapsed(side,collapsed){mainLayout.classList.toggle(side+'-collapsed',collapsed);applyPanelLayout();savePanelLayout()}
function setupPanelResizer(side){
  const resizer=$(side+'-resizer'),toggle=resizer.querySelector('.panel-toggle'),collapsedClass=side+'-collapsed';let drag=null,frame=0,pendingX=0;
  const update=clientX=>{const rect=mainLayout.getBoundingClientRect(),otherSide=side==='left'?'right':'left',other=mainLayout.classList.contains(otherSide+'-collapsed')?0:panelWidths[otherSide],raw=side==='left'?clientX-rect.left:rect.right-clientX;if(raw<72)mainLayout.classList.add(collapsedClass);else{mainLayout.classList.remove(collapsedClass);panelWidths[side]=Math.min(Math.max(150,raw),Math.max(150,rect.width-other-374))}applyPanelLayout()};
  const finish=event=>{if(!drag||event.pointerId!==drag.pointerId)return;drag=null;if(frame){cancelAnimationFrame(frame);frame=0;update(pendingX)}try{resizer.releasePointerCapture(event.pointerId)}catch{}resizer.classList.remove('active');mainLayout.classList.remove('resizing');savePanelLayout();renderActivePlot()};
  toggle.onclick=event=>{event.stopPropagation();setPanelCollapsed(side,!mainLayout.classList.contains(collapsedClass))};
  resizer.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setPanelCollapsed(side,!mainLayout.classList.contains(collapsedClass));return}if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const direction=event.key==='ArrowRight'?1:-1,delta=(side==='left'?direction:-direction)*16;setPanelCollapsed(side,false);panelWidths[side]=Math.max(150,panelWidths[side]+delta);applyPanelLayout();savePanelLayout()};
  resizer.onpointerdown=event=>{if(event.button!==0||event.target.closest('.panel-toggle')||mainLayout.classList.contains(collapsedClass))return;event.preventDefault();drag={pointerId:event.pointerId};pendingX=event.clientX;resizer.setPointerCapture(event.pointerId);resizer.classList.add('active');mainLayout.classList.add('resizing')};
  resizer.onpointermove=event=>{if(!drag||event.pointerId!==drag.pointerId)return;pendingX=event.clientX;if(!frame)frame=requestAnimationFrame(()=>{frame=0;update(pendingX)})};
  resizer.onpointerup=finish;resizer.onpointercancel=finish;
}
applyPanelLayout();setupPanelResizer('left');setupPanelResizer('right');window.addEventListener('resize',applyPanelLayout);

$('send').onclick=guard(async()=>{const control=composerControlState();if(control.action==='start'){await startPreparedRun($('prompt').value.trim());$('prompt').value='';renderComposerControl();return}if(control.action==='message')return sendAgentComposerMessage({input:$('prompt'),button:$('send'),request:message=>api('/api/control/command',{action:'message',message}),apply:result=>syncSession({...session,...result}),render:renderComposerControl});if(control.action){const result=await api('/api/control/command',{action:control.action});syncSession({...session,...result});if(result.cancellation_error)notice(result.cancellation_error)}});
$('prompt').oninput=()=>{renderComposerControl();if((session?.state||'idle')!=='idle')return;promptEdited.user=true};$('system-prompt').oninput=()=>{promptEdited.system=true};bindEnterToSend($('prompt'),$('send'));$('problem-description').oninput=()=>{fitProblemDescription();syncResearchProblem($('problem-description').value)};
$('data-agent-send').onclick=dataGuard(async()=>{const control=dataAgentControlState();if(control.action==='message')return sendAgentComposerMessage({input:$('data-agent-input'),button:$('data-agent-send'),request:message=>api('/api/data/agent',{message}),render:renderDataAgentControl});if(control.action){const result=await api('/api/data/agent/stop',{});syncSession(result);if(result.cancellation_error)notice(result.cancellation_error)}});
$('data-agent-input').oninput=renderDataAgentControl;
bindEnterToSend($('data-agent-input'),$('data-agent-send'));
for(const button of document.querySelectorAll('[data-data-settings-tab]'))button.onclick=()=>selectDataSettingsTab(button.dataset.dataSettingsTab);
$('data-provider').onchange=()=>{$('data-api-key').value='';refreshDataProviderCredential().catch(notice)};
$('data-api-key-visibility').onclick=()=>{const input=$('data-api-key'),show=input.type==='password';input.type=show?'text':'password';renderDataApiKeyVisibility()};
$('data-agent-settings-toggle').onclick=dataGuard(()=>setDataAgentSettingsOpen($('data-agent-settings').hidden));
$('data-agent-settings-close').onclick=$('data-settings-cancel').onclick=()=>setDataAgentSettingsOpen(false);
$('data-model-test').onclick=testDataAgentModel;
$('data-settings-apply').onclick=dataGuard(async()=>{const queued=agentSettingsQueued(session?.data_interaction_state),credential=await saveDataProviderCredential();syncSession(await api('/api/data/agent/settings',dataAgentSettingsPayload(),'PUT'));await setDataAgentSettingsOpen(false);notice(credential?_('apiKeySaved',{env:credential.env_var}):_(queued?'settingsQueued':'dataSettingsSaved'))});

$('data-model-test').before($('data-settings-hint'));$('data-api-key-status').remove();
$('data-agent-state').classList.add('composer-status-center');$('data-agent-send').before($('data-agent-state'),composerKeyboardHint('data-agent-keyboard-hint'));
$('settings-cancel').before($('settings-hint'));$('api-key-status').remove();
const modelTestStatus=el('span',undefined,'model-test-status'),modelTestButton=el('button',_('dataAgentModelTest'));modelTestStatus.id='model-test-status';modelTestStatus.setAttribute('role','status');modelTestButton.id='model-test';modelTestButton.type='button';$('settings-cancel').before(modelTestStatus,modelTestButton);modelTestButton.onclick=guard(testModel);
mountAdvanceControls();mountTruncationSetting();mountStopSettings();
const composerToolbar=$('send').parentElement;composerToolbar.prepend($('settings-toggle'),$('initial-prompt-toggle'));$('status').className='small muted composer-status-center';$('send').before($('status'),composerKeyboardHint('prompt-keyboard-hint'));
const promptInput=$('prompt'),promptResizeHandle=document.createElement('span');promptResizeHandle.className='prompt-resize-handle';promptResizeHandle.tabIndex=0;promptResizeHandle.setAttribute('role','separator');promptResizeHandle.setAttribute('aria-orientation','horizontal');promptResizeHandle.setAttribute('aria-label','调整用户提示词输入区域高度');promptResizeHandle.title='调整用户提示词输入区域高度';promptInput.after(promptResizeHandle);const positionPromptResizeHandle=()=>promptResizeHandle.style.top=promptInput.offsetTop+7+'px',resizePromptInput=height=>{promptInput.style.height=Math.min(260,Math.max(72,height))+'px'};new ResizeObserver(positionPromptResizeHandle).observe($('composer-purpose'));requestAnimationFrame(positionPromptResizeHandle);promptResizeHandle.onpointerdown=event=>{event.preventDefault();positionPromptResizeHandle();const startY=event.clientY,startHeight=promptInput.getBoundingClientRect().height;promptResizeHandle.setPointerCapture(event.pointerId);promptResizeHandle.onpointermove=moveEvent=>resizePromptInput(startHeight-(moveEvent.clientY-startY));promptResizeHandle.onpointerup=promptResizeHandle.onpointercancel=()=>{promptResizeHandle.onpointermove=null;promptResizeHandle.onpointerup=null;promptResizeHandle.onpointercancel=null}};promptResizeHandle.onkeydown=event=>{if(event.key!=='ArrowUp'&&event.key!=='ArrowDown')return;event.preventDefault();resizePromptInput(promptInput.getBoundingClientRect().height+(event.key==='ArrowUp'?12:-12))};
$('initial-prompt-toggle').onclick=()=>setInitialPromptOpen($('initial-prompt-panel').hidden);$('initial-prompt-close').onclick=()=>setInitialPromptOpen(false);
for(const button of document.querySelectorAll('[data-settings-tab]'))button.onclick=()=>selectSettingsTab(button.dataset.settingsTab);$('provider').onchange=()=>{$('api-key').value='';refreshProviderCredential().catch(notice)};$('api-key-visibility').onclick=()=>{const input=$('api-key'),show=input.type==='password';input.type=show?'text':'password';renderApiKeyVisibility()};$('settings-toggle').onclick=guard(()=>setSettingsOpen($('settings-panel').hidden));$('settings-close').onclick=$('settings-cancel').onclick=()=>setSettingsOpen(false);$('apply').onclick=guard(async()=>{const queued=sessionSettingsQueued(),credential=await saveProviderCredential();syncSession(await api('/api/session/settings',settingsPayload()));await setSettingsOpen(false);notice(credential?_('apiKeySaved',{env:credential.env_var}):_(queued?'settingsQueued':'settingsSaved'))});$('next-c').onclick=guard(()=>api('/api/control/command',{action:'next_c'}));$('next-r').onclick=guard(()=>api('/api/control/command',{action:'next_r'}));
$('refresh').onclick=guard(async()=>{filesSignature='';await refreshFiles()});$('new-folder').onclick=()=>openWorkspaceNameEditor();$('workspace-name-cancel').onclick=closeWorkspaceNameEditor;$('workspace-name-input').oninput=updateWorkspaceEditorIcon;$('workspace-name-editor').onsubmit=guard(async event=>{event.preventDefault();const name=$('workspace-name-input').value.trim();if(!workspaceNameIsValid(name))throw Error(_('invalidName'));if(workspaceEditItem){const parent=workspaceEditItem.path.split('/').slice(0,-1).join('/');await moveWorkspaceItem(workspaceEditItem.path,workspaceJoin(parent,name))}else{await api('/api/workspace/directory',{path:name});filesSignature='';await refreshFiles()}closeWorkspaceNameEditor()});$('upload').onclick=()=>$('file-input').click();$('file-input').onchange=guard(async event=>{await uploadFiles(event.target.files);event.target.value=''});
$('workspace').ondragover=event=>{const types=event.dataTransfer.types;if(types.includes('Files')||types.includes(WORKSPACE_DRAG_TYPE)){event.preventDefault();event.dataTransfer.dropEffect=types.includes(WORKSPACE_DRAG_TYPE)?'move':'copy';$('workspace').classList.add('dragging')}};$('workspace').ondragleave=event=>{if(!$('workspace').contains(event.relatedTarget))$('workspace').classList.remove('dragging')};$('workspace').ondrop=guard(async event=>{event.preventDefault();$('workspace').classList.remove('dragging');const source=event.dataTransfer.getData(WORKSPACE_DRAG_TYPE);if(source){await moveIntoDirectory(source,'');return}await uploadFiles(event.dataTransfer.files)});
function selectCenterTab(tab){
  const dataMode=tab==='prepare'||tab==='data';if(dataMode){setSettingsOpen(false);setInitialPromptOpen(false)}$('data-preparation').hidden=tab!=='prepare';$('data-setup').hidden=tab!=='data';$('context').hidden=tab!=='context';$('composer').classList.toggle('data-mode',dataMode);
  for(const name of ['prepare','data','timeline','context'])$(name+'-tab').classList.toggle('active',name===tab);$('context-tab').hidden=tab!=='context';const showDataInsights=tab==='prepare'||tab==='data';$('search-insights').hidden=showDataInsights;$('data-insights').hidden=!showDataInsights;renderTimelineSurface();$('follow').hidden=tab!=='timeline'||$('feed').scrollHeight-$('feed').scrollTop-$('feed').clientHeight<100;if(tab==='prepare'||tab==='data'){if(!dataPreview)hydrateCommittedContext().catch(error=>dataNote(error.message,true));requestAnimationFrame(renderActivePlot)}else if(tab==='timeline'&&session?.state==='idle'&&!dataPreview)hydrateCommittedContext().catch(error=>dataNote(error.message,true));
}
let tabHintTimer;function showTabHint(message){clearTimeout(tabHintTimer);$('tab-hint').textContent=message;$('tab-hint').hidden=false;tabHintTimer=setTimeout(()=>$('tab-hint').hidden=true,5000)}
for(const tab of ['prepare','data','timeline','context'])$(tab+'-tab').onclick=()=>selectCenterTab(tab);
$('relationship-preview-mode').onchange=()=>{const selected=$('relationship-preview-mode').value;plotMode=['table','structure','scatter','distribution','heatmap'].includes(selected)?selected:'table';localStorage.setItem('sr-harness-plot-mode',plotMode);plotPreview=null;heatmapPreview=null;plotPreviewToken+=1;heatmapPreviewToken+=1;renderPlotSlots();renderPlotModeLanguage();renderDataPreviewGroupPicker();loadDataPreviewGroup(selectedDataPreviewGroup).catch(error=>dataNote(error?.message||error,true));loadActivePlotPreview()};
$('distribution-bin-count').value=String(distributionBins);$('distribution-bin-count').oninput=()=>{const value=Number.parseInt($('distribution-bin-count').value,10);if(!Number.isFinite(value))return;distributionBins=Math.max(2,Math.min(100,value));$('distribution-bin-count').value=String(distributionBins);localStorage.setItem('sr-harness-distribution-bins',String(distributionBins));renderDistribution()};
$('candidate-topk').onclick=()=>{candidateMode='topk';localStorage.setItem('sr-harness-candidate-mode',candidateMode);renderTopk()};$('candidate-pareto').onclick=()=>{candidateMode='pareto';localStorage.setItem('sr-harness-candidate-mode',candidateMode);renderTopk()};
$('theme-toggle').onclick=()=>{uiTheme=uiTheme==='light'?'dark':'light';applyTheme()};$('language-toggle').onclick=()=>{currentLocale=SUPPORTED_LOCALES[(SUPPORTED_LOCALES.indexOf(currentLocale)+1)%SUPPORTED_LOCALES.length];applyLanguage()};$('tree').addEventListener('load',applyTheme);
$('data-refresh').onclick=dataGuard(refreshCommittedContext);
for(const slot of document.querySelectorAll('.plot-slot')){slot.ondragover=event=>{if(!event.dataTransfer.types.includes('application/x-srh-plot-variable'))return;event.preventDefault();slot.classList.add('dragover')};slot.ondragleave=()=>slot.classList.remove('dragover');slot.ondrop=event=>{event.preventDefault();plotDragAccepted=true;event.dataTransfer.dropEffect=event.dataTransfer.getData('application/x-srh-slot-channel')?'move':'copy';slot.classList.remove('dragover');setPlotChannel(slot.dataset.channel,event.dataTransfer.getData('application/x-srh-plot-variable'),event.dataTransfer.getData('application/x-srh-slot-channel'))};slot.ondblclick=()=>setPlotChannel(slot.dataset.channel,'')}
document.addEventListener('click',event=>{if(!event.target.closest('.role-picker'))for(const picker of document.querySelectorAll('.role-picker[open]'))picker.open=false;if(!event.target.closest('.file-actions'))for(const menu of document.querySelectorAll('.file-actions[open]'))menu.open=false;if(!event.target.closest('.conversation-item-actions'))for(const menu of document.querySelectorAll('.conversation-item-actions[open]'))menu.open=false;if(!event.target.closest('.candidate-number-format'))$('candidate-number-format').open=false});
let discoveryTasks=[],discoveryLoading=false;
function renderDiscoveryTasks(){
  const references={
    Chen_NatureAstronomy2023:{citation:'(Chen et al., Nature Astronomy, 2023)',summary:String.raw`基于双模 RR Lyrae 的周期与 SDSS 光谱金属丰度数据，得到金属丰度标定公式：
$$[\mathrm{Fe}/\mathrm{H}]=-173\operatorname{log}_{10}\!\left(\frac{P_{1\mathrm{O}}/P_{\mathrm{F}}}{0.745}\right)-6.62\operatorname{log}_{10}\!\left(\frac{P_{1\mathrm{O}}}{0.37}\right)-1.76$$`},
    Xiang_Nature2022:{citation:'(Xiang & Rix, Nature, 2022)',summary:String.raw`基于恒星年龄、化学丰度与轨道参数目录，得到厚盘族群的窄年龄—金属丰度序列，可近似描述为：
$$⟨τ⟩\approxτ_0+a[\mathrm{Fe}/\mathrm{H}]$$`},
    Li_Nature2023:{citation:'(Li et al., Nature, 2023)',summary:String.raw`基于恒星质量、金属丰度及动力学族群数据，得到初始质量函数的幂律描述，其斜率随丰度与时代变化：
$$\frac{dN}{dM}∝ M^{-\alpha},\quad\alpha=\alpha([\mathrm{Fe}/\mathrm{H}],t)$$`},
    Feng_Science2022:{citation:'(Feng et al., Science, 2022)',summary:String.raw`基于校准射电爆发的频率分辨偏振数据，得到退偏振关系，并约束磁离子环境的变化：
$$\frac{p}{p_0}=\operatorname{exp}\!\left(-2\sigma_{\mathrm{RM}}^2\lambda^4\right)$$`},
    Li_Nature2021:{citation:'(Li et al., Nature, 2021)',summary:String.raw`基于 1652 次重复 FRB 的爆发表，得到由对数正态与广义柯西分量组合描述的能量分布：
$$N(E)=\frac{N_0}{\sqrt{2\pi}\sigma_E E}\operatorname{exp}\!\left[-\frac{(\operatorname{log} E-\operatorname{log} E_0)^2}{2\sigma_E^2}\right]+\frac{\epsilon_E}{1+(E/E_0)^{\alpha_E}}$$`},
    Chiang_NatureAstronomy2026:{citation:'(Chiang, Nature Astronomy, 2026)',summary:String.raw`基于宇宙谱线背景统计与气体转换模型，得到宇宙平均分子气体密度随红移演化的拟合：
$$\Omega_{\mathrm{H}_2}(z)\approx\frac{1.9\times10^{-4}(1+z)^{2.3}}{1+[(1+z)/2.8]^{6.5}}$$`},
    Kainulainen_Science2014:{citation:'(Kainulainen et al., Science, 2014)',summary:String.raw`基于分子云消光图重建的体密度统计（本例提供论文观测表），得到密度分布及恒星形成阈值的约束：
$$p(s)∝\operatorname{exp}\!\left[-\frac{(s-\mu)^2}{2\sigma_s^2}\right],\quad n_{\mathrm{crit}}\approx(5\pm2)\times10^3\,\mathrm{cm}^{-3}$$`},
  };
  const options=document.querySelector('#demo-picker .demo-options');options.replaceChildren();
  for(const task of discoveryTasks){
    const reference=references[task.name],card=el('article',undefined,'demo-option'),enabled=task.available&&!discoveryLoading;card.dataset.discoveryTask=task.name;card.tabIndex=enabled?0:-1;card.setAttribute('aria-disabled',String(!enabled));card.setAttribute('aria-label',(currentLocale==='en'?'Load study: ':'加载研究：')+task.subject_zh);
    const header=el('div',undefined,'discovery-card-header'),topic=el('span',task.topic,'discovery-topic'),citation=el('a',reference.citation,'discovery-citation'),title=el('b',task.subject_zh);
    citation.href=task.publisher_url;citation.target='_blank';citation.rel='noopener noreferrer';citation.title=task.title;header.append(topic,citation);
    const description=el('p',currentLocale==='en'?task.description_en:task.description_zh,'discovery-description'),summary=el('div',undefined,'discovery-summary markdown-rendered');summary.append(markdownFragment(reference.summary));
    card.onclick=event=>{if(enabled&&!event.target.closest('a'))loadDiscoveryTask(task.name)};
    card.onkeydown=event=>{if(enabled&&event.target===card&&['Enter',' '].includes(event.key)){event.preventDefault();loadDiscoveryTask(task.name)}};
    card.append(header,title,description,summary);if(!task.available)card.append(el('span',currentLocale==='en'?'Data unavailable':'数据尚未就绪','discovery-unavailable'));options.append(card);
  }
}
async function openDiscoveryPicker(){
  $('demo-picker').showModal();renderDemoPickerLanguage();$('demo-picker-status').textContent=currentLocale==='en'?'Checking data…':'正在检查任务数据…';
  try{const result=await api('/api/data/discovery-tasks');discoveryTasks=result.tasks;renderDiscoveryTasks();$('demo-picker-status').textContent=''}catch(error){$('demo-picker-status').textContent=error.message}
}
function applyDiscoveryPrompts(p){
  clearTimeout(promptRefreshTimer);promptRefreshToken+=1;
  promptEdited={user:true,system:true};promptDefaults={...promptDefaults,problem_description:p.problem_description,system_prompt:p.system_prompt,user_prompt:p.user_prompt};
  $('data-agent-input').value=p.data_agent;$('problem-description').value=p.problem_description;$('evaluator-agent-input').value=p.evaluator_agent;$('system-prompt').value=p.system_prompt;$('prompt').value=p.user_prompt;
  const evaluatorAgent=document.querySelector('.evaluator-agent'),evaluatorToggle=$('evaluator-agent-toggle'),open=Boolean(p.evaluator_agent?.trim());if(evaluatorAgent&&evaluatorToggle){evaluatorAgent.hidden=!open;evaluatorToggle.setAttribute('aria-expanded',String(open))}
  renderDataAgentControl();renderEvaluatorAgentControl();renderComposerControl();renderWorkflowNextControls();requestAnimationFrame(fitProblemDescription);
}
async function loadDiscoveryTask(name){
  if(discoveryLoading)return;discoveryLoading=true;renderDiscoveryTasks();$('demo-picker-status').textContent=currentLocale==='en'?'Mounting read-only inputs…':'正在只读加载数据…';
  try{
    const generation=serverSessionGeneration,available=await api('/api/session/capabilities',undefined,'GET');
    if(generation!==serverSessionGeneration)return;
    const result=await api('/api/data/discovery-tasks/load',{name});
    if(generation!==serverSessionGeneration)return;
    const data=session.data_agent_settings,searchOnly=['prepare-discovery-handoff','fit-before-ranking','stable-observational-search'];
    const prepared=await api('/api/data/agent/settings',{tools:data.tools.filter(name=>!['validate_discovery_contract','calibrate_observation_scatter'].includes(name)),skills:(data.skills||[]).filter(name=>!searchOnly.includes(name))},'PUT');
    if(generation!==serverSessionGeneration)return;syncSession(prepared);
    const configured=await api('/api/session/settings',{tools:available.default_tools,skills:available.default_skills.filter(name=>![...searchOnly,'validate-observational-discovery'].includes(name)),force_initial_diagnostics:false,ranking_metric:'mse',larger_is_better:false});
    if(generation!==serverSessionGeneration)return;syncSession(configured);
    const evaluator=await api('/api/evaluator?selected=default',undefined,'GET');
    if(generation!==serverSessionGeneration)return;
    await api('/api/evaluator',{selected:'default',source:evaluator.source},'PUT');
    if(generation!==serverSessionGeneration)return;
    await loadEvaluatorConfiguration();await syncSettingsForm();
    if(generation!==serverSessionGeneration)return;
    applyDiscoveryPrompts(result.prompts);
    $('demo-picker').close();filesSignature='';await refreshFiles();selectCenterTab('prepare');
    notice(currentLocale==='en'?'Read-only inputs and stage-specific prompts are ready. Prepare the data, then build and confirm the evaluator before searching.':'已只读加载数据并填入各阶段提示词。请先整理数据，再构建并确认评测器。');
  }catch(error){$('demo-picker-status').textContent=error.message}
  finally{discoveryLoading=false;renderDiscoveryTasks()}
}
$('create-demo').onclick=event=>{event.preventDefault();openDiscoveryPicker()};$('demo-picker-close').onclick=()=>$('demo-picker').close();$('demo-picker').onclick=event=>{if(event.target===$('demo-picker'))$('demo-picker').close()};

async function uploadDataFiles(files){const uploaded=[...files];if(!uploaded.length)return;for(const file of uploaded){const response=await fetch('/api/workspace/upload?path='+encodeURIComponent(file.name),{method:'PUT',headers:conversationHeaders(),body:file});if(!response.ok)throw Error(file.name+': '+await responseError(response,_('uploadFailed')))}await refreshFiles()}
const dataDrop=$('data-drop'),dataIngest=$('data-ingest'),dataIngestHeading=dataIngest.querySelector('.ingest-heading'),dataIngestIntro=document.createElement('div'),dataDropCopy=$('data-drop-copy');dataIngestIntro.className='data-ingest-intro';dataIngestIntro.append(...dataIngestHeading.querySelector('div').children);dataIngest.before(dataIngestIntro);dataDropCopy.className='data-ingest-prompt';dataIngest.append(dataDropCopy,$('data-upload'),$('data-file-input'));dataIngestHeading.remove();dataDrop.remove();$('data-upload').onclick=()=>$('data-file-input').click();$('data-file-input').onchange=dataGuard(async event=>{const files=[...event.target.files];event.target.value='';await uploadDataFiles(files)});dataIngest.ondragover=event=>{if(!event.dataTransfer.types.includes('Files'))return;event.preventDefault();dataIngest.classList.add('dragover')};dataIngest.ondragleave=event=>{if(!dataIngest.contains(event.relatedTarget))dataIngest.classList.remove('dragover')};dataIngest.ondrop=dataGuard(async event=>{event.preventDefault();dataIngest.classList.remove('dragover');await uploadDataFiles(event.dataTransfer.files)});
const dataIngestIntroCopy=document.createElement('div');dataIngestIntroCopy.className='data-ingest-intro-copy';dataIngestIntroCopy.append(...dataIngestIntro.children);dataIngestIntro.append(dataIngestIntroCopy);
function structureStepHeading(host){const copy=document.createElement('div');copy.className='step-heading-copy';copy.append(...host.children);host.append(copy);host.classList.add('step-heading')}
structureStepHeading(document.querySelector('.data-agent-heading>div:first-child'));structureStepHeading(document.querySelector('#variable-config-card .variable-card-heading>div:first-child'));const taskProblemHeading=document.createElement('div');taskProblemHeading.className='task-problem-heading step-heading';$('task-problem-title').before(taskProblemHeading);const taskProblemCopy=document.createElement('div');taskProblemCopy.className='step-heading-copy';taskProblemCopy.append($('task-problem-title'),$('task-problem-help'));taskProblemHeading.append(taskProblemCopy);
const variableHeadingCopy=document.querySelector('#variable-config-card .step-heading-copy'),variableHeadingActions=document.querySelector('#variable-config-card .variable-card-actions');variableHeadingCopy.querySelector('h3').after($('data-refresh'));variableHeadingActions.remove();
const variableTableHead=document.querySelector('#variable-config-card>.variable-table-head');$('variable-role-table').prepend(variableTableHead);
const runVariableTable=document.querySelector('#run-variable-preview .variable-role-table'),runVariableTableHead=document.querySelector('#run-variable-preview>.variable-table-head');runVariableTableHead.firstElementChild.remove();runVariableTableHead.firstElementChild.remove();runVariableTable.prepend(runVariableTableHead);
let variableTableWidth=-1;new ResizeObserver(entries=>{const width=entries[0].contentRect.width;if(width===variableTableWidth)return;variableTableWidth=width;requestAnimationFrame(()=>{for(const description of document.querySelectorAll('#variable-role-body .variable-description'))resizeVariableDescription(description)})}).observe($('variable-role-table'));
let scatterResizeFrame=0;new ResizeObserver(()=>{if(mainLayout.classList.contains('resizing'))return;cancelAnimationFrame(scatterResizeFrame);scatterResizeFrame=requestAnimationFrame(renderActivePlot)}).observe($('plot-stage'));
$('close-preview').onclick=()=>$('preview').close();mountEvaluatorWorkbench();for(const [control,label] of [['data-api-key','data-api-key-label'],['api-key','api-key-label'],['evaluator-agent-api-key','evaluator-agent-api-key-label'],['R','restart-count-label'],['C','branch-count-label']])normalizeCompositeField(control,label);mountEvaluatorHighlight();mountRequestedLayout();mountConversationUI();mountMarkdownModeButtons();mountCandidateFormulaControl();applyTheme();applyLanguage();selectCenterTab(document.querySelector('.tabs button.active')?.id.replace(/-tab$/,'')||'prepare');document.documentElement.classList.add('ui-ready');requestAnimationFrame(fitProblemDescription);pollStatus();pollEvents();pollFiles();setInterval(renderActivity,1000);
