"""Seven scientific examples: comparison cards, read-only inputs and editable prompts."""
from __future__ import annotations

import os
from pathlib import Path

# Paper conclusions are display-only and are never used to build agent prompts.
CASES = [{'topic': 'Gaia',
  'name': 'Chen_NatureAstronomy2023',
  'title': 'The use of double-mode RR Lyrae stars as robust distance and metallicity indicators',
  'publisher_url': 'https://www.nature.com/articles/s41550-023-02011-y',
  'subject_zh': '双模 RR Lyrae 周期—周期比—金属丰度',
  'relation_zh': 'SDSS: [Fe/H] = -173*log10((P1O/PF)/0.745) - 6.62*log10(P1O/0.37) - 1.76；见 Eq.1 '
                 '的不确定度。',
  'caveat_zh': '优先回归样本。SDSS/LAMOST 标定分开；Gaia DR3 选源与视差用于距离标定。',
  'files': ['41550_2023_2011_MOESM1_ESM.txt'],
  'data_stage': '作者原始发布参数表 · 303 颗恒星',
  'task': '我想评估双模脉动恒星的周期测量能否用于估计光谱金属丰度，以及这种估计能否跨巡天使用。请以 SDSS 作为开发样本，LAMOST 作为表达式冻结后才使用的外部检验；先交叉匹配天体，外部检验中排除与开发样本重复的恒星。同一天体的记录不能跨训练与验证集合。保留并使用金属丰度测量误差，同时检查巡天系统差异与额外散布，不把形式误差视为全部误差。可在训练样本上预估并冻结统一额外散布，报告它也可能包含基线失配；所有候选共享该误差模型，不随验证分数调整。请将开发样本和未参与搜索的外部检验样本分别保存，明确评测器需执行的划分和误差处理。核实周期变量的定义关系，由数据决定是否存在可解释的关系及其形式。'},
 {'topic': 'Gaia',
  'name': 'Xiang_Nature2022',
  'title': 'A time-resolved picture of our Milky Way’s early formation history',
  'publisher_url': 'https://www.nature.com/articles/s41586-022-04496-5',
  'subject_zh': '年龄—金属丰度及轨道作用量',
  'relation_zh': 'mean_age([Fe/H]) = age0 + a*[Fe/H]，厚盘窄年龄—金属丰度序列；不是全银河统一函数。',
  'caveat_zh': '年龄为等龄线模型推断量；按族群、年龄区间划分，处理选择函数与年龄误差。',
  'files': ['41586_2022_4496_MOESM3_ESM.txt'],
  'data_stage': '作者发布恒星目录 · 年龄为模型推断量',
  'task': '我想研究银河系早期盘族群的年龄与化学丰度之间是否存在可解释的关系，而不是训练一个适用于整个目录的年龄预测器。请先核查年龄和轨道量的质量标志，不用宇宙年龄上限截断目录年龄；年龄误差或相对误差筛选须披露目标依赖并作为敏感性检查。保持研究域的完整丰度覆盖，依据化学丰度及运动学给出可复核的族群选择方案，并说明它为何适合这个研究问题；不要根据某条候选关系拟合得好不好来挑选恒星。先保存选择规则及各步样本数，再实际应用筛选，将一个科学上可比较的族群送入首轮符号回归。其它族群保留作对照，不混入同一拟合。保留年龄误差、观测分组及选择边界，检查结论对合理边界变化是否稳定；若族群无法可靠区分，应说明不足。关系是否存在、符号、函数形式及散布均由数据检验。'},
 {'topic': 'Gaia',
  'name': 'Li_Nature2023',
  'title': 'Stellar initial mass function varies with metallicity and time',
  'publisher_url': 'https://www.nature.com/articles/s41586-022-05488-1',
  'subject_zh': '初始质量函数斜率随丰度/时代变化',
  'relation_zh': 'dN/dM ∝ M^(-alpha)，alpha 随金属丰度及恒星族群时代变化；0.3–0.7 Msun 范围。',
  'caveat_zh': 'Gaia 视差/自行与 LAMOST 联用；不能把单星质量直接当作 IMF 斜率标签，须分箱及选择函数/双星修正。',
  'files': ['jdli22_imf.csv'],
  'data_stage': '作者发布恒星样本 · 需估计分布',
  'task': '从恒星样本研究质量分布是否随化学丰度及动力学族群变化。处理样本完备性、选择函数和双星等限制；质量函数需要由样本统计估计，不能将单星质量当分布参数。先核实作者发布的nu_i局部数密度摘要及其生成分组：逐项检查mass_bin宽度归一、mh_bin、jz_bin和观测plate的含义，不假定公开nu_i已经是各金属丰度子群的每单位质量密度；生成口径不明时保存摘要和缺项，主要IMF任务标记replication_status=insufficient_measurements，可另行明确范围做摘要预测，但不能混称主要结论复现。若用其研究质量、高度与化学丰度的联合关系，应注明固定0.5 dex是作者拟合假设而非逐星实测误差，并按观测plate分组。保留质量区间、观测误差、完备性及族群标识，根据实际测量交付质量分布似然或发布密度摘要回归，不能以族群平均质量替代质量函数。没有上游选择函数、双星与年代证据时，仅报告已验证的模型组件，不宣称完整IMF结论。若分布参数无法稳定估计或卡在拟合边界，应报告失败并修正统计表示。'},
 {'topic': 'FRB',
  'name': 'Feng_Science2022',
  'title': 'Frequency-dependent polarization of repeating fast radio bursts—implications for their '
           'origin',
  'publisher_url': 'https://www.science.org/doi/10.1126/science.abl7759',
  'subject_zh': '频率相关退偏振及磁离子环境参数关系',
  'relation_zh': 'p/p0 = exp(-2*sigma_RM^2*lambda^4)；再研究 sigma_RM 与 |RM|、散射时标的关系。',
  'caveat_zh': '退偏振公式并非本文首创；37 份校准观测约 3.73 GB。注意偏振格式差异、频带内退偏振、噪声上限及同源爆发的相关性。',
  'files': [],
  'data_stage': '校准后的原始 PSRFITS · 37 份观测',
  'task': '从校准射电爆发观测提取可靠的频率分辨偏振等物理测量，探索频率、偏振和磁离子环境量之间的数据支持关系。文件可能为.calibP或无扩展名，按FITS内容识别。如有可用的PSRFITS元数据检查工具可先使用；逐文件检查POL_TYPE、轴顺序、校准、权重和单位；四路观测不保证已是IQUV。保留背景、噪声、检测与上限、观测和天体标识。每个频率子带须保留其爆发和天体来源；先在同一天体内比较频率依赖，允许使用由频率标准换算的物理波长坐标但不预设其函数形式；跨仪器数据需保留校准与观测时段混杂，再讨论跨天体差异，验证时保留整次观测。核对检测与积分信噪比，噪声主导的偏振估计应保留不确定度或作为上限处理，不直接混成无误差标签。'},
 {'topic': 'FRB',
  'name': 'Li_Nature2021',
  'title': 'A bimodal burst energy distribution of a repeating fast radio burst source',
  'publisher_url': 'https://www.nature.com/articles/s41586-021-03878-5',
  'subject_zh': '重复 FRB 的能量分布（扩展阅读）',
  'relation_zh': '爆发能量分布使用 log-normal 与 generalized Cauchy 组合描述。',
  'caveat_zh': '与严格的多变量关系发现有区别，列为分布建模补充。能量由流量等推导，避免标签泄漏；附勘误入口。',
  'files': ['41586_2021_3878_MOESM3_ESM.csv'],
  'data_stage': '作者原始发布爆发表 · 1652 次爆发',
  'task': '从重复射电爆发的流量、宽度、频带和时间等测量研究能量分布及其稳定性。先核实表格实际分隔符与误差记法，检查完备阈值、分箱与非分箱结果。不把能量的定义公式当作发现。本轮目标是总体能量分布及跨观测时段稳定性，不是用宽度和峰值流量预测单次能量。保留每次爆发、观测时段和检测限制，按完整时段划分开发训练与验证；区分按能量bin的爆发率与归一化概率密度，缺少bin宽或曝光定义时不能声称二者等价。坐标变换与概率测度必须分别记录，交付可评测分布的统计表示，明确密度测度及归一化范围，不预设分布族或峰的数量。'},
 {'topic': 'ISM',
  'name': 'Chiang_NatureAstronomy2026',
  'title': 'Cosmic CO and [C\u2009II] backgrounds and the fuelling of star formation over 12\u2009'
           'Gyr',
  'publisher_url': 'https://www.nature.com/articles/s41550-026-02798-6',
  'subject_zh': '宇宙分子气体演化与恒星形成律',
  'relation_zh': 'Omega_H2(z)≈1.9e-4*(1+z)^2.3/[1+((1+z)/2.8)^6.5]；宇宙平均KS型关系指数约1.5。',
  'caveat_zh': '这是星系总体/宇宙平均ISM，非单云数据；CO-H2转换因子与MCMC后验相关性重要。Code Ocean完整链未下载。',
  'files': ['rho_CO_CII--8_z_bins.ecsv', 'Chiang_et_al_25_v2/Data'],
  'data_stage': '作者发布统计测量与协方差 · 非原始全天图',
  'task': '从宇宙谱线与背景统计测量研究气体和恒星形成随红移的变化。优先使用独立红移分箱测量与协方差，辨别观测约束、转换假设和模型后验。不要把稠密最佳拟合曲线当独立观测重新发现其生成函数。先明确本轮能检验的是谱线观测关联还是气体密度与恒星形成关系；后者需要注明转换及配对恒星形成率数据，当前8点是CO谱线总和，不能当作CO(1–0)或H2；同一模型产生的SFR后验摘要也不能充作独立观测。若缺少主目标所需转换及独立SFR，保存replication_status=insufficient_measurements及blocked_reason，停在测量审计，不以辅助曲线拟合替代主发现。评测保留非对称误差与可获得的协方差，小样本逐箱留出并检查结果稳定性。'},
 {'topic': 'ISM',
  'name': 'Kainulainen_Science2014',
  'title': 'Unfolding the laws of star formation: The density distribution of molecular clouds',
  'publisher_url': 'https://www.science.org/doi/10.1126/science.1248724',
  'subject_zh': '分子云体密度分布与恒星形成',
  'relation_zh': '从消光图重建体密度PDF，比较其宽度与恒星形成活动，并约束密度阈值/阈值以上效率。',
  'caveat_zh': '合并统计行不能作为独立训练样本；体密度由投影图反演，受几何假设及消光图分辨率限制。',
  'files': ['table_S1_transcribed.csv'],
  'data_stage': '论文观测表转录 · 非原始消光图',
  'task': '研究分子云密度分布的测量摘要与恒星形成活动的关系。核实单位、误差、独立云标识，排除合并统计行。说明没有原始消光图时不能检验投影反演步骤，只能复现参数表层面的关联。按独立云复合体进行留组验证，保留样本少带来的不确定性；云名、排序和合并记录不得作为物理预测变量。可独立复算低恒星形成活动云的最大对数密度摘要，但需核实H核与H2密度约定；由既定阈值计算的致密气体质量不能反过来验证同一阈值。原图或必要密度定义缺失时，将主复现状态标为insufficient_measurements并说明缺项，不用其它回归替代。'}]


def prompts(case, paths, system_prompt):
    """Draft visible user instructions; comparison-card answers stay out."""
    inputs = "\n".join("- " + path.name + ("/" if path.is_dir() else "") for path in paths)
    task = case['task']
    evidence = ('不要查阅论文目标公式或以前的复现实验。由数据选择变量与函数形式，不预设结论。'
                '比较简单基线，保留误差、来源与选择限制，不将定义恒等式或标签泄漏作为发现。'
                '表达式冻结前不使用外部测试数据。区分预测效果、结构恢复与物理解释。')
    preparation = (f'{task}\n本任务只使用以下只读输入：\n{inputs}\n'
                   '读取prepare-discovery-handoff与validate-observational-discovery技能，'
                   '检查元数据和小样本，再保存可重复处理脚本、测量诊断及中间表。输入不得修改。'
                   '将数组和manifest保存到context.data/，调用validate_context_data；'
                   '保存analysis_plan.json和discovery_contract.json，用validate_discovery_contract检查。'
                   '完成后报告实际target、features、固定划分、objective（排序取最小）及局限；分布任务说明测度与支持区间，供用户在现有任务设置中确认；'
                   '另外给出一段可复制到符号回归User Prompt的交接说明，不推荐公式。'
                   '缺少关键测量时保留资料并说明缺项，不替换研究目标。\n' + evidence)
    problem = task + '\n根据实际准备结果探索可验证的数学关系或分布。\n' + evidence
    search = (problem + '\n使用evaluate_observational_formula比较候选、submit_observational_formula提交，'
              '训练统计使用observational_statistics。先读取准备Agent给出的交接说明；'
              '若尚未明确实际目标、允许特征、划分、评测目标或测量限制，请向用户索取，勿猜测。'
              '按已选择的ObservationalEvaluator评测，系数只在训练集拟合。'
              '无分箱分布的表达式是指定测度下的密度，不是单次观测的预测。')
    evaluator = ('可选：选择ObservationalEvaluator后无需评测器构建Agent。'
                 '仅在内置能力无法满足明确的科学要求时构建并验证自定义评测器；'
                 '不得编码论文目标函数或奖励特定公式。\n' + task)
    return {'data_agent': preparation, 'problem_description': problem,
            'evaluator_agent': evaluator, 'system_prompt': system_prompt, 'user_prompt': search}


def project_root():
    configured = os.environ.get('ASTRAL_PROJECT_ROOT')
    if configured:
        return Path(configured).expanduser().resolve()
    for path in (Path.cwd(), *Path(__file__).resolve().parents):
        if (path / 'data').is_dir() and (path / 'pyproject.toml').exists():
            return path
    return Path.cwd()


def sources(case):
    root = project_root()
    if case['name'] == 'Feng_Science2022':
        candidates = [root / '.cache/replication_raw/ScienceDB',
                      root / 'data/spark04/FRB/Feng_Science2022/ScienceDB']
        for directory in candidates:
            if directory.is_dir() and len([p for p in directory.glob('*/*') if p.is_file() and p.suffix in {'', '.calibP'} and p.stat().st_size > 0]) == 37:
                return sorted(p for p in directory.iterdir() if p.is_dir())
        return []
    return [root / 'data' / case['topic'] / case['name'] / name for name in case['files']]


def ready(paths):
    return bool(paths) and all(p.is_file() and p.stat().st_size > 0 or
                               p.is_dir() and any(p.iterdir()) for p in paths)


def list_cases():
    return [{k: v for k, v in case.items() if k not in {'files', 'task'}} |
            {'available': ready(sources(case))} for case in CASES]


def load_case(session, name):
    case = next((case for case in CASES if case['name'] == name), None)
    if case is None:
        raise ValueError('Unknown scientific discovery task')
    paths = sources(case)
    if not ready(paths):
        raise FileNotFoundError('任务数据尚未就绪；请先下载或接通原始数据目录。')
    with session.lock:
        if session.state != 'idle' or any(t and t.is_alive() for t in
                (session.data_thread, session.evaluator_agent_thread)):
            raise ValueError('请在空闲的新会话中加载科学发现任务。')
        context = session.workspace / 'context.data'
        if session.context.data or context.exists() and (not context.is_dir() or any(context.iterdir())):
            raise ValueError('当前已有处理后的数据，请新建会话后选择论文任务。')
        names = [p.name for p in paths]
        if len(names) != len(set(names)):
            raise ValueError('Task input names must be unique')
        for path in paths:
            logical = session.workspace / path.name
            if (logical.exists() or logical.is_symlink()) and not (
                    logical.is_symlink() and logical.resolve() == path.resolve()):
                raise FileExistsError(f'工作区已有同名文件：{path.name}；请新建会话。')
        preview = session.preview_initial_prompts({'problem_description': case['task']})
        drafted = prompts(case, paths, preview['system_prompt'])
        mounted = [session.workspace_manager.mount(path, readonly=True).name for path in paths]
        session.initial_prompt = drafted['problem_description']
        session.discovery_task = {'name': name, 'prompts': drafted}
        session.data_interaction_manager.publish_event('workspace_changed',
            {'operation': 'mounted', 'paths': mounted, 'read_only': True})
        return {'name': name, 'mounts': mounted, 'read_only': True, 'prompts': drafted}


def restore_mounts(session, name):
    """Restore only catalog-approved inputs, never arbitrary paths from a snapshot."""
    case = next((case for case in CASES if case['name'] == name), None)
    if case is None:
        raise ValueError('Unknown persisted scientific discovery task')
    paths = sources(case)
    if not ready(paths) or session.workspace_manager.read_only:
        return
    for path in paths:
        logical = session.workspace / path.name
        if logical.is_symlink() and logical.resolve() == path.resolve():
            session.workspace_manager.mount(path, readonly=True)
