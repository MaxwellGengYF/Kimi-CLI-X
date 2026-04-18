import kimix.agent_utils as agent_utils
from kaos.path import KaosPath
from pathlib import Path
from . import constants
from kimix.kimi_utils import print_debug, print_warning
from . import utils


def set_arg():
    import argparse
    parser = argparse.ArgumentParser(description='Kimi Agent CLI')
    parser.add_argument('-c', '--clean', action='store_true',
                        help='Delete cache file after quit')
    parser.add_argument('-no_color', '--no_color', action='store_true',
                        help='Disable colorful print')
    parser.add_argument('-ralph', '--ralph', action='store_true',
                        help='Continue work until done (auto-loop)')
    parser.add_argument('-no_think', '--no_think', action='store_true',
                        help='Disable thinking mode')
    parser.add_argument('-plan', '--plan', action='store_true',
                        help='Enable plan mode')
    parser.add_argument('-no_yolo', '--no_yolo', action='store_true',
                        help='Disable YOLO mode')
    parser.add_argument('-s', '--skill-dir', type=str, nargs='*', default=None,
                        help='Specify custom skill directory(s)')
    parser.add_argument('--config', type=str, default=None,
                        help='Path to a JSON config file to load as default provider')
    parser.add_argument('--server', action='store_true',
                        help='Enable server mode')
    args = parser.parse_args()
    if args.no_color:
        agent_utils._colorful_print = False

    constants.CLEAN_MODE = args.clean
    if constants.CLEAN_MODE:
        print_debug('Clean mode ON, delete cache file after quit.')
    else:
        print_debug('Clean mode OFF.')

    if args.ralph:
        agent_utils._ralph_iterations = -1
        print_debug(
            'Ralph loop ON, continue work until done(or running OUT of your TOKEN!!!).')
    else:
        agent_utils._ralph_iterations = 0
        print_debug('Ralph loop OFF.')

    if args.no_think:
        agent_utils._default_thinking = False
        print_debug('Thinking OFF.')
    else:
        agent_utils._default_thinking = True
        print_debug('Thinking ON.')

    if args.plan:
        agent_utils._default_plan_mode = True
        print_debug('Plan mode ON.')
    else:
        agent_utils._default_plan_mode = False
        print_debug('Plan mode OFF.')

    if args.no_yolo:
        agent_utils._default_yolo = False
        print_debug('YOLO OFF.')
    else:
        agent_utils._default_yolo = True
        print_debug('YOLO ON.')

    if args.server:
        utils._server_mode = True
        print_debug('Server mode ON.')
    else:
        utils._server_mode = False
        print_debug('Server mode OFF.')

    # Handle --config argument
    if args.config:
        import json
        config_path = Path(args.config)
        if not config_path.is_absolute():
            abs_path = constants.curr_dir / config_path
            if not (abs_path.exists() and abs_path.is_file()):
                config_path = Path(__file__).parent.parent / config_path
            else:
                config_path = abs_path
        config_path = config_path.resolve()
        if config_path.exists() and config_path.is_file():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    agent_utils._default_provider = json.load(f)
            except json.JSONDecodeError as e:
                print_warning(
                    f'Invalid JSON in config file: {str(config_path)} ({e})')
            except Exception as e:
                print_warning(
                    f'Failed to load config file: {str(config_path)} ({e})')
        else:
            print_warning(f'Config file not found: {str(config_path)}')

    # Handle --skill-dir argument
    if args.skill_dir:
        for skill_dir in args.skill_dir:
            skill_dir_path = Path(skill_dir)
            if not skill_dir_path.is_absolute():
                skill_dir_path = constants.curr_dir / skill_dir_path
            # Normalize the path (resolve ., .., and symlinks)
            skill_dir_path = skill_dir_path.resolve()
            if skill_dir_path.exists() and skill_dir_path.is_dir():
                agent_utils._default_skill_dirs.append(
                    KaosPath(skill_dir_path))
                print_debug(f'Skill dir added: {str(skill_dir_path)}')
            else:
                print_warning(f'Skill dir not found: {str(skill_dir_path)}')
