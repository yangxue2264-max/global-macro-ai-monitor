# A股盘前机会雷达 v4.0

一个每天北京时间 09:00 更新的 A 股盘前研究工具。它不重复行情终端，而是把用户自选股、可靠新闻、海外价格确认和 A 股传导映射放进同一个核查流程。

## 产品只回答两个问题

1. **海外已验证：** 可靠新闻出现后，相关美股或海外代理已经显著交易。A 股尚未开盘，可能存在需要核查的盘前预期差。
2. **传导待验证：** 新闻可靠且存在明确 A 股传导链，但海外价格尚未确认。先加入观察，等待集合竞价与开盘量价验证。

这两个标签都不是买卖建议。它们用于安排盘前研究顺序。

## v4.0 信息架构

- **盘前决策台：** 扫描用户自选股，突出直接新闻、主题新闻和海外代理异动，并显示原因与开盘验证步骤。
- **机会雷达：** 合并原“信号流”和“主题账本”，按“海外已验证 / 传导待验证”呈现事件、A 股标的、传导链与失效条件。
- **方法与数据：** 解释阈值、来源、刷新方式与边界。

原“跨资产”页面已经删除。原“定价缺口”不再作为模糊的独立 20 日差值页面，而是被改造成每条机会卡片里的“海外已交易、A 股尚未开盘”盘前预期差。

## 自选股

用户可以在“盘前决策台 → 管理自选股”中直接增删股票，不需要后台修改代码。

- 输入 6 位 A 股代码即可，系统会转换成对应市场后缀。
- 映射主题决定相关新闻和默认传导链。
- 海外代理决定盘前使用哪些海外资产进行价格验证。
- 公司专属关键词只填写公司名称、英文名或常用别名，不要填写“AI、黄金、能源”等宽泛行业词。
- 保存后，自选股配置会编码进当前网址。收藏或复制该网址即可保留个人配置。

这种方案不依赖账户数据库。不同用户可以各自保留自己的配置链接。

## 每日 09:00 快照

`.github/workflows/daily_snapshot.yml` 在每个工作日 `01:00 UTC` 运行，即北京时间 `09:00`。它执行：

```bash
python scripts/generate_morning_brief.py
```

脚本将固定盘前快照保存到：

- `data/latest_morning_brief.json`
- `data/brief_history/YYYY-MM-DD.json`

网站优先读取该快照，日内不会每 15 分钟反复改写结论。若最新快照缺失，网站会做一次按需回退抓取并明确标注。

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
PYTHONPATH=. python tests/test_decision_engine.py
PYTHONPATH=. python tests/smoke_test.py
```

## Streamlit Cloud 部署

1. 将本文件夹内的全部内容上传到现有 GitHub 仓库根目录。
2. 保持 `app.py` 为入口。
3. 确认 GitHub Actions 的 Workflow permissions 为 `Read and write permissions`。
4. 在 Actions 页面手动运行一次 `Daily 09:00 A-share pre-open snapshot`，确认生成 `data/latest_morning_brief.json`。
5. 重新打开 Streamlit 网站，确认页面显示当日快照时间。

基础功能不依赖 OpenAI API。当前 v4 日常工作流不再把 AI 作为单点依赖。

## 数据来源与边界

- Yahoo Finance：海外收盘价格和 A 股上一交易日数据。
- GDELT：新闻发现；失败时回退 Google News RSS。普通工作日读取近24小时，周一读取近72小时以覆盖周末。
- FRED / 美国财政部：只提供隔夜风险背景，不再作为独立跨资产页面。
- 免费数据可能延迟或中断；页面必须保留快照、DEMO 与过期状态标注。

研究辅助，不构成投资建议。
