# 部署步骤

项目按 GitHub + Streamlit Community Cloud + Supabase 准备。

1. 将整个项目上传到 GitHub 仓库根目录，不要再套一层文件夹。
2. 保持 `app.py` 为 Streamlit 入口。
3. 在 Supabase 创建 `subscriptions` 表。
4. 将数据库、SMTP和可选API密钥同时加入 Streamlit Secrets 与 GitHub Actions Secrets。
5. 将 GitHub Actions 的 Workflow permissions 设为 `Read and write permissions`。
6. 先用自己的邮箱完成验证码订阅。
7. 手动运行 `A-share personalized email reports`，分别测试 morning 与 auction；确认无误后依靠定时任务运行。

详细字段、SQL和安全测试顺序见 [EMAIL_SUBSCRIPTION_SETUP.md](EMAIL_SUBSCRIPTION_SETUP.md)。

定时安排：

- A股交易日北京时间08:45：第一阶段个人盘前报告；
- A股交易日北京时间09:27：集合竞价后二次个人报告。
