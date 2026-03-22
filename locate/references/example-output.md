# Example Output — Locate Skill

Below is a complete example of the expected output when a user asks:

> "用户点击'提交订单'按钮后，为什么有时候会出现重复扣款？"

---

## Call Chain Flowchart

```mermaid
graph TD
    classDef entry fill:#d4edda,stroke:#28a745,color:#000
    classDef terminal fill:#f8d7da,stroke:#dc3545,color:#000
    classDef external fill:#cce5ff,stroke:#007bff,color:#000
    classDef decision fill:#fff3cd,stroke:#ffc107,color:#000

    A["用户点击'提交订单'<br/><code>src/pages/Checkout.tsx:87</code>"]:::entry
    B["handleSubmitOrder()<br/><code>src/pages/Checkout.tsx:142</code>"]
    C["orderApi.createOrder()<br/><code>src/api/order.ts:56</code>"]
    D["POST /api/v1/orders<br/><code>server/routes/order.route.ts:23</code>"]
    E["OrderController.create()<br/><code>server/controllers/order.controller.ts:45</code>"]
    F{"检查幂等键?<br/><code>server/controllers/order.controller.ts:52</code>"}:::decision
    G["OrderService.createOrder()<br/><code>server/services/order.service.ts:78</code>"]
    H[("DB: INSERT orders<br/><code>server/services/order.service.ts:95</code>")]:::external
    I[("PaymentGateway.charge()<br/><code>server/services/payment.service.ts:34</code>")]:::external
    J["返回 201 Created<br/><code>server/controllers/order.controller.ts:68</code>"]:::terminal
    K["返回 409 Conflict<br/><code>server/controllers/order.controller.ts:55</code>"]:::terminal

    A -->|"onClick"| B
    B -->|"async call"| C
    C -->|"HTTP POST"| D
    D -->|"routes to"| E
    E -->|"checks idempotency"| F
    F -->|"key exists"| K
    F -->|"key missing / not checked"| G
    G -->|"INSERT"| H
    H -->|"success"| I
    I -->|"charge result"| J
```

## 定位结论

| 维度 | 内容 |
|------|------|
| **所属模块** | 订单服务 / Order Service + 支付服务 / Payment Service |
| **入口位置** | `src/pages/Checkout.tsx:87` — 提交订单按钮的 onClick 事件 |
| **核心代码位置** | `server/controllers/order.controller.ts:52` — 幂等键检查逻辑 |
| **调用链路径** | Checkout.onClick → handleSubmitOrder → orderApi.createOrder → POST /api/v1/orders → OrderController.create → OrderService.createOrder → DB INSERT → PaymentGateway.charge |
| **当前逻辑** | 用户点击提交后，前端发起 POST 请求创建订单。Controller 层有一个幂等键（idempotency key）检查，但当前实现仅在 Redis 中缓存 key，TTL 仅 5 秒。如果用户在 5 秒后重复点击，或者 Redis 缓存失效，幂等检查将失效，导致同一笔订单被重复创建并重复扣款。 |
| **问题原因 / 缺失点** | 1. 前端缺少防重复点击（debounce/disable button）机制 — `Checkout.tsx:87` 的 onClick 未做任何防护。 2. 后端幂等键 TTL 过短（5秒）— `order.controller.ts:52` 的 Redis TTL 应与业务订单生命周期匹配。 3. 数据库层缺少唯一约束 — `order.service.ts:95` 的 INSERT 语句没有 `ON CONFLICT` 保护。 |
| **影响范围** | 支付模块（重复扣款）、库存模块（重复扣减）、用户钱包/余额、订单列表展示 |
| **建议修复方向** | 1. 前端：提交后立即 disable 按钮 + loading 状态。 2. 后端：将幂等键 TTL 延长至 24h，或改用数据库唯一索引做幂等。 3. DB：给 orders 表添加 `(user_id, idempotency_key)` 唯一约束。 |

---

## Notes on This Example

- Every Mermaid node has a `file:line` reference that was verified by reading the actual file
- The decision node (rhombus) shows a branch point in the logic
- External calls (DB, payment gateway) use stadium-shaped nodes
- The diagnosis table uses business language a product manager can understand
- Root cause analysis identifies multiple layers (frontend + backend + DB) rather than a single point of failure
