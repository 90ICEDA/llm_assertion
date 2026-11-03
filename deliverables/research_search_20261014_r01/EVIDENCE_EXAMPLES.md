# Actual search witnesses

These are development search results. Candidates were frozen; no model revision, native SVA execution, historical nonregression, or independent final test is claimed here.

## spill: slot_07, collision_empty

Actual query `spill/3113/contract/00`, cycle 5. The candidate accepts the reset-to-first-violation prefix; the independent monitor identifies a buggy violation and a fixed-safe obligation witness.

```systemverilog
assert property (@(posedge clk_i) disable iff (!rst_ni) (flush_i) |=> ((data_o == flush_i)));
```

| Cycle | Buggy sample | Fixed sample |
|---|---|---|
| 1 | `{"data_i": 0, "data_o": 0, "flush_i": 0, "push_i": 0, "rst_ni": 0, "valid_o": 0}` | `{"data_i": 0, "data_o": 0, "flush_i": 0, "push_i": 0, "rst_ni": 0, "valid_o": 0}` |
| 2 | `{"data_i": 0, "data_o": 0, "flush_i": 0, "push_i": 0, "rst_ni": 1, "valid_o": 0}` | `{"data_i": 0, "data_o": 0, "flush_i": 0, "push_i": 0, "rst_ni": 1, "valid_o": 0}` |
| 3 | `{"data_i": 0, "data_o": 0, "flush_i": 0, "push_i": 1, "rst_ni": 1, "valid_o": 0}` | `{"data_i": 0, "data_o": 0, "flush_i": 0, "push_i": 1, "rst_ni": 1, "valid_o": 0}` |
| 4 | `{"data_i": 0, "data_o": 0, "flush_i": 1, "push_i": 1, "rst_ni": 1, "valid_o": 1}` | `{"data_i": 0, "data_o": 0, "flush_i": 1, "push_i": 1, "rst_ni": 1, "valid_o": 1}` |
| 5 | `{"data_i": 0, "data_o": 0, "flush_i": 0, "push_i": 0, "rst_ni": 1, "valid_o": 1}` | `{"data_i": 0, "data_o": 0, "flush_i": 0, "push_i": 0, "rst_ni": 1, "valid_o": 0}` |

Raw run: `deliverables/research_search_20261014_r01/runs/search/spill/3113/contract/00/spill/buggy`. Full assertion checks and independent reference events are in `evidence_examples.json`.

## stat: slot_05, valid_latency

Actual query `stat/3113/contract/00`, cycle 4. The candidate accepts the reset-to-first-violation prefix; the independent monitor identifies a buggy violation and a fixed-safe obligation witness.

```systemverilog
assert property (@(posedge clk_i) disable iff (!rst_ni) (frame_done_i) |=> (stat_valid_o));
```

| Cycle | Buggy sample | Fixed sample |
|---|---|---|
| 1 | `{"frame_done_i": 0, "frame_len_i": 0, "rst_ni": 0, "stat_len_o": 0, "stat_valid_o": 0}` | `{"frame_done_i": 0, "frame_len_i": 0, "rst_ni": 0, "stat_len_o": 0, "stat_valid_o": 0}` |
| 2 | `{"frame_done_i": 0, "frame_len_i": 0, "rst_ni": 1, "stat_len_o": 0, "stat_valid_o": 0}` | `{"frame_done_i": 0, "frame_len_i": 0, "rst_ni": 1, "stat_len_o": 0, "stat_valid_o": 0}` |
| 3 | `{"frame_done_i": 1, "frame_len_i": 0, "rst_ni": 1, "stat_len_o": 0, "stat_valid_o": 0}` | `{"frame_done_i": 1, "frame_len_i": 0, "rst_ni": 1, "stat_len_o": 0, "stat_valid_o": 0}` |
| 4 | `{"frame_done_i": 0, "frame_len_i": 0, "rst_ni": 1, "stat_len_o": 0, "stat_valid_o": 1}` | `{"frame_done_i": 0, "frame_len_i": 0, "rst_ni": 1, "stat_len_o": 0, "stat_valid_o": 0}` |

Raw run: `deliverables/research_search_20261014_r01/runs/search/stat/3113/contract/00/stat/buggy`. Full assertion checks and independent reference events are in `evidence_examples.json`.

