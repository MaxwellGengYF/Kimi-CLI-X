# SetTodoList

A todo list tool to track and manage tasks.

## When to Use

- Tasks with multiple subtasks or milestones
- Multiple tasks in a single request
- Complex work that needs organization

## When NOT to Use

- Simple questions (e.g., "What language is used?")
- Tasks that take only a few steps
- Very specific, direct instructions

## Parameters

- **todos**: List of todo items, each with:
  - **title**: Task description
  - **status**: `"pending"`, `"in_progress"`, or `"done"`

## Example

```json
{
  "todos": [
    {"title": "Analyze requirements", "status": "done"},
    {"title": "Design architecture", "status": "in_progress"},
    {"title": "Implement feature", "status": "pending"}
  ]
}
```

## Tips

- Be flexible - start using it for complex tasks, stop if it turns out simple
- Update regularly to reflect progress
- Mark items as done and add new ones as needed
