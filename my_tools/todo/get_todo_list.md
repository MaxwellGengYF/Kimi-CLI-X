# GetTodoList

A todo list tool to retrieve the current todo list from the database.

## When to Use

- When you need to check the current status of tasks
- Before updating a todo list to see existing items
- To verify what work has been completed or is in progress
- When resuming work on a complex task

## When NOT to Use

- When you already have the todo list in context
- For simple tasks that don't need tracking

## Parameters

- **todos**: List of todo items (optional, used for compatibility), each with:
  - **title**: Task description
  - **status**: `"pending"`, `"in_progress"`, or `"done"`

## Returns

The current todo list from the database, containing items with:
- **title**: Task description
- **status**: `"pending"`, `"in_progress"`, or `"done"`

## Example

```json
{
  "todos": []
}
```

## Tips

- Call this before SetTodoList if you need to see existing tasks
- Use this to check progress before adding new tasks
- Returns empty list if no todo list exists for the current session
