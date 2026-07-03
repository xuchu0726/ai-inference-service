# 双TP=2主备与Redis Stream异步任务验收摘要

## 1. 架构
- primary：GPU 0,1；Seed-OSS-36B W8A8 TP=2；API :8002
- fallback：GPU 2,3；Seed-OSS-36B W8A8 TP=2；API :8010
- Gateway：:8000；Redis：:16379；Worker metrics：:9101

## 2. 主备故障切换
- 基线请求走 primary，返回 42。
- 受控停止 primary 后，Gateway 对 primary 尝试 2 次。
- 请求成功切到 fallback；fallback thinking_budget=512。
- primary 恢复后，双 upstream health 均为 ready。

## 3. Redis Stream异步任务
- job_id=0f088922d681432dbbb6de64d5dff700
- 状态路径：queued -> running -> succeeded。
- Worker：week4-cloud-worker-1。
- 推理路由：primary；返回 42；primary_attempts=1。
- Stream key 使用 hash tag：{ai-inference:week4:jobs}:stream。
- 成功后执行 XACK + XDEL；因此无待处理消息时 stream key 会消失。

## 4. 结果边界
- 本证据证明真实异步入队、消费、状态更新、Seed TP=2执行与成功ACK清理。
- 本次只验证成功路径；worker异常退出后的 pending reclaim 需要单独受控实验。
