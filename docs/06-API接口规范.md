# 06 · API 接口规范

> 定位：前后端之间的唯一契约。**契约未锁定前，任何一端都不许动手**
> 状态：v1.0 · 待 FE/BE 联合评审

---

## 1. 通用约定

### 1.1 基础

| 项 | 约定 |
|:---|:---|
| 前缀 | `/api/v1` |
| 协议 | HTTPS（生产）/ HTTP（本地开发） |
| 编码 | UTF-8，`Content-Type: application/json` |
| 时间格式 | ISO 8601 UTC，如 `2026-09-18T12:30:00Z` |
| ID 类型 | 雪花 ID（int64），JSON 中序列化为 **string**（避免 JS 精度丢失） |

> ⚠️ **int64 必须序列化为 string**。JavaScript 的 Number 最大安全整数是 2^53-1，
> 大 ID 会精度丢失。这是前后端协作的经典坑。

### 1.2 认证

```
Authorization: Bearer <access_token>
```

- 除注册/登录外，所有接口都需要
- token 过期返回 `401 ERR_TOKEN_EXPIRED`，客户端用 refresh_token 换新
- WebSocket 通过 query 参数传：`/ws?token=xxx`

### 1.3 统一响应结构

**成功**
```jsonc
{
  "code": 0,
  "message": "ok",
  "data": { ... },        // 业务数据，可能为 null
  "request_id": "req_7f3a9c"   // 链路追踪用
}
```

**失败**
```jsonc
{
  "code": 10001,
  "message": "用户名已存在",
  "data": null,
  "request_id": "req_7f3a9c"
}
```

HTTP 状态码与业务 code 的对应：

| HTTP | 含义 | 使用场景 |
|:---:|:---|:---|
| 200 | 成功 | 查询、更新 |
| 201 | 已创建 | 注册、发消息、建群 |
| 400 | 请求错误 | 参数不合法（Pydantic 校验失败） |
| 401 | 未认证 | 无 token / token 无效 / 过期 |
| 403 | 无权限 | 非群成员、非好友 |
| 404 | 不存在 | 资源不存在 |
| 409 | 冲突 | 用户名已存在、已是好友 |
| 422 | 语义错误 | 业务逻辑不满足（如成员超上限） |
| 429 | 频率限制 | 频控触发 |
| 500 | 服务器错误 | 未捕获异常（**不应出现，出现即 bug**） |

### 1.4 游标分页约定

**请求参数**

| 参数 | 类型 | 默认 | 说明 |
|:---|:---|:---|:---|
| `cursor` | string | 空 | 上一页返回的 `next_cursor`，首页不传 |
| `limit` | int | 20 | 每页条数，最大 50 |

**响应结构**
```jsonc
{
  "code": 0,
  "data": {
    "list": [ ... ],
    "next_cursor": "880",     // null 表示没有更多
    "has_more": true
  }
}
```

**禁止**使用 `page` / `offset` 参数。

---

## 2. 错误码表

| code | 常量名 | HTTP | 含义 |
|---:|:---|:---:|:---|
| 0 | OK | 200 | 成功 |
| 10001 | USERNAME_TAKEN | 409 | 用户名已存在 |
| 10002 | PASSWORD_WRONG | 401 | 密码错误 |
| 10003 | USER_NOT_FOUND | 404 | 用户不存在 |
| 10004 | WEAK_PASSWORD | 400 | 密码强度不足 |
| 10005 | USER_DISABLED | 403 | 账号已禁用 |
| 20001 | TOKEN_INVALID | 401 | token 无效 |
| 20002 | TOKEN_EXPIRED | 401 | token 过期 |
| 20003 | REFRESH_TOKEN_INVALID | 401 | refresh token 无效 |
| 30001 | ROOM_NOT_FOUND | 404 | 会话不存在 |
| 30002 | NOT_ROOM_MEMBER | 403 | 非会话成员 |
| 30003 | MEMBER_LIMIT_EXCEEDED | 422 | 群成员超限 |
| 30004 | NOT_GROUP_OWNER | 403 | 非群主 |
| 30005 | ROOM_SELF_NOT_ALLOWED | 400 | 不能和自己建单聊 |
| 40001 | MESSAGE_NOT_FOUND | 404 | 消息不存在 |
| 40002 | MESSAGE_RECALL_TIMEOUT | 422 | 超过撤回时限 |
| 40003 | NOT_MESSAGE_SENDER | 403 | 非消息发送者 |
| 50001 | ALREADY_FRIEND | 409 | 已是好友 |
| 50002 | REQUEST_NOT_FOUND | 404 | 申请不存在 |
| 50003 | USER_BLOCKED | 403 | 已被拉黑 |
| 60001 | FILE_TOO_LARGE | 422 | 文件过大 |
| 60002 | FILE_TYPE_NOT_ALLOWED | 422 | 文件类型不允许 |
| 90001 | RATE_LIMITED | 429 | 请求过于频繁 |
| 99999 | INTERNAL_ERROR | 500 | 服务器内部错误 |

---

## 3. 认证接口

### POST `/api/v1/auth/register`

**请求**
```jsonc
{ "username": "fisher", "password": "abcd1234", "nickname": "渔夫" }
```

| 字段 | 类型 | 校验 |
|:---|:---|:---|
| username | string | 3-20 字符，字母数字下划线 |
| password | string | 8-32 位，含字母和数字 |
| nickname | string | 可选，1-50 字符 |

**响应** `201`
```jsonc
{ "code": 0, "data": { "id": "10001", "username": "fisher", "nickname": "渔夫" } }
```

**错误**：`10001` 用户名已存在 · `10004` 密码强度不足 · `90001` 频控

---

### POST `/api/v1/auth/login`

**请求**
```jsonc
{ "username": "fisher", "password": "abcd1234" }
```

**响应** `200`
```jsonc
{
  "code": 0,
  "data": {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "eyJhbGciOi...",
    "expires_in": 604800,
    "user": { "id": "10001", "username": "fisher", "nickname": "渔夫", "avatar_url": null }
  }
}
```

**错误**：`10002` 密码错误 · `10003` 用户不存在 · `90001` 频控（IP 10次/分）

---

### POST `/api/v1/auth/refresh`

**请求** `{ "refresh_token": "..." }`
**响应** `200` 同 login 的 token 部分
**错误**：`20003`

---

## 4. 用户接口

### GET `/api/v1/users/me`

**响应** `200`
```jsonc
{ "code": 0, "data": { "id": "10001", "username": "fisher", "nickname": "渔夫", "avatar_url": null, "created_at": "2026-09-18T12:00:00Z" } }
```

### PATCH `/api/v1/users/me`

**请求** `{ "nickname": "老渔夫", "avatar_url": "https://..." }`
**响应** `200` 同 GET

### GET `/api/v1/users/search?keyword=xxx`

**响应** `200`
```jsonc
{ "code": 0, "data": { "list": [ { "id": "10002", "username": "crab", "nickname": "螃蟹" } ] } }
```

---

## 5. 会话接口

### GET `/api/v1/rooms`

**响应** `200`
```jsonc
{
  "code": 0,
  "data": {
    "list": [
      {
        "id": "50001",
        "type": 1,
        "name": null,
        "avatar_url": null,
        "last_message": { "id": "880", "type": 1, "content": "那游标分页呢", "from_uid": "10002", "created_at": "2026-09-18T12:38:00Z" },
        "unread_count": 3,
        "updated_at": "2026-09-18T12:38:00Z"
      }
    ]
  }
}
```

> 按 `rooms.updated_at` 倒序。会话列表不分页（量级小）。

---

### POST `/api/v1/rooms/single`

创建或获取单聊会话（**幂等**）。

**请求** `{ "target_uid": "10002" }`
**响应** `201` / `200`
```jsonc
{ "code": 0, "data": { "id": "50001", "type": 1, "name": null } }
```

**错误**：`50003` 已被对方拉黑 · `30005` target_uid 是自己 · `10003` 用户不存在

---

### POST `/api/v1/rooms/group`

**请求**
```jsonc
{ "name": "MinIM 开发组", "member_ids": ["10002", "10003"] }
```

**响应** `201`
```jsonc
{ "code": 0, "data": { "id": "50002", "type": 2, "name": "MinIM 开发组", "member_count": 3 } }
```

**错误**：`30003` 成员超限（>500）

---

### GET `/api/v1/rooms/{room_id}/members`

**响应** `200`
```jsonc
{
  "code": 0,
  "data": {
    "list": [
      { "user_id": "10001", "nickname": "螃蟹", "avatar_url": null, "role": 1 },
      { "user_id": "10002", "nickname": "渔夫", "avatar_url": null, "role": 2 }
    ]
  }
}
```

**错误**：`30002` 非成员

---

### DELETE `/api/v1/rooms/{room_id}/members/me`

退群。**响应** `200` `{ "code": 0, "data": null }`

---

## 6. 消息接口 ⭐ 核心

### GET `/api/v1/rooms/{room_id}/messages`

**Query**

| 参数 | 类型 | 默认 | 说明 |
|:---|:---|:---|:---|
| cursor | string | — | 游标 |
| limit | int | 20 | 最大 50 |

**响应** `200`
```jsonc
{
  "code": 0,
  "data": {
    "list": [
      {
        "id": "880",
        "room_id": "50001",
        "from_uid": "10002",
        "type": 1,
        "content": "那游标分页呢",
        "extra": null,
        "reply_to": null,
        "created_at": "2026-09-18T12:38:00Z"
      }
    ],
    "next_cursor": "860",
    "has_more": true
  }
}
```

**错误**：`30002` 非成员

---

### POST `/api/v1/messages`

**请求**
```jsonc
{
  "room_id": "50001",
  "type": 1,
  "content": "想清楚了，单聊群聊共用一张表",
  "reply_to_id": null,
  "extra": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---:|:---|
| room_id | string | ✅ | |
| type | int | ✅ | 见消息类型枚举 |
| content | string | 文本必填 | 最长 4096 |
| reply_to_id | string | — | 回复的消息 ID |
| extra | object | — | 图片/文件等扩展信息 |

**响应** `201`
```jsonc
{ "code": 0, "data": { "id": "881", "room_id": "50001", "from_uid": "10001", "type": 1, "content": "想清楚了...", "created_at": "..." } }
```

**错误**：`30002` 非成员 · `90001` 频控（20条/分）

> 敏感词命中时**不报错**，返回替换后的内容。

---

### POST `/api/v1/messages/{msg_id}/recall`

**响应** `200` `{ "code": 0, "data": null }`

**错误**：`40003` 非发送者 · `40002` 超过撤回时限（2 分钟）

---

### POST `/api/v1/messages/{msg_id}/marks`

**请求** `{ "mark_type": 1 }`（1 点赞 · 2 点踩）
**响应** `200`
```jsonc
{ "code": 0, "data": { "msg_id": "881", "mark_type": 1, "count": 3 } }
```

重复提交同一 mark_type = 取消（幂等切换）。

---

## 7. 好友接口

### POST `/api/v1/friends/requests`

**请求** `{ "to_uid": "10002", "message": "加个好友" }`
**响应** `201` `{ "code": 0, "data": { "id": "70001", "status": 0 } }`

**错误**：`50001` 已是好友 · `50003` 已被拉黑 · `409` 已有待处理申请

### GET `/api/v1/friends/requests?type=received`

**响应** `200`
```jsonc
{ "code": 0, "data": { "list": [ { "id": "70001", "from_user": {"id":"10002","nickname":"渔夫"}, "message": "加个好友", "status": 0, "created_at": "..." } ] } }
```

### PUT `/api/v1/friends/requests/{request_id}`

**请求** `{ "action": "accept" }`（accept / reject）
**响应** `200` `{ "code": 0, "data": { "room_id": "50001" } }`（接受时返回建立的会话）

### GET `/api/v1/friends`

**响应** `200` 好友列表

### DELETE `/api/v1/friends/{friend_id}`

**响应** `200`

---

## 8. 文件接口

### POST `/api/v1/files`

`multipart/form-data`，字段名 `file`

**限制**
| 项 | 值 |
|:---|:---|
| 图片 | ≤ 10 MB，jpg/png/gif/webp |
| 文件 | ≤ 50 MB |
| 单用户 | 10 次/分钟 |

**响应** `201`
```jsonc
{ "code": 0, "data": { "id": "90001", "url": "https://minio.local/mallchat/xxx.png", "mime_type": "image/png", "size": 204800 } }
```

**错误**：`60001` 文件过大 · `60002` 类型不允许

---

## 9. WebSocket 协议

### 9.1 连接

```
WS /ws?token=<access_token>&last_seq=<可选>
```

| 关闭码 | 含义 |
|:---:|:---|
| 4001 | token 无效或过期 |
| 4002 | 连接数超限 |
| 4003 | 心跳超时 |

### 9.2 统一信封

```jsonc
{
  "type": "message.new",
  "seq": 12345,
  "data": { ... },
  "ts": 1758174000000
}
```

| 字段 | 说明 |
|:---|:---|
| type | 事件类型 |
| seq | 服务端单调递增序号，**断线补偿的依据** |
| data | 业务负载 |
| ts | 服务端时间戳（毫秒） |

### 9.3 客户端 → 服务端

| type | data | 说明 |
|:---|:---|:---|
| `ping` | `{}` | 心跳，建议 30s 一次 |
| `message.read` | `{room_id, last_read_msg_id}` | 上报已读 |

### 9.4 服务端 → 客户端

| type | data | 说明 |
|:---|:---|:---|
| `pong` | `{}` | 心跳响应 |
| `message.new` | 消息对象 | 新消息 |
| `message.recalled` | `{room_id, msg_id}` | 消息被撤回 |
| `message.read` | `{room_id, user_id, last_read_msg_id}` | 对方已读 |
| `room.updated` | 会话对象 | 会话信息变更 |
| `member.joined` | `{room_id, user}` | 有人入群 |
| `member.left` | `{room_id, user_id}` | 有人退群 |
| `friend.request.new` | 申请对象 | 收到好友申请 |
| `friend.request.accepted` | `{user, room_id}` | 申请被接受 |
| `sync.done` | `{}` | 断线补偿完成 |

### 9.5 断线补偿

```
1. 客户端记录最后收到的 seq
2. 重连时带 last_seq
3. 服务端补发所有 seq > last_seq 的事件
4. 补发完毕发送 sync.done
```

**服务端保留最近 1000 条事件**用于补偿（Redis 或内存）。

---

## 10. 契约变更流程

```
1. 提出变更 → 更新本文档
2. 更新 OpenAPI 注解 / Pydantic 模型
3. 通知 FE 与 QA
4. git commit 里注明 [BREAKING] 或 [COMPAT]
5.  Breaking 变更需要 FE 确认才能合入
```

**契约即法律。** 任何一方单方面改动契约，另一方的代码就会在半夜崩掉。
