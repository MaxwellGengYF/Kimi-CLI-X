from kimi_utils import *


def implement_file(
    file_path,
    requires,
    validate_after_work: bool = False
):
    try:
        file_path = ','.join(file_path)
    except TypeError:
        pass
    s = f'In file {str(file_path)}, finish this requiremets:\n'
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
        s = f'In file {str(file_path)}, check and validate all requirements finished:\n{req_str}'
        prompt(s)
        
        
        
