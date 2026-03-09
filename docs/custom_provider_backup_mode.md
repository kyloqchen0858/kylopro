# Kylopro: Custom Provider 仅备用模式说明

## 当前状态
Kylopro 当前使用 Nanobot 的 `custom` provider，并已设置为 "仅备用路" 模式：
- 主路（primary）已关闭，不会再发起主路请求。
- 备路（backup）使用正规 API（当前为 DeepSeek OpenAI 兼容接口）。
- 上层 Agent 入参和返回格式保持不变，不影响任务循环。

## 为什么要这样配置
当主路端点还未确定或不稳定时，保留主路占位地址会导致每次请求先失败，再切备路，终端持续出现黄色告警。

将主路显式关闭后：
- 请求会直接走备用正规 API。
- 终端不再重复出现 `主路请求失败` 的告警。
- 系统行为更稳定，便于后续调试和观察。

## 已生效配置（核心字段）
配置文件：`C:\Users\qianchen\.nanobot\config.json`

```json
{
  "agents": {
    "defaults": {
      "provider": "custom",
      "model": "deepseek-chat"
    }
  },
  "providers": {
    "custom": {
      "primaryApiBase": null,
      "primaryBearerToken": "",
      "primaryExtraHeaders": null,
      "backupApiBase": "https://api.deepseek.com/v1",
      "backupApiKey": "<你的正规备用Key>",
      "backupExtraHeaders": {
        "User-Agent": "Kylopro/1.0"
      }
    }
  }
}
```

## 以后如何开启主路
当你准备好主路后，只需在同一配置文件填写：
- `providers.custom.primaryApiBase`
- `providers.custom.primaryBearerToken`
- `providers.custom.primaryExtraHeaders`（可选）

并保持 `backupApiBase` + `backupApiKey` 不为空作为兜底。

## 快速排错
如果再次出现大量黄色告警，优先检查：
1. `primaryApiBase` 是否误填了占位 URL。
2. `primaryBearerToken` 是否为空但 `primaryApiBase` 非空。
3. 主路 DNS/网络可达性是否异常。

当不需要主路时，保持 `primaryApiBase: null` 是最稳妥方案。
