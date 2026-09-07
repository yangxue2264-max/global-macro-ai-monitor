# WorkBuddy 接入操作指南

## 已完成的部分

项目已经包含一套可提交到 WorkBuddy 开放平台的 MCP 连接器：

- `workbuddy_connector/connector-meta.json`：连接器名称、描述和使用示例。
- `workbuddy_connector/mcp.json`：本地 Node.js MCP Server 启动配置。
- `workbuddy_connector/server.mjs`：读取网站只读数据并提供三个工具。
- `workbuddy_connector/skills/a-share-preopen/SKILL.md`：约束AI的调用顺序、输出格式和投资表述边界。

网站部署后，公开数据地址为：

`https://yang-global-macro-ai-monitor.streamlit.app/app/static/workbuddy/latest.json`

该文件只包含公开新闻、公开行情、主题映射和默认自选股，不包含券商账户、持仓、交易密码或其他敏感凭证。

## 第一步：先更新网站仓库

把本项目根目录的全部文件上传到现有 GitHub 仓库，确保新增文件和修改后的工作流都被保留。上传后：

1. 在 GitHub Actions 中手动运行 `Daily 09:00 A-share pre-open snapshot`。
2. 等待任务成功，并确认仓库出现 `static/workbuddy/latest.json`。
3. 打开上面的静态数据地址，应看到JSON内容，而不是404页面。
4. 再手动运行 `Daily 09:27 A-share auction snapshot`。只有在交易日09:26之后且竞价数据源可用时，该任务才会生成有效结果。

## 第二步：本地测试连接器

在项目根目录运行：

```bash
RADAR_DATA_FILE=static/workbuddy/latest.json node workbuddy_connector/server.mjs
```

输入下面一行并回车：

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

如果返回三个工具，说明连接器基础通信正常。按 `Ctrl+C` 退出。

## 第三步：入驻WorkBuddy开放平台

1. 打开 `https://open.workbuddy.cn/` 并登录WorkBuddy账号。
2. 完成个人开发者入驻和实名认证。
3. 新建“连接器”，选择 `MCP + Skill` 接入。
4. 上传或按平台表单填写 `workbuddy_connector/` 中的配置和图标。
5. 在预览态测试以下三句话：
   - “生成今天的A股盘前晨报，只保留最值得研究的三项。”
   - “检查我的自选股今天是否受到隔夜新闻影响。”
   - “集合竞价后，哪些股票仍有预期差，哪些已经定价？”
6. 核对返回日期、新闻来源、网站链接和竞价阶段，再提交审核。

WorkBuddy官方要求个人开发者准备中国大陆二代身份证号码、实名手机号、可接收验证码的邮箱，并完成手机人脸识别。这一步只能由账号本人操作。

## 第四步：设置两条自动化

### 每个交易日09:00

```text
调用“A股盘前机会雷达”生成今天的09:00盘前候选摘要。只报告命中我自选股且证据可靠的前三项；每项必须包含事件、来源、海外价格验证、A股标的、传导链、下一检查和失效条件。若数据日期不是今天，或没有有效候选，请明确说明，不要补写。最后附完整网站链接。研究辅助，不构成投资建议。
```

### 每个交易日09:27

```text
调用“A股盘前机会雷达”复核今天09:00的候选。按“仍有预期差、基本定价、过度定价/追高风险、A股不确认”分类，只列命中我自选股的结果，并解释竞价涨跌与海外方向的关系。若当日竞价数据缺失，不得输出定价结论，只提示继续等待或人工核查。最后附完整网站链接。研究辅助，不构成投资建议。
```

首次设置后先点击测试运行，确认内容和日期正确，再开启企业微信或WorkBuddy小程序推送。

## 工具说明

| 工具 | 用途 | 是否写入数据 |
| --- | --- | --- |
| `get_daily_brief` | 默认自选股或网站链接自选股的盘前摘要 | 否 |
| `analyze_watchlist` | 分析用户直接提供的1至30只股票 | 否 |
| `analyze_stock` | 分析单只股票及其证据链 | 否 |

## 当前边界

- 当前连接器是只读研究工具，不提供买卖建议、仓位、目标价或自动交易。
- 自选股继续以网站URL中的 `watch` 参数保存；WorkBuddy可读取该参数，但不会替用户修改网站。
- 09:00只形成海外候选；必须取得当日09:27竞价数据后，才能讨论A股是否已经定价。
- 免费行情和新闻数据可能延迟或中断。关键数据缺失时应降低结论，而不是使用旧数据补齐。
