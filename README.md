# 华泰行情 JSON：GitHub Actions + Pages

每天在北京时间 `14:27`、`14:31`、`14:36` 调用华泰 Skill 后端，抓取七只 A 股的结构化实时行情，并把 GPT 可直接读取的 JSON 发布到 GitHub Pages。

## 输出

- `latest.json`：最近一次七只股票全部成功的结构化行情。
- `status.json`：最近一次执行状态；失败或休市时不会覆盖 `latest.json`。
- `snapshots/YYYY-MM-DD/HHMMSS.json`：三个时点的快照，保留最近 90 个交易日。
- `index.json`：服务说明、固定 URL 和股票清单。
- `openapi.yaml`：可导入自定义 GPT Action 的只读 OpenAPI 定义。

结构化 `quotes[]` 保存华泰 `getQuote` 的完整字段，并增加：

- `stockCode`
- `exchange`
- `changePctCalculated`

`analysis.answerMarkdown` 保存 `query-indicator` 返回的分时、小时线、成交量和成交额补充文本。该字段是非结构化 Markdown，不应当作稳定的 K 线数组解析。

## 一次性部署

1. 在 GitHub 新建一个**公开仓库**，把本项目推到默认分支 `main`。
2. 进入 `Settings → Secrets and variables → Actions → Secrets`，新建：
   - 名称：`HT_APIKEY`
   - 值：轮换后的华泰 API Key
3. 进入 `Settings → Pages → Build and deployment`，将 Source 设为 **GitHub Actions**。
4. 在 `Actions` 页手动运行一次 `Refresh Huatai market JSON`。
5. 打开：

   ```text
   https://<GitHub用户名>.github.io/<仓库名>/latest.json
   ```

若使用自定义域名，在 Actions Variables 新建 `PUBLIC_BASE_URL`，值为不带末尾 `/` 的站点根 URL。默认情况下脚本会从 `GITHUB_REPOSITORY` 自动推导 Pages 地址。

## GPT 调取

最简单的方式是在 GPT 提示词或自动任务中固定提供 `latest.json` URL，并要求它先检查：

1. `status`
2. `asOf`
3. `marketDate`
4. `quotes` 是否正好七条

自定义 GPT 可导入 Pages 上的 `openapi.yaml`，使用：

- `getLatestMarketSnapshot`
- `getMarketRefreshStatus`

静态 JSON 没有鉴权，任何知道 URL 的人都可以读取；仓库和 Actions 日志中不包含 `HT_APIKEY`。

为规避缓存，自动读取时可以附加查询参数：

```text
https://<GitHub用户名>.github.io/<仓库名>/latest.json?t=202607231440
```

## 本地运行

项目使用 uv：

```powershell
$env:HT_APIKEY = "<不要写入文件>"
uv sync
uv run refresh-market-json --output public
uv run pytest
```

本地脚本遵循与 Actions 相同的保护规则：七只结构化行情只要缺一只，就只更新 `status.json`，不覆盖最后一份有效的 `latest.json`。

## 调度说明

GitHub Cron 使用 UTC，工作流中的 `06:27/06:31/06:36 UTC` 对应北京时间 `14:27/14:31/14:36`。交易日由 `exchange-calendars` 的上交所日历判断；周末和 A 股休市日跳过。

GitHub 官方说明定时工作流可能因平台负载延迟，甚至在高负载时被丢弃。因此三个时点既保存独立快照，也构成容错重试；它不是秒级准时任务。

## 安全

- 只把 Key 放在 GitHub Actions Secret `HT_APIKEY`。
- 不要提交 `.env` 或本机 `.htsc-skills/config`。
- 行情与分析结果是公开数据，不包含账户、持仓、委托或成交记录。
- 本机 Key 曾在诊断输出中显示过，部署前应先在华泰侧轮换。

