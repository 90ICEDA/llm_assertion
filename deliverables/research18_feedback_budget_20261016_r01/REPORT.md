# Archived feedback and context qualification

Qualification passed: False.
No model generation, new RTL execution or independent-test read. Actual archived native evidence was reused unchanged.

| Request | Rendered input tokens | Conservative input | Output reserve | Fits |
|---|---:|---:|---:|---|
| original | 25025 | 25473 | 1024 | False |
| compact_original | 16307 | 16755 | 1024 | False |
| compact_rebuilt | 15841 | 16289 | 1024 | False |

All four fair-drain control/mutant observations retain cycle 111 in rebuilt and compact feedback. The one-window diagnostic limit also prioritizes that checkpoint over earlier candidate failures; actual failure cycles are preserved in window_qualification.json.

Removed opaque hash lists and cycle arrays are represented by counts; complete native evidence remains in its original artifact directory. Template counting uses the actual runner tokenizer with a documented conservative wrapper allowance; it is not claimed to exactly reproduce every Ollama Go-template path.

Diagnostic selection and prompt-budget qualification only. No new SVA success, native replay or semantic repair claim.
