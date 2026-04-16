from kimix.kimi_utils import *
import kimix.kimi_utils as kimi_utils

def implement_file(
    file_path,
    requires,
    skill_name = None,
    validate_after_work: bool = False
):
    try:
        file_path = ','.join(file_path)
    except TypeError:
        pass
    s = ''
    
    if skill_name:
        try:
            if type(skill_name) is not str:
                new_str = ', '.join(skill_name)
                skill_name = new_str
        except:
            pass
        skill_found = False
        for skill_dir in agent_utils._default_skill_dirs:
            skill_path = Path(str(skill_dir)) / skill_name / 'SKILL.md'
            if skill_path.exists():
                skill_found = True
                break
        if skill_found:
            s += f'Use skill:{skill_name}. '
        else:
            print_warning(f'Skill {skill_name} not exists.')
    s += f'In file: {str(file_path)}, finish this requiremets:\n'
    req_str = ''
    try:
        for i in requires:
            req_str += f'* {i}\n'
    except TypeError:
        req_str = f'* {requires}\n'
    s += req_str
    prompt(s)
    if validate_after_work:
        clear_context()
        s = f'In file: {str(file_path)}, check and validate all requirements finished:\n{req_str}'
        prompt(s)
