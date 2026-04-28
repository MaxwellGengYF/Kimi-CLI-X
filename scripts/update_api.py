from kimix.utils import *
prompt('''
according to python files under `src/kimix/utils`,
update `.agents/skills/api/SKILL.md`
''', session = create_session(), close_session_after_prompt=True)
clear_default_context()
# double check
prompt('''
verify and update API in `.agents/skills/api/SKILL.md`, according to `src/kimix/utils`.
''')