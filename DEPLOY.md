# 部署步骤

项目已按 Streamlit Community Cloud + GitHub 准备。

最终需要用户参与的账号操作：
1. 创建/选择 GitHub 仓库并上传本项目；
2. 用 GitHub 登录 Streamlit Community Cloud；
3. 选择仓库和 `app.py` 部署；
4. 若启用 AI，在 Streamlit Secrets 中粘贴 `OPENAI_API_KEY`；
5. 如需每天自动保存晨报，允许 GitHub Actions workflow 写入 contents。

cron 已换算为北京时间工作日 08:25。


## 当前我已经替你准备好的内容

- `app.py`：网页主程序
- `requirements.txt`：部署依赖
- `.streamlit/config.toml`：网页主题
- `.github/workflows/morning_brief.yml`：工作日 08:25（北京时间）晨报任务
- `.streamlit/secrets.toml.example`：AI密钥模板
- `config/watchlist.json`：资产池，可后续直接修改
- DEMO fallback：免费行情源临时失败时，网页仍可演示，并会明确标识非实时数据

因此，真正需要用户亲自操作的步骤只剩 **GitHub/Streamlit账号授权与API Key粘贴**。
