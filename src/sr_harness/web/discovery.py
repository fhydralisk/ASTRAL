"""Read-only observation tasks for the interactive discovery picker."""
from __future__ import annotations

import os
from pathlib import Path
from .discovery_catalog import CASES


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


def prompts(case, paths, system_prompt):
    inputs = '\n'.join('- ' + path.name + ('/' if path.is_dir() else '') for path in paths)
    task = case['task']
    evidence = ('不要查阅论文目标公式或以前的复现实验。由数据选择变量与函数形式，不预设结论。'
                '先比较常数和简单基线，使用独立天体/观测分组验证，系数只在训练集拟合；'
                '保留外部测试集直至表达式冻结。处理误差、上限、选择效应和共享变量，'
                '避免定义恒等式与标签泄漏。噪声数据不追求零误差；区分预测效果、结构恢复与物理解释。')
    preparation = (f'{task}\n本任务只使用以下只读输入：\n{inputs}\n'
                   '只读输入不得修改。先读取可用的 validate-observational-discovery 技能，'
                   '检查元数据和一个小样本，再分块处理全部数据；先保存可执行处理脚本、'
                   '测量诊断和小型中间表，随后检查再扩展。不要输出完整大数组。'
                   '保留单位、来源、误差、检测标志和分组标识。把结果写入 context.data/，'
                   '按系统要求保存manifest.json与NPY并调用validate_context_data。'
                   '另保存analysis_plan.json，含target、features、group_variable、rationale、limitations；'
                   '标识和误差列默认不作预测变量。若证据不足，说明缺少什么，不制造关系。\n' + evidence)
    problem = task + '\n根据数据准备结果和analysis_plan.json确认目标与特征，搜索最简且可验证的数学关系或分布。\n' + evidence
    evaluator = ('可选步骤：先检查已准备的数据与analysis_plan.json。若默认逐样本回归评测足够，'
                 '说明可直接使用默认评测器，不修改它。只有分布、误差权重、删失/上限或分组验证'
                 '需要时才构建评测器；不得编码任何论文目标函数或对某种公式给予奖励。'
                 '确保训练拟合与验证隔离，报告原单位误差、样本数、覆盖率和简单基线；'
                 '小样本指标不稳定时明确说明。用小型自检验证接口与数值，再保存评测器供用户确认。\n'
                 '科学任务：' + task)
    return {'data_agent': preparation, 'problem_description': problem,
            'evaluator_agent': evaluator, 'system_prompt': system_prompt + '\n\n观测科学任务约束：\n' + evidence,
            'user_prompt': problem}


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
