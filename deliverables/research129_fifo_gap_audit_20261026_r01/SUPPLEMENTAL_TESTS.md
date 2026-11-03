# 固定research69版本的补测清单（本轮不执行）

冻结哈希：`ef3974b9ac0dd7a79f008564d7af4a43b77e9befdc1da93bfb4ba79543bca3da`。所有项目为开发补测，不能直接称新独立验收。
对应当前9个未曝光单元：Depth2/Pipeline0、Depth4/Pipeline1各4义务，以及Depth4/Pipeline2排空。另检查背压持续/解除、短/长时段及复位合法取消。

|参数|项目|义务|构造与曝光要求|
|---|---|---|---|
|2/0|d2p0_corrupt|order_payload|至少一个输入实际握手接受后输出；错误数据为该复位区间首违例|
|2/0|d2p0_duplicate_payload|order_payload|四个唯一数据已实际接受；第4个错误重复第3个，确认队列对应|
|2/0|d2p0_reset_residue|no_unsolicited_output, reset_cancellation|接受并暂存唯一数据，背压时复位取消；复位释放后不再输入，旧数据被接受时同时曝光两项|
|2/0|d2p0_stall_glitch|stall_stability|前周期valid=1且ready=0；当前数据改变，分别保留合法跨周期对照|
|2/0|d2p0_valid_withdraw_stalled|stall_stability|短背压持续阶段撤销valid，数据保持；请求呈现不代替接受|
|2/0|d2p0_valid_withdraw_release|stall_stability|短背压后ready恢复边界撤销valid；检查前周期触发与本周期要求|
|2/0|d2p0_long_valid_withdraw_stalled|stall_stability|至少8个已呈现输出的连续背压周期后撤销valid|
|2/0|d2p0_long_valid_withdraw_release|stall_stability|至少8个背压周期后的ready恢复边界撤销valid|
|2/0|d2p0_legal_reset_cancel|reset_cancellation, stall_stability, no_unsolicited_output|输出背压中复位，取消旧事务后不输出；跨复位的保持要求被取消，新epoch握手另行对应|
|4/1|d4p1_corrupt|order_payload|至少一个输入实际握手接受后输出；错误数据为该复位区间首违例|
|4/1|d4p1_duplicate_payload|order_payload|四个唯一数据已实际接受；第4个错误重复第3个，确认队列对应|
|4/1|d4p1_reset_residue|no_unsolicited_output, reset_cancellation|接受并暂存唯一数据，背压时复位取消；复位释放后不再输入，旧数据被接受时同时曝光两项|
|4/1|d4p1_stall_glitch|stall_stability|前周期valid=1且ready=0；当前数据改变，分别保留合法跨周期对照|
|4/1|d4p1_valid_withdraw_stalled|stall_stability|短背压持续阶段撤销valid，数据保持；请求呈现不代替接受|
|4/1|d4p1_valid_withdraw_release|stall_stability|短背压后ready恢复边界撤销valid；检查前周期触发与本周期要求|
|4/1|d4p1_long_valid_withdraw_stalled|stall_stability|至少8个已呈现输出的连续背压周期后撤销valid|
|4/1|d4p1_long_valid_withdraw_release|stall_stability|至少8个背压周期后的ready恢复边界撤销valid|
|4/1|d4p1_legal_reset_cancel|reset_cancellation, stall_stability, no_unsolicited_output|输出背压中复位，取消旧事务后不输出；跨复位的保持要求被取消，新epoch握手另行对应|
|4/2|d4p2_isolated_tail|drain_no_loss|复用research29家族逻辑但显式支持Depth4/Pipeline2；目标为最后第4个已接受输出被隐藏，不能提前出现顺序错误；最终至少18个真实ready=1且input-valid=0周期；合法对照应排空或复位取消。|
|4/2|d4p2_continuous_tail|drain_no_loss|复用research29家族逻辑但显式支持Depth4/Pipeline2；目标为最后第4个已接受输出被隐藏，不能提前出现顺序错误；最终至少18个真实ready=1且input-valid=0周期；合法对照应排空或复位取消。|
|4/2|d4p2_parked_tail|drain_no_loss|复用research29家族逻辑但显式支持Depth4/Pipeline2；目标为最后第4个已接受输出被隐藏，不能提前出现顺序错误；最终至少18个真实ready=1且input-valid=0周期；合法对照应排空或复位取消。|
|4/2|d4p2_reset_then_tail|drain_no_loss|复用research29家族逻辑但显式支持Depth4/Pipeline2；目标为最后第4个已接受输出被隐藏，不能提前出现顺序错误；最终至少18个真实ready=1且input-valid=0周期；合法对照应排空或复位取消。|
|4/2|d4p2_legal_three|drain_no_loss|复用research29家族逻辑但显式支持Depth4/Pipeline2；目标为最后第4个已接受输出被隐藏，不能提前出现顺序错误；最终至少18个真实ready=1且input-valid=0周期；合法对照应排空或复位取消。|
|4/2|d4p2_reset_cancels_tail|drain_no_loss|复用research29家族逻辑但显式支持Depth4/Pipeline2；目标为最后第4个已接受输出被隐藏，不能提前出现顺序错误；最终至少18个真实ready=1且input-valid=0周期；合法对照应排空或复位取消。|

预定种子12907、12919；24种设计，共48个场景定义。若每项均保留正确/故障侧，至多96次回放，3个参数构建，编译冒烟另计。没有运行这些场景，不承诺必然曝光或通过。
现有research29生成器的默认参数含4/1、不含4/2；后续应新增显式参数入口，保持历史默认不变。本轮仅列出该实现前置条件。
每项目记录实际接受/响应/取消周期、正确/故障侧参考队列、原生前件起始和后件检查周期、首违例与归因状态。只呈现请求不计为事务，波形不同不直接计为Bug。
后续unknown的处理：分别构造单故障、首违例或复位隔离场景重新验证，不能删除旧unknown或放宽归因规则；额外重复/丢失事件需要单独归因，不能直接宣称原级联已解决。
失败时保留冻结版本并停止对应单元；本清单不授权模型修改。若将失败用于细化，完成历史回放后重新冻结，再用完全新批次独立验收。
不覆盖全参数空间或内部RAM满状态：当前参数为2/0、4/1、4/2（另有归档8/2）；外部背压不等于已证明内部full，FIFO流水响应不是无条件固定延迟。
