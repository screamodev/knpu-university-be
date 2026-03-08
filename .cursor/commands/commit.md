---
description: Create a commit analyzing staged changes with a clear action-based message
---

# Create Conventional Commit

Analyze staged changes and create a commit using clear action-based messages.

## Instructions

1. Run `git diff --cached` to see staged changes
2. Run `git status` to see the overall state
3. Analyze the changes and determine the appropriate action
4. Create a commit with a properly formatted message

## Commit Types

| Type | When to use |
|------|-------------|
| `Create` | Adding new files, features, or components |
| `Update` | Modifying existing functionality or content |
| `Delete` | Removing files, features, or code |
| `Fix` | Bug fixes or error corrections |
| `Refactor` | Code restructuring without behavior change |
| `Move` | Relocating or renaming files/code |
| `Style` | Code formatting (no logic change) |
| `Test` | Adding or updating tests |
| `Docs` | Documentation changes |
| `Config` | Configuration or build system changes |

## Format

```
<Type> <description>
```

- **Type**: required, capitalized, from the list above
- **description**: detailed, imperative mood, no period, lowercase

## Examples

```
Create JWT refresh endpoint
Update null response handling in user service
Refactor order validation logic into separate module
Delete deprecated legacy migration scripts
Fix incorrect total calculation when applying discount
Docs update API authentication section
```