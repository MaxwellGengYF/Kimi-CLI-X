from string import Template
generate_memory = Template('''Please compact our session context into a '${memory_file}' file in the current directory.

The '${memory_file}' should include:
1. **Project Overview**: Brief description of the project and its purpose
2. **Key Decisions**: Important decisions made during our session
3. **Current State**: What has been completed so far
4. **Important Files**: Key code files and their roles
5. **TODOs/Pending Tasks**: Any unfinished tasks or next steps
6. **Technical Notes**: Relevant technical details to remember

Use WriteFile tool to create/update '${memory_file}' with this structured content. Be concise but comprehensive.''')

read_memory = Template('''
read '${memory_file}' and remember.
'''.strip())