# A股盘前机会雷达 v4.2

一个每天北京时间 09:00 形成候选池、09:27 用集合竞价二次筛选的 A 股盘前研究工具。它不重复行情终端，而是把用户自选股、可靠新闻、海外价格确认、A 股传导映射和“剩余预期差”放进同一个核查流程。

## 产品回答三个连续问题

1. **海外已验证：** 可靠新闻出现后，相关美股或海外代理已经显著交易，因此进入 09:00 候选池。
2. **传导待验证：** 新闻可靠且存在明确 A 股传导链，但海外价格尚未确认。先加入观察，等待集合竞价与开盘量价验证。
3. **竞价后还有没有交易价值：** 09:27 读取 A 股集合竞价，将候选分成“仍有预期差、基本定价、过度定价/追高风险、A 股不确认”。

这两个标签都不是买卖建议。它们用于安排盘前研究顺序。

## v4.1 信息架构

- **盘前决策台：** 扫描用户自选股，09:00 显示海外候选，09:27 后突出竞价仍有预期差或追高风险的股票。
- **机会雷达：** 合并原“信号流”和“主题账本”，呈现事件、A 股标的、传导链、集合竞价判断与失效条件。
- **方法与数据：** 解释阈值、来源、刷新方式与边界。

原“跨资产”页面已经删除。原“定价缺口”不再作为模糊的独立 20 日差值页面，而是被改造成可行动的二次判断：海外已经交易后，A 股竞价到底消化了多少预期。

## 自选股

用户可以在“盘前决策台 → 管理自选股”中直接增删股票，不需要后台修改代码。

- 输入 6 位 A 股代码即可，系统会转换成对应市场后缀。
- 映射主题决定相关新闻和默认传导链。
- 海外代理决定盘前使用哪些海外资产进行价格验证。
- 公司专属关键词只填写公司名称、英文名或常用别名，不要填写“AI、黄金、能源”等宽泛行业词。
- 保存后，自选股配置会编码进当前网址。收藏或复制该网址即可保留个人配置。

这种方案不依赖账户数据库。不同用户可以各自保留自己的配置链接。

## 每日两次快照

`.github/workflows/daily_snapshot.yml` 在每个工作日 `01:00 UTC` 运行，即北京时间 `09:00`。它执行：

```bash
python scripts/generate_morning_brief.py
```

脚本将固定盘前快照保存到：

- `data/latest_morning_brief.json`
- `data/brief_history/YYYY-MM-DD.json`

网站优先读取该快照，日内不会每 15 分钟反复改写结论。若最新快照缺失，网站会做一次按需回退抓取并明确标注。

`.github/workflows/auction_snapshot.yml` 在每个工作日 `01:27 UTC` 运行，即北京时间 `09:27`。它执行：

```bash
python scripts/generate_auction_snapshot.py
```

竞价结果保存到：

- `data/latest_auction_snapshot.json`
- `data/auction_history/YYYY-MM-DD.json`

系统优先读取 Tushare `stk_auction`；未配置权限时尝试公开行情回退，并在页面明确标注数据模式。用户临时添加的自选股若不在固定快照中，页面会单独按需补取。

> GitHub 定时任务可能因平台排队延迟几分钟；页面会显示真实生成时间。

## 信号规则

### 海外已验证

- 新闻证据分不低于 70；并且
- 一个相关海外代理单日绝对涨跌不低于 2%，或多个代理的单日涨跌中位数绝对值不低于 1%。

### 传导待验证

- 新闻证据分不低于 70；
- 事件能映射到预设 A 股主题和标的；
- 但相关海外代理尚未达到价格确认阈值。

### 机会优先级

`来源可靠度（45）+ 海外价格响应（35）+ 自选股相关性（20）`

优先级不是预期收益率，也不代表 A 股一定跟随海外方向。

### 集合竞价二次判断

系统根据海外方向、标的与海外信号的同向/反向关系，计算“竞价有效反应”：

- **仍有预期差：** 有效反应低于基本定价阈值，进入开盘优先观察。
- **基本定价：** 有效反应达到海外波动约 45%，且至少 1%。
- **过度定价/追高风险：** 有效反应超过海外波动约 125%，且至少 3%。
- **A 股不确认：** 有效反应反向超过 0.5%。
- **方向需人工判断：** 公司可能同时存在受益与受损路径，系统不自动给结论。

这些是待回测的研究阈值，不是收益预测或买卖指令。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

离线测试：

```bash
MACRO_MONITOR_OFFLINE_TEST=1 streamlit run app.py
PYTHONPATH=. python tests/test_preopen.py
PYTHONPATH=. python tests/test_auction_provider.py
PYTHONPATH=. python tests/test_decision_engine.py
PYTHONPATH=. python tests/smoke_test.py
```

## Streamlit Cloud 部署

1. 将本文件夹内的全部内容上传到现有 GitHub 仓库根目录。
2. 保持 `app.py` 为入口。
3. 确认 GitHub Actions 的 Workflow permissions 为 `Read and write permissions`。
4. 在 Actions 页面手动运行一次 `Daily 09:00 A-share pre-open snapshot`，确认生成 `data/latest_morning_brief.json`。
5. 可选：在 GitHub 仓库 `Settings → Secrets and variables → Actions` 添加 `TUSHARE_TOKEN`，以使用官方竞价接口。该接口需要单独的数据权限。
6. 手动运行一次 `Daily 09:27 A-share auction snapshot`，确认生成 `data/latest_auction_snapshot.json`。
7. 重新打开 Streamlit 网站，确认页面同时显示当日 09:00 与竞价数据状态。

基础功能不依赖 OpenAI API。当前 v4.1 日常工作流不再把 AI 作为单点依赖。

## 数据来源与边界

- Yahoo Finance：海外收盘价格和 A 股上一交易日数据。
- GDELT：新闻发现；失败时回退 Google News RSS。普通工作日读取近24小时，周一读取近72小时以覆盖周末。
- FRED / 美国财政部：只提供隔夜风险背景，不再作为独立跨资产页面。
- Tushare `stk_auction`：A 股集合竞价结果，需单独权限；无权限时使用公开行情回退。
- 免费数据可能延迟或中断；页面必须保留快照、DEMO 与过期状态标注。

研究辅助，不构成投资建议。

## WorkBuddy 接入

本版本新增只读的 WorkBuddy 数据通道和 MCP 连接器。网站仍负责数据、规则和证据链，WorkBuddy 负责自然语言调用、定时执行与消息推送。

- 09:00 工作流会在生成晨报后同步生成 `static/workbuddy/latest.json`。
- 09:27 工作流会用当日集合竞价更新同一文件。
- Streamlit 静态地址为 `https://yang-global-macro-ai-monitor.streamlit.app/app/static/workbuddy/latest.json`。
- WorkBuddy 连接器位于 `workbuddy_connector/`，提供 `get_daily_brief`、`analyze_watchlist` 和 `analyze_stock` 三个只读工具。
- 连接器不会修改网站、不会下单，也不会接触券商账户。

完整的安装、测试和自动化设置步骤见 `WORKBUDDY_SETUP.md`。
