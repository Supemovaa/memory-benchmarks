# USAGE

## What's this

本repo基于 `mem0` 官方的 benchmark evaluator ，做了若干修改。

- 支持 `mem0` v3 版。 `mem0` v3 部分函数的参数与原 evaluator 不同
- 增加中转站支持，增大 memory extractor、 llm client 的 `max_token` 并作为 configurable 项目
- 打通 timestamp 传导。原版 `mem0` 和 evaluator 都没有针对测bench的 timestamp 优化，导致直接使用系统时间。现在将对话时间作为时间戳加入 `user_prompt` 和记忆条目
- 增加对 Qwen3+ 系列模型 api 的适配，即 `enable_thinking` 参数的配置

## How to run

使用 README 的 Option B: Mem0 OSS (Self-Hosted) 搭建容器。

使用
```
python -m benchmarks.locomo.run \
--project-name <project-name> \
--dataset-path datasets/locomo/locomo10.json \
--predict-only \
--answerer-model <answerer> \
--judge-model <judge> \
--top-k-cutoffs 10,20,50,60,100,200
```
搭建记忆库并为每条问题检索记忆。

使用
```
python -m benchmarks.locomo.run \
--project-name <project-name> \
--dataset-path datasets/locomo/locomo10.json \
--evaluate-only \
--answerer-model <answerer> \
--judge-model <judge> \
--top-k-cutoffs 10,20,50,60,100,200
```
做回答和评价。

如果去掉 `predict-only` 和 `evaluate-only` 则先后做两件事。如果加入 `rejudge` 则重新生成并评价。

建议先跑一个conversation（一共10个），ingest memory 共耗时约1h，extractor用Qwen2.5-7B-Instruct，answerer和judge使用gpt-oss-120b。