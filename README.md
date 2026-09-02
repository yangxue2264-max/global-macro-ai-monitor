# Global Macro AI Monitor v2.2

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

## API配置
OpenAI可选；FRED Key建议配置，以使用官方宏观API。未配置或请求失败时，系统仍会回退FRED CSV、美国财政部和明确标注的市场代理。

`.streamlit/secrets.toml`:
```toml
OPENAI_API_KEY = "..."
OPENAI_MODEL = "gpt-5.6-luna"
FRED_API_KEY = "..."
```

## 自动晨报
GitHub Actions 已预设工作日北京时间 08:25 运行，生成日度 JSON 历史。

## 免费数据源
- Yahoo Finance / yfinance
- FRED官方API；失败回退FRED CSV
- 美国财政部名义与实际利率曲线
- 东方财富 / 腾讯：创业板指、科创50精确指数回退
- 创业板ETF / 科创50ETF：最后一级、明确标注的行情代理
- NOAA CPC
- GDELT；失败回退 Google News RSS
- OpenAI Responses API（可选）

免费源不是交易级行情。

## v2.2新增
- 正式读取 `FRED_API_KEY`，并显示本次成功返回的FRED序列数量
- 新增科创50；创业板指和科创50支持多源精确指数回退
- 精确指数不可用时使用明确标注的ETF代理，不伪装成指数
- 顶部手动刷新按钮、行情日期、页面更新时间和指标级来源说明
- 修正官方数据与市场代理的健康统计口径

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
