# Complex FIFO RTL execution

Reuses vendored `axis_fifo.v`. Every output is aligned to an accepted input (`valid && ready`), with explicit reset cancellation. Depth 3 rounds to RAM depth 4; pipeline storage is additional.

96 RTL runs; 72/72 same-input artificial-mutant contrast witnesses; 0 illegal/unknown stimulus runs.

Independent tests use seeds first generated after the engineering candidate freeze. No LLM-generated or refined final assertion is claimed. Native SVA probe fails with the installed Icarus version. All Python candidate checks are auxiliary diagnostics.

Evidence and waveforms: `runs/<split>/d<depth>_p<pipeline>_s<seed>/<mutation>/`. Queue oracle obligations, request/response cycles, data ordering, cancellation and latency are in `evidence.json`; actual port traces in `trace.json`; commands/logs and VCD retained.

Raw differences are never counted alone: a witness requires fixed oracle pass, mutant obligation violation and identical legal stimuli. Deduplication counts mutation/obligation pairs, not waveform variants. The original FIFO presented bug remains unknown.

Run: `python3 scripts/research_fifo_experiment.py`
