# URL Helpers

A Directus extension bundle that provides two interfaces for managing URL-friendly fields: **Permalink** and **Slug**.

Both interfaces auto-generate values from other fields using templates, with manual editing support and configurable auto-generation triggers.

## Interfaces

### Permalink

Generates URL paths from other fields. Each path segment is slugified individually, preserving the `/` structure.

For example, a source template of `{{year}}/{{title}}` with a title of "My First Post" and a year of "2025" produces `2025/my-first-post`.

**Options:**

| Option | Description |
|---|---|
| Source | Template for generating the permalink value (e.g. `{{title}}`). Uses other field values. |
| Prefix | Template prepended to the value in the preview (e.g. `https://example.com/blog/`). |
| Suffix | Template appended to the value in the preview (e.g. `/`). |
| Icon Left | Icon displayed before the preview. |
| Custom Replacements | A list of custom replacements (source/target pairs) applied before slugification. Useful for words like "iPhone" → "iphone" that would otherwise be split into "i-phone". |
| Auto Generate | When to auto-generate: on create, on update, or both. Defaults to on create. |

### Slug

Generates a URL-safe slug from other fields. The entire value is slugified as a single string.

For example, a source template of `{{title}}` with a title of "My First Post" produces `my-first-post`.

**Options:**

| Option | Description |
|---|---|
| Source | Template for generating the slug value (e.g. `{{title}}`). Uses other field values. |
| Prefix | Template prepended to the value when editing (e.g. `/blog/`). |
| Suffix | Template appended to the value when editing (e.g. `/`). |
| Icon Left | Icon displayed before the preview. |
| Custom Replacements | A list of custom replacements (source/target pairs) applied before slugification. Useful for words like "iPhone" → "iphone" that would otherwise be split into "i-phone". |
| Auto Generate | When to auto-generate: on create, on update, or both. Defaults to on create. |

## Features

- **Template-based generation** - Use `{{field_name}}` syntax to reference other fields in the same item.
- **Manual override** - Click the edit button to manually set a value. Manual edits stop auto-generation until reset.
- **Regenerate button** - When the source fields change and the current value differs, a regenerate button appears.
- **Clickable preview** - If the prefix starts with `http://` or `https://`, the preview becomes a clickable link.
- **Cancel editing** - Press Escape while editing to restore the previous value.

## Installation

```bash
npm install @nialto-services/directus-extension-url-helpers
```

## Attribution

This extension was originally based on [directus-extension-wpslug-interface](https://github.com/dimitrov-adrian/directus-extension-wpslug-interface) by dimitrov-adrian, licensed under GPL-3.0.
