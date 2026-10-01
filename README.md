# MinIM

一个最小可用的即时通讯内核 · Python + FastAPI 从零实现

单聊 + 群聊 + 实时推送（WebSocket）+ 好友体系 + 文件上传 + 审计/频控/敏感词。
用于系统练习 Python 后端工程化与分布式基础能力。

**不是**电商系统，不做商品/订单/支付。名字叫 MinIM 就是因为它只是个 Mini IM。

参考项目 [MallChat](https://github.com/zongzibinbin/MallChat)（Java，4.6k star）——
它的 IM 部分有真东西，但宣称的电商能力交付为 0、测试近乎为零、依赖太多跑不起来。
MinIM 继承它的 6 个好设计，并针对性补上这三块短板。

## 当前进度

**M0–M7 全部完成**：用户认证 / 单聊消息 / WebSocket 实时推送 / 群聊与好友 /
消息可靠性（撤回·点赞·已读）/ Outbox 轮询投递与文件上传 / 安全合规
（审计日志 + 频控 + 敏感词 DFA 可切 Aho-Corasick）。
外加一个**最小 Web 前端**（`web/`，单文件），可跑通验收用例的交互路径。
全量测试 86 通过，核心链路覆盖率 ≥ 90%。

## 快速开始

```bash
# 1. 起依赖服务（PostgreSQL / Redis）
docker compose up -d

# 2. Python 环境
python -m venv .venv && source .venv/bin/activate   # 或用 uv
pip install -r requirements.txt

# 3. 配置
cp .env.example .env   # 按需改数据库连接；MinIO 不配 key 则自动降级为内存 fake

# 4. 迁移 + 启动
alembic upgrade head
uvicorn app.main:app --port 8000
```

浏览器打开 `http://localhost:8000`（最小前端由后端直接托管），或走 Swagger：
`http://localhost:8000/docs`。

> **MinIO 说明**：对象存储做了抽象（`app/core/storage.py`），
> 不配 `MINIO_ACCESS_KEY` 时用内存 fake（数据不持久化，开发够用）；
> 配了则走 MinIO，惰性连接，连不上报错不静默。

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

Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Alembic · PostgreSQL 16 · Redis 7 · MinIO（可选）· pytest

刻意不引入 Kafka / Elasticsearch / Celery / K8s —— 每多一个中间件，启动门槛高一分。

## 成功标准（验收）

- [x] 两个窗口实时互发消息（前端 + WebSocket，`web/` 可体验）
- [x] 群聊广播正常（集成测试覆盖）
- [x] 历史消息游标分页不重不漏（上滑翻页在前端）
- [x] 断线重连不丢消息（WS 指数退避重连 + `last_seq` 补发）
- [x] 测试覆盖率 ≥ 60%，核心链路 ≥ 80%（实际 90%+）
- [ ] `docker compose up` 一条命令在全新目录起全部依赖（含 MinIO，待镜像源解决）

## 里程碑

M0 环境 ✅ · M1 认证 ✅ · M2 单聊 ✅ · M3 推送 ✅ · M4 群聊好友 ✅ ·
M5 可靠性 ✅ · M6 异步文件 ✅ · M7 安全 ✅ · M8 AI（选做，未开始）

## 环境铁律（本机 SSD 是 exFAT 的项目才需要）

1. **源码在 SSD，运行时产物在本地盘**（venv 放本地盘）
2. **数据库数据只走 Docker named volume**，绝不落在 exFAT
3. **不用 Docker 跑应用本身**，只用它跑依赖服务
