# Probe 顺序敏感性离线重放

固定 30 parents、240 candidates、每 parent 64 probes、840 个同-parent无序候选对；3 种顺序各 5 seeds，budget=8/16/32。disagreement score 定义为单个 probe 将 8 candidates 的 28 对按 (FP,TP) verdict 分开的数量，distinct signature 数为次级分数；同分用 seed 打散。

完整长路径读取到 15,360/15,360 verdict cells，缓存一致性错误 0，timeout stage 48，所以未补跑 formal。完整 64-probe pool 后所有策略/seed 最终 resolved set 一致：True，共 546 对。

Jaccard 仅比较 resolved pair 集合；到达顺序由 `first_distinguish_rank.csv` 和 `kendall_probe_order.csv` 单独报告。
