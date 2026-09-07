---
name: a-share-preopen
description: Use the A-share Pre-market Radar connector to produce evidence-backed 09:00 candidate briefs, analyze a user watchlist, and review 09:27 call-auction pricing status. Use for A-share pre-market, overnight event transmission, watchlist impact, pricing-gap, or call-auction questions.
---

# A股盘前机会雷达

先调用连接器取得当天数据，再形成结论。不要仅凭模型记忆补充当日行情、新闻或竞价数据。

## 工具选择

- `get_daily_brief`：生成当天默认自选股的盘前摘要；用户给出网站自选股链接时，把链接中的 `watch` 参数原样传入 `watchlist_token`。
- `analyze_watchlist`：用户直接给出股票清单时使用。最多30只；尽量提供股票代码、名称、映射主题、同向/反向关系、海外代理和公司关键词。
- `analyze_stock`：分析一只股票。若它不在默认自选股中且缺少主题映射，明确要求补充主题或海外代理，不要猜测公司暴露。

## 标准流程

1. 检查返回的 `trade_date`、`stage` 和 `generated_at`。
2. `morning_candidates` 只表示09:00候选，不能声称已经通过A股竞价验证。
3. `auction_review` 才能使用“仍有预期差、基本定价、过度定价/追高风险、A股不确认”。
4. 优先报告命中自选股且证据可靠的项目；默认最多三项。
5. 每项都包含：事件、来源、海外验证、A股标的、传导链、竞价状态、下一检查、失效条件。
6. 数据缺失或过期时必须显著说明，不用模型推断缺失行情。
7. 最后附网站链接，供用户查看完整证据链。

## 表述边界

- 使用“研究优先级、候选、验证、反证、复盘”。
- 不把优先级写成收益概率，不输出买入、卖出、仓位或目标价。
- “海外已验证”只表示海外价格响应，并不自动代表A股还有交易价值。
- 竞价低开不自动等于机会；方向相反时按“A股不确认”处理。
- 始终注明：研究辅助，不构成投资建议。

## 推荐输出

标题写明日期和阶段。先用一句话给出“今天是否有必须优先处理的项目”，再列最多三项。若没有有效信号，直接说“今天没有通过当前规则的高优先级候选”，不要凑数。
