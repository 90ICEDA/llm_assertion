# Four Prompt Input Methods

```mermaid
flowchart LR
    S["Specification"] --> M1["Method 1\nspec only"]

    S --> M2["Method 2\nspec + RTL"]
    R["RTL code"] --> M2

    S --> M3["Method 3\nspec + RTL + raw trace"]
    R --> M3
    T["Good/bad raw trace"] --> M3

    S --> M4["Method 4\nspec + RTL + trace summary"]
    R --> M4
    U["Good/bad divergence summary"] --> M4

    M1 --> O["SVA generation"]
    M2 --> O
    M3 --> O
    M4 --> O
```

## Input Difference

| Method | Spec | RTL | Raw Trace | Trace Summary |
|---|---:|---:|---:|---:|
| Method 1: spec only | Yes | No | No | No |
| Method 2: spec + RTL | Yes | Yes | No | No |
| Method 3: spec + RTL + raw trace | Yes | Yes | Yes | No |
| Method 4: spec + RTL + trace summary | Yes | Yes | No | Yes |

