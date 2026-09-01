# Global Macro AI Monitor v0.5

面向 **A股开盘前** 的全球投资研究看板。

核心链条：

> **事件 → 状态变量 → 因果传导 → 资产映射 → 市场定价 → 待验证数据 → 反证条件**

## 页面
- 晨间一页
- 研究流：按宏观模块与主题压缩全球信息
- 跨资产
- 宏观七维
- AI资本开支：算力 → 电网/电力 → 商品 → 融资
- 异动雷达
- 事件实验室
- 方法与数据

## 本地运行
```bash
pip install -r requirements.txt
streamlit run app.py
```

## OpenAI（可选）
不配置 API Key 时，行情、宏观、新闻和规则式事件传导仍可工作。

`.streamlit/secrets.toml`:
```toml
OPENAI_API_KEY = "..."
OPENAI_MODEL = "gpt-5.6-luna"
```

## 自动晨报
GitHub Actions 已预设工作日北京时间 08:25 运行，生成日度 JSON 历史。

## 免费数据源
- Yahoo Finance / yfinance
- FRED
- GDELT；失败回退 Google News RSS
- OpenAI Responses API（可选）

免费源不是交易级行情。

## v0.3 新增
- A股开盘前主题映射
- 晨报 Markdown 下载
- 行情 freshness 字段
- 部署 doctor 检查脚本

## 离线逻辑测试
```bash
PYTHONPATH=. python tests/smoke_test.py
```

## v0.7 新增
- NOAA CPC 官方 ENSO 模块
- 气候 → 农业 → 食品通胀 → 资产的传导链
- 玉米 / 大豆 20日价格验证
- 免费行情源失败时自动 DEMO fallback，且显式标识非实时
- 新闻证据分层

## v0.8 新增
- 隔夜主题 → A股/中国资产观察池
- AI服务器、光模块、PCB、电网、铜资源、农业等主题代理
- 行情 as-of 日期与数据模式标记
- 修复 GitHub Actions 的 Python import path
- 部署前检查清单

## v0.9
- 增加关键行情 as-of 日期与数据状态表，避免把延迟/演示数据误认为实时。
