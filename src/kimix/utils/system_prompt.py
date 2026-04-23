from typing import Optional, Callable
from string import Template
import sys
from pathlib import Path
import os
from kaos.path import KaosPath
import kimix.base as base
from kimi_cli.soul.agent import BuiltinSystemPromptArgs


_SYSTEM_PROMP = Template('''You are a ${AGENT_ROLE}.
Rules:
1. NO reasoning effort. NO thinking effort. NO explanations, apologies, or questions. Only concise language.
2. Minimal diff; preserve surrounding formatting.
3. For long tasks, use `Run`/`Python` with `run_in_background=true`, then manage via `TaskList`, `TaskOutput`, `Input`, `TaskStop`. Return control immediately after starting.
4. Python path `${PYTHON_PATH}`, ALWAYS use this python.
5. For complex or multi-step tasks, use `SetTodoList` to track progress.
${SPAWN}${SHELL}${PLAN_MODE}${YOLO_MODE}${RAG}
${AGENTS_MD}${SKILLS}
''')
_START_INDEX = 6


def get_system_prompt(
        is_sub_agent: bool = False,
        plan_mode: bool | None = None,
        yolo: bool | None = None,
        work_dir: Optional[KaosPath] = None,
        skills_dirs: Optional[list[KaosPath]] = None) -> Callable[[BuiltinSystemPromptArgs], str]:
    agent_md = (Path(str(work_dir)) if work_dir is not None else Path(
        os.curdir)) / 'AGENTS.md'
    plan_mode = plan_mode if plan_mode is not None else base._default_plan_mode
    yolo = yolo if yolo is not None else base._default_yolo

    def system_prompt_func(args: BuiltinSystemPromptArgs) -> str:
        role_doc = 'coding sub-agent' if is_sub_agent else 'coding agent'
        spawn_doc = None
        plan_mode_doc = None
        shell_doc = None
        agent_md_doc = None
        skill_doc = None
        rag = None
        yolo_doc = None
        index = _START_INDEX
        # Spawn
        if not is_sub_agent:
            spawn_doc = f'''{index}. Use `Spawn` for: "parallelizable independent subtasks", "large-context analysis or tasks needing different expertise", "permission-graded operations like read-only analysis or sandboxed execution".'''
            index += 1
        # Shell
        if args.KIMI_OS == 'Windows':
            shell_doc = f'''
{index}. No Shell commands; use `Run`/`Python` instead.
'''
        else:
            shell_doc = f'''
{index}. Shell: {args.KIMI_SHELL}.
'''
        index += 1
        # Plan
        if plan_mode:
            plan_mode_doc = f'''
{index}. Plan mode: draft plan, run `ExitPlanMode`, then execute.
'''
            index += 1
        # Yolo
        if yolo:
            yolo_doc = f'''
{index}. Yolo mode: act decisively without asking. Never write outside working directory or change system settings(if not asked).
'''
            index += 1
        if agent_md.is_file():
            agent_md_doc = agent_md.read_text(
                encoding='utf-8', errors='replace')
            agent_md_doc = f'''
AGENTS.md:
```
{agent_md_doc}
```
'''
        # Use RAG to search skill files, no need to list all skills
        rag = f'{index}: Use `SkillRag` tool to search and retrieve skills.'
        index += 1
        if skills_dirs:
            skill_doc = f'''
Skills dirs:
```
'''
            for i in skills_dirs:
                skill_doc += f'{str(i)}\n'.replace('\\', '/')
            skill_doc += '```'
        return _SYSTEM_PROMP.substitute(
            AGENT_ROLE=role_doc.strip(),
            PYTHON_PATH=sys.executable,
            RAG=(rag.strip() + '\n') if rag else '',
            PLAN_MODE=(plan_mode_doc.strip() + '\n') if plan_mode_doc else '',
            SHELL=(shell_doc.strip() + '\n') if shell_doc else '',
            SPAWN=(spawn_doc.strip() + '\n') if spawn_doc else '',
            AGENTS_MD=(agent_md_doc.strip() + '\n') if agent_md_doc else '',
            SKILLS=(skill_doc.strip() + '\n') if skill_doc else '',
            YOLO_MODE=(yolo_doc.strip() + '\n') if yolo_doc else '',
        ).strip()
    return system_prompt_func
