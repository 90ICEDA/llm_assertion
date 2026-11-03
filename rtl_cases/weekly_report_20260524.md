# AssertionForge实验进度周报 5.24

这周主要围绕 AssertionForge 的小规模 RTL 数据集构建、波形导出、prompt 设计和自动化评测链路做了一整套打通。和上周相比，这周最大的进展不是单点脚本，而是把“case 构造 - 仿真 - trace 文本化 - prompt 生成 - LLM 产出 SVA - 自动评测”这一条链真正串起来了。

首先我们整理了 10 个小型 RTL case，覆盖的 bug 类型包括 reset 漏掉、grant 延迟、valid/ready 逻辑错误、FSM 跳转错误、counter 边界错误、priority encoder 优先级错误、FIFO full 边界错误、pulse width 错误、地址步进错误和 hold valid until ready 错误。每个 case 下面都统一整理了 correct RTL、buggy RTL、testbench、good waveform、bad waveform，方便后续统一做 prompt 实验和断言评测。

一开始 good/bad waveform 只是手写的 cycle 级 CSV，为了让数据更真实，我们后来补上了 WSL Ubuntu 下的 iverilog/vvp 仿真环境，把 10 个 case 全部重新跑了一遍，并自动导出了 VCD。之后又把原来的 waveform_good.csv / waveform_bad.csv 替换成了从真实仿真结果转换出来的版本，这样后面不管是看波形、导出 trace，还是做断言筛选，基础数据都更可靠。

在波形处理这部分，我们另外写了脚本，把 VCD 或 CSV 仿真结果转成按 cycle 展开的文本波形，像 req、grant、state、valid、ready、count、addr 这些关键信号都可以直接按每个周期列出来。这样一来，LLM 不只是看到一句 spec，或者一段 RTL，而是能直接看到 good trace 和 bad trace 在哪些时刻开始分叉。

围绕这个思路，我们设计了三种 prompt。第一种只给 spec；第二种给 spec + RTL；第三种给 spec + RTL + good/bad trace。目标是比较这三种输入条件下，LLM 生成的 SVA 质量到底有没有显著差异。

为了把这个流程跑顺，我们又补了一套自动化脚本。具体来说，prepare_prompt_assets.py 负责整理 spec、trace 和三种 prompt；generate_sva_from_prompts.py 负责调用本地 Ollama 模型生成 SVA；evaluate_generated_sva.py 负责检查生成的断言能不能编译、在 correct RTL 上能不能 pass、在 buggy RTL 上能不能 fail、是不是 non-vacuous。这样我们就不再是凭感觉看某条断言“像不像对”，而是可以批量、统一地做评估。

在生成策略上，这周还做了几轮比较关键的迭代。最开始模型经常输出格式不规范、引用不存在信号、或者把多条 assertion 拼在一起，所以后来我们把生成流程改成了两阶段：先让模型输出 JSON 结构，再在本地拼成标准 SVA；如果 JSON 阶段失败，再回退到直接生成 assertion 的老路径。同时又加了信号白名单、禁用 next_state / count_next / S_* 之类不可见或不稳定符号、限制只能输出单条 assert property、并拒收嵌套 implication。

后面我们又进一步加了 trace gate 和多候选筛选。也就是说，不再每种 prompt 只生成一条断言，而是生成多条候选，再根据 good trace / bad trace 上 antecedent 是否命中、good 上会不会违背、bad 上会不会违背来做一个轻量预筛。这个方向本身是有效的，至少把很多纯格式错误和明显无效的断言压下去了，不过也暴露出来一个问题：现在真正的瓶颈已经不是“能不能生成”，而是“生成出来的断言是不是足够强、能不能真正区分 correct 和 buggy”。

从目前 10 个 case 的结果看，spec only 基本是最弱的，很多断言虽然能编译，但要么 vacuous，要么只是说了一句总是成立的废话。spec + RTL 会有一些提升，已经能在个别 case 上打到 buggy，但常常 correct 也会一起挂，说明 false positive 还比较多。spec + RTL + good/bad trace 整体上是三种方法里最好的，目前唯一一个可以明确说“既能在 correct 上通过，又能在 buggy 上失败，而且 non-vacuous”的 case 是 case03，也就是 valid/ready OR bug。除此之外，case01、case06、case07 在 spec + RTL 或 spec + RTL + trace 下也能生成一部分能抓到 bug 的断言，但目前还带有误报，只能算部分有效。

所以这周阶段性的结论是：加入 good/bad trace 这个方向是对的，确实比只给 spec，或者只给 spec + RTL 更容易生成有区分能力的断言，但在我们当前这 10 个小 case 上，这个提升还不能说已经非常稳定，更多是“有正向趋势，但还需要继续打磨生成约束和筛选策略”。尤其像 FSM 跳转、pulse width、hold valid until ready 这类带更强时序特征的 case，在我们当前只允许单条布尔 antecedent / consequent 的受限 SVA 形式下，表达能力本身就有点不够，这也是为什么 case04、case08、case10 目前效果不理想。

另外，这周也顺手把整套实验结果整理成了表格，能够按 case 对比三种方法生成的 SVA、语法是否通过、correct 是否 pass、buggy 是否 fail、是否 vacuous，以及人工判断这条断言是不是有用。这样后面如果要扩充数据集，或者做更正式的对比实验，这套统计表可以直接沿用。

总体来看，这周最大的收获其实不是“已经把断言生成做得很好了”，而是把问题空间看清楚了。现在我们知道：一，trace 信息是有价值的；二，格式约束和信号白名单很重要；三，真正难的部分不是编译过，而是避免 vacuous 和 false positive；四，如果后面要在更复杂的 bug 上继续提升，单纯靠现在这种非常受限的 SVA 表达形式，可能已经不够了。

下一步预计主要做三件事：第一，继续加强弱断言过滤和 good/bad trace 分离筛选，尽量减少 vacuous 和 tautology；第二，针对 FSM、pulse、hold 这几类 case 放宽到 temporal-lite 模式，尝试支持更轻量的时序表达；第三，继续扩大 case 数量，把这 10 个小 case 先扩展成更稳定的一批小基准，再考虑是否值得往 LoRA 微调或者 formal rerank 方向继续推进。
