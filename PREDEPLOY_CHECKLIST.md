# PRE-DEPLOY CHECKLIST

## 代码已完成

- [x] 以v4.1为基线，移除WorkBuddy
- [x] 自选股编辑器只要求股票代码或名称
- [x] 系统自动补齐名称、主题、海外代理、传导方向和新闻关键词
- [x] 邮箱验证码后才允许订阅、更新或退订
- [x] 每位订阅者保存独立自选股
- [x] A股交易日08:45与09:27两阶段个人邮件
- [x] GitHub Actions定时任务
- [x] 休市日过滤
- [x] 语法、核心逻辑、自动映射、邮件渲染与Streamlit启动测试

## 上线前账号配置

- [ ] 创建 Supabase 项目并运行建表 SQL
- [ ] 准备专用发件邮箱与 App Password
- [ ] 配置 Streamlit Secrets
- [ ] 配置 GitHub Actions Secrets
- [ ] 开启 GitHub Actions `Read and write permissions`
- [ ] 用自己的邮箱验证完整订阅流程
- [ ] 手动测试 morning 和 auction 两封邮件

配置值与步骤见 [EMAIL_SUBSCRIPTION_SETUP.md](EMAIL_SUBSCRIPTION_SETUP.md)。
