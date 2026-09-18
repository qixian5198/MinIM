# MinIM

一个最小可用的即时通讯内核 · Python + FastAPI 从零实现

> 项目位置：`/Volumes/SSK SSD/MinIM`（exFAT，运行时产物不落此盘）
> 当前阶段：S0 完成（文档就绪），待进 S1 编码

---

## 它是什么

单聊 + 群聊 + 实时推送的 IM 内核。用于系统练习 Python 后端工程化与分布式基础能力。

**不是**电商系统，不做商品/订单/支付。名字叫 MinIM 就是因为它只是个 Mini IM。

参考项目 [MallChat](https://github.com/zongzibinbin/MallChat)（Java，4.6k star）——
它的 IM 部分有真东西，但宣称的电商能力交付为 0、测试近乎为零、依赖太多跑不起来。
MinIM 继承它的 6 个好设计，并针对性补上这三块短板。

## 快速开始

```bash
cd "/Volumes/SSK SSD/MinIM"

# 1. 起依赖服务（PostgreSQL / Redis / MinIO）
docker compose up -d

# 2. Python 环境（venv 放本地盘，避开 exFAT）
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/minim"
uv venv --python 3.12 && source "$HOME/.venvs/minim/bin/activate"
uv pip install -r requirements.txt

# 3. 配置
cp .env.example .env && vim .env

# 4. 迁移 + 启动
alembic upgrade head
uvicorn app.main:app --reload
```

详细见 [`docs/09-环境搭建.md`](docs/09-环境搭建.md)。

## 文档

| # | 文档 | 用途 |
|:--:|:---|:---|
| 00 | [项目总览](docs/00-项目总览.md) | 全局导航 |
| 01 | [产品需求与范围](docs/01-产品需求与范围.md) | 做什么、不做什么 |
| 02 | [系统架构](docs/02-系统架构.md) | 分层、模块、关键决策 |
| 03 | [业务流程](docs/03-业务流程.md) | 核心链路时序图 |
| 04 | [技术栈](docs/04-技术栈.md) | 选型与版本 |
| 05 | [数据模型与 ER 图](docs/05-数据模型与ER图.md) | 表结构、索引、迁移 |
| 06 | [API 接口规范](docs/06-API接口规范.md) | REST + WebSocket 契约 |
| 07 | [测试策略](docs/07-测试策略-全栈.md) | 单元/集成/E2E |
| 08 | [安全测试](docs/08-安全测试.md) | 越权/注入/频控 |
| 09 | [环境搭建](docs/09-环境搭建.md) | 从零到跑起来 |
| 10 | [项目初始化](docs/10-项目初始化.md) | 目录结构与骨架 |
| 11 | [编码实现指南](docs/11-编码实现指南.md) | 分层规范与各 M 实现要点 |
| 12 | [性能优化](docs/12-性能优化.md) | 瓶颈与压测 |
| 13 | [部署上线](docs/13-部署上线.md) | 构建、发布、回滚 |
| 14 | [运维手册](docs/14-运维手册.md) | 监控、日志、备份、故障 |

## 技术栈

Python 3.12 · FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis 7 · MinIO · pytest

刻意不引入 Kafka / Elasticsearch / Celery / K8s —— 每多一个中间件，启动门槛高一分。

## 成功标准

- [ ] 两个窗口实时互发消息，延迟 < 500ms
- [ ] 群聊广播正常
- [ ] 历史消息游标分页不重不漏
- [ ] 断线重连不丢消息
- [ ] **测试覆盖率 ≥ 60%，核心链路 ≥ 80%**
- [ ] **`docker compose up` 一条命令启动**

## 里程碑

M0 环境 · M1 认证 · M2 单聊 · M3 推送 · M4 群聊好友 · M5 可靠性 · M6 异步文件 · M7 安全 · M8 AI（选做）

约 16.5 人天。详见 [`docs/00-项目总览.md`](docs/00-项目总览.md)。

## 项目盘是 exFAT 的三条铁律

1. **源码在 SSD，运行时产物在本地盘**（venv → `~/.venvs/minim`）
2. **数据库数据只走 Docker named volume**，绝不落在 exFAT
3. **不用 Docker 跑应用本身**，只用它跑依赖服务

原因与细节见 [`docs/09-环境搭建.md`](docs/09-环境搭建.md) 第 0 节。
