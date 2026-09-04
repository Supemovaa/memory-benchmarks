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

## Useful commands

```
docker compose down && COLLECTION_NAME=XXX docker compose up -d: 停止当前服务（mem0和qdrant）并起一个新的，能做到记忆隔离

docker compose exec mem0 env | grep COLLECTION_NAME: 检查当前qdrant collection的名字

curl -s http://localhost:6333/collections/<collection_name>: 检查记忆数目

docker compose ps: 检查容器是否已经运行（healthy）

curl -fsS -X DELETE "http://localhost:6333/collections/<collection_name>"
curl -fsS -X DELETE "http://localhost:6333/collections/<collection_name>_entities": 清除记忆

docker logs -f memory-benchmarks-mem0-1 > temp.log 2>&1: 查看mem0 container内日志

docker compose up -d --build --no-deps --force-recreate mem0: 仅重启mem0容器，主要用于patch修复
```