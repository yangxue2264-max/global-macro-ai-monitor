# PRE-DEPLOY CHECKLIST

## 已自动完成

- [x] Streamlit 主程序
- [x] 免费行情 / FRED / GDELT / Google News fallback
- [x] NOAA CPC ENSO 官方模块
- [x] AI资本开支链条
- [x] 全球跨资产监控
- [x] 主流海外个股与A股观察池
- [x] 新闻证据分层
- [x] 免费源故障时 DEMO fallback，避免现场演示白屏
- [x] 工作日北京时间 08:25 GitHub Actions 晨报
- [x] OpenAI Responses API 接口
- [x] Python 语法检查
- [x] 离线核心逻辑 smoke test

## 用户必须亲自完成

因为涉及账号与密钥授权，下面三步无法代替用户执行：

1. 登录 GitHub，新建一个仓库；
2. 把本项目上传到该仓库；
3. 登录 Streamlit Community Cloud，授权 GitHub 并选择 `app.py` 部署。

### 如需真正开启AI功能
还需要：
4. 在 Streamlit App Secrets 中添加 `OPENAI_API_KEY`。

在完成第 1 步后，把 GitHub 仓库地址发回聊天，我可以继续检查部署结构与后续配置。
