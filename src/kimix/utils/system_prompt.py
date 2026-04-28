from typing import Optional, Callable
from pathlib import Path
import os
from enum import Enum
from kaos.path import KaosPath
import kimix.base as base
from kimi_cli.soul.agent import BuiltinSystemPromptArgs

# This system prompt is designed to stop the modern LLM from over thinking and hallucination
_SYSTEM_PROMP = (
    '{AGENT_ROLE}.\n{RULES}\n{NOTE}\n{NUMBERED}{AGENTS_MD}{SKILLS}\n'
)

_NOTE = (
    'Note:\n'
    '1. For long tasks, use `Run`/`Python` with `run_in_background=true`, then manage via '
    '`TaskList`, `TaskOutput`, `Input`, `TaskStop`. Return control immediately after starting.\n'
    '2. For complex or multi-step tasks, use `SetTodoList` to track progress.'
)

class SystemPromptType(Enum):
    Worker = 0
    TodoMaker = 1
    SwarmCoordinator = 1
    

def get_system_prompt(
        is_sub_agent: bool = False,
        plan_mode: bool | None = None,
        yolo: bool | None = None,
        work_dir: Optional[KaosPath] = None,
        skills_dirs: Optional[list[KaosPath]] = None,
        agent_role: SystemPromptType = SystemPromptType.Worker
) -> Callable[[BuiltinSystemPromptArgs], str]:
    agent_md = (Path(str(work_dir)) if work_dir is not None else Path(
        os.curdir)) / 'AGENTS.md'
    plan_mode = plan_mode if plan_mode is not None else base._default_plan_mode
    yolo = yolo if yolo is not None else base._default_yolo

    def system_prompt_func(args: BuiltinSystemPromptArgs) -> str:
        items: list[str] = []
        rules: str | None = None
        note_doc = ''
        agent_md_doc = ''
        skill_doc = ''
        match agent_role:
            case SystemPromptType.Worker:
                rules = (
                    'Rules: Direct output only. No chain-of-thought. No analysis. '
                    'No step-by-step. No reasoning blocks. No thinking-effort. zero preamble. '
                    'No postamble. Minimal explanation. Concisely. Shortly.'
                )
                role_doc = 'You are a terse ' + ('sub-agent' if is_sub_agent else 'coder')
                note_doc = _NOTE
                if not is_sub_agent:
                    items.append(
                        'Use `Agent` for: "parallelizable independent subtasks", '
                        '"large-context analysis or tasks needing different expertise", '
                        '"permission-graded operations like read-only analysis or sandboxed execution".'
                    )
                if args.KIMI_OS == 'Windows':
                    items.append('No Shell commands; use `Run`/`Python` instead.')
                else:
                    items.append(f'Shell: {args.KIMI_SHELL}.')
                if plan_mode:
                    items.append('Plan mode: draft plan, run `ExitPlanMode`, then execute.')
                start_index = 3
                if yolo:
                    items.append(
                        'Yolo mode: act decisively without asking. '
                        'Never write outside working directory or change system settings(if not asked).'
                    )
            case SystemPromptType.TodoMaker:
                role_doc = '''You are a plan maker.
Record all steps with `Note` per turn, one-by-one
Do not write multiple steps at once.
'''
                start_index = 1
            case SystemPromptType.SwarmCoordinator:
                role_doc = (
                    'You are a swarm coordinator. Decompose the task into sub-agent nodes '
                    'using AddNode and AddEdge tools to build a dependency DAG.\n'
                    '- AddNode: create a sub-task with a clear, actionable prompt\n'
                    '- AddEdge: set execution order (upstream -> downstream)\n'
                    'Rules: keep graph acyclic; add edges only when necessary to maximize parallelism.\n'
                    'After building, report all nodes and edges.\n\n'
                )
                start_index = 1


        if agent_md.is_file():
            agent_md_content = agent_md.read_text(encoding='utf-8', errors='replace')
            agent_md_doc = f'AGENTS.md:\n```\n{agent_md_content}\n```\n'
        items.append('Use `SkillRag` tool to search and retrieve skills.')
        if args.KIMI_SKILLS:
            skill_doc = f'Skills:\n{args.KIMI_SKILLS}\n'

        numbered_block = ''.join(
            f'{i + start_index}. {item}\n' for i, item in enumerate(items)
        )

        return _SYSTEM_PROMP.format(
            AGENT_ROLE=role_doc.strip(),
            RULES=rules.strip() if rules else '',
            NOTE=note_doc,
            NUMBERED=numbered_block,
            AGENTS_MD=agent_md_doc,
            SKILLS=skill_doc,
        ).strip()
    return system_prompt_func
