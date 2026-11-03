# Overall Method Flowchart

```mermaid
flowchart TD
    A["10 RTL bug cases"] --> B["Prepare inputs"]
    B --> B1["Spec + correct RTL + buggy RTL + testbench"]
    B --> B2["Good/bad waveforms"]

    B2 --> C["Trace processing"]
    C --> C1["Convert waveform to text trace"]
    C --> C2["Summarize good/bad divergence"]

    B1 --> D["Build prompt variants"]
    C1 --> D
    C2 --> D

    D --> D1["Method 1: spec only"]
    D --> D2["Method 2: spec + RTL"]
    D --> D3["Method 3: spec + RTL + raw trace"]
    D --> D4["Method 4: spec + RTL + trace summary"]

    D1 --> E["Generate SVA candidates"]
    D2 --> E
    D3 --> E
    D4 --> E

    E --> F["SVA static filtering"]
    F --> G["Simulation-based evaluation"]

    G --> G1["Compile check"]
    G --> G2["Pass on correct RTL"]
    G --> G3["Fail on buggy RTL"]
    G --> G4["Non-vacuous / antecedent triggered"]

    G1 --> H["Strict evaluation report"]
    G2 --> H
    G3 --> H
    G4 --> H

    H --> I["Four-method comparison"]
    H --> J["Best assertion per case"]
    H --> K["Final deliverables"]
```

## Notes

- Each case is evaluated under the same testbench on both correct and buggy RTL.
- The four methods differ only in how much context is included in the prompt.
- Static filtering removes malformed or low-quality SVA candidates before simulation.
- Final evaluation checks syntax, correctness on the good design, bug detection on the bad design, and vacuity.
