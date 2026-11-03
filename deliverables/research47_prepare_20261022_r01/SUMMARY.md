# research47：采样字段绑定门控

本地正负检查 280/280 通过。复用11个原生开发窗口，新增 anchor_reset/check_reset/anchor_pending 明确字段；各字段逐项核验，失败或伪造的接受结果不能创建SVA请求。

research46两个真实失败结果只读复核一致，全部历史产物哈希保持不变。本阶段真实模型调用尚未执行，不能宣称周期判断已通过；新增仿真/形式化为0。

请求：plan_request.preview.json；本地证书：expected.private.json（不发送）；检查：qualification.json；规则：protocol.json。

真实调用需先明确转用或新增最多2次周期判断额度；旧剩余额度用途不同。通过即停止，仅生成受门控的后续请求产物，不调用SVA模型。
