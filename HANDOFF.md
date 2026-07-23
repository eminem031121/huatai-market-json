# Handoff

## 当前目标

把七只 A 股的华泰行情在交易日北京时间 14:27、14:31、14:36 抓取为公开 JSON，供 GPT 读取。

## 架构边界

- `a-share-paper-trading.getQuote` 是结构化行情真源。
- `query-indicator.queryIndicator` 只作为分时、小时线和量额的 Markdown 补充。
- 不调用账户、持仓、委托、下单、撤单等接口。
- Pages 只暴露行情结果，Key 只存在 GitHub Secret。
- 七只结构化行情不完整时，绝不覆盖最后有效 `latest.json`。

## 关键文件

- `config/watchlist.json`：股票清单、分析查询和保留期。
- `src/market_json/huatai.py`：华泰 HTTP 契约。
- `src/market_json/app.py`：交易日判断、生成、快照和清理。
- `.github/workflows/refresh-market.yml`：调度、提交生成数据、Pages 部署。
- `tests/`：成功、休市、部分失败和分析失败保护。

## 部署待办

本机没有 GitHub CLI，因此当前交付不包含远程仓库创建和首次 Pages 部署。后续需要：

1. 创建公开 GitHub 仓库。
2. 推送 `main`。
3. 配置 `HT_APIKEY` Secret。
4. 将 Pages Source 设为 GitHub Actions。
5. 手动运行工作流并核对 `latest.json`。

## 已知限制

- GitHub Cron 不保证准点；三次调度用于缓解延迟和单次失败。
- `analysis.answerMarkdown` 无稳定字段契约。
- `exchange-calendars` 能覆盖常规休市安排，但突发临时休市仍需人工关注。
- GitHub Pages 是公开静态站点，不适合账户数据或任何敏感信息。

