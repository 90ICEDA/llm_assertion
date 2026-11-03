# Ibex #54 new encoding boundaries

New low16 encodings are frozen before original-RTL replay, separately from five old development anchors. The original module has no parameters. This validates handwritten engineering properties with native SVA and a separate encoding oracle; it is not independent validation of learned assertions.

[
  {
    "revision": "before",
    "cohort": "new_boundary",
    "vectors": 119,
    "violating_vectors": 32,
    "failures": 32,
    "by_family": {
      "legal_li": {
        "vectors": 20,
        "violating_vectors": 0
      },
      "legal_lui": {
        "vectors": 16,
        "violating_vectors": 0
      },
      "legal_slli": {
        "vectors": 16,
        "violating_vectors": 0
      },
      "legal_srai": {
        "vectors": 9,
        "violating_vectors": 0
      },
      "legal_srli": {
        "vectors": 9,
        "violating_vectors": 0
      },
      "lui_zero_reserved": {
        "vectors": 4,
        "violating_vectors": 0
      },
      "new_c_slli_x0_hint": {
        "vectors": 32,
        "violating_vectors": 32
      },
      "rv32_high_shift_reserved": {
        "vectors": 9,
        "violating_vectors": 0
      },
      "uncompressed_passthrough": {
        "vectors": 4,
        "violating_vectors": 0
      }
    },
    "compile_status": "passed",
    "execution_status": "completed"
  },
  {
    "revision": "before",
    "cohort": "old_anchor",
    "vectors": 5,
    "violating_vectors": 5,
    "failures": 5,
    "by_family": {
      "original_repair_anchor": {
        "vectors": 5,
        "violating_vectors": 5
      }
    },
    "compile_status": "passed",
    "execution_status": "completed"
  },
  {
    "revision": "after",
    "cohort": "new_boundary",
    "vectors": 119,
    "violating_vectors": 0,
    "failures": 0,
    "by_family": {
      "legal_li": {
        "vectors": 20,
        "violating_vectors": 0
      },
      "legal_lui": {
        "vectors": 16,
        "violating_vectors": 0
      },
      "legal_slli": {
        "vectors": 16,
        "violating_vectors": 0
      },
      "legal_srai": {
        "vectors": 9,
        "violating_vectors": 0
      },
      "legal_srli": {
        "vectors": 9,
        "violating_vectors": 0
      },
      "lui_zero_reserved": {
        "vectors": 4,
        "violating_vectors": 0
      },
      "new_c_slli_x0_hint": {
        "vectors": 32,
        "violating_vectors": 0
      },
      "rv32_high_shift_reserved": {
        "vectors": 9,
        "violating_vectors": 0
      },
      "uncompressed_passthrough": {
        "vectors": 4,
        "violating_vectors": 0
      }
    },
    "compile_status": "passed",
    "execution_status": "completed"
  },
  {
    "revision": "after",
    "cohort": "old_anchor",
    "vectors": 5,
    "violating_vectors": 0,
    "failures": 0,
    "by_family": {
      "original_repair_anchor": {
        "vectors": 5,
        "violating_vectors": 0
      }
    },
    "compile_status": "passed",
    "execution_status": "completed"
  }
]

Sources and exact original commits are in protocol.json; commands, native logs, waves and independent per-vector judgments are under execution/. Run `python3 scripts/research15_history_ibex54.py prepare`, `run`, `report` in WSL. Existing output is exclusive.
