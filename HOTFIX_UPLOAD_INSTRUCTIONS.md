# 本版本上传说明

本包从 Git 提交 `2dad570`（v4.1）重新构建，不包含后续 WorkBuddy 文件。

上传时将解压后的全部内容拖入 GitHub 仓库根目录并替换同名文件。需要同时保留：

- `app.py`
- `core/`
- `config/`
- `scripts/`
- `.github/workflows/two_stage_reports.yml`
- `requirements.txt`

若仓库里还留有 `workbuddy_connector/`、`WORKBUDDY_SETUP.md`、`static/workbuddy/` 或 `core/workbuddy_export.py`，应在提交前删除；它们不属于本版本。

上传后按 [EMAIL_SUBSCRIPTION_SETUP.md](EMAIL_SUBSCRIPTION_SETUP.md) 配置订阅密钥，再 Reboot Streamlit 应用。
