# 邮箱订阅部署配置

## 1. 创建订阅表

在 Supabase 新建项目，进入 SQL Editor，运行：

```sql
create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  watchlist jsonb not null default '[]'::jsonb,
  active boolean not null default true,
  verified_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.subscriptions enable row level security;
```

不要创建匿名读写策略。本项目只在 Streamlit Python 服务端和 GitHub Actions 中使用 secret key；不要把 secret key 写入仓库文件或浏览器代码。旧项目也兼容 `SUPABASE_SERVICE_ROLE_KEY`，但新项目优先使用 `SUPABASE_SECRET_KEY`。

## 2. 配置邮件发送账户

推荐先用专门的 Gmail 发件账户做小规模测试：开启两步验证，生成 App Password。不要填写邮箱登录密码。

需要的配置：

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_..."
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "465"
SMTP_USERNAME = "sender@gmail.com"
SMTP_PASSWORD = "16位App Password"
EMAIL_FROM = "A股盘前机会雷达 <sender@gmail.com>"
APP_URL = "https://your-app.streamlit.app"
OPENAI_API_KEY = "..." # 可选；只用于规则库之外的新股票
OPENAI_MODEL = "gpt-5.6-luna" # 可选
```

## 3. Streamlit Cloud Secrets

在 Streamlit Cloud 应用设置的 Secrets 中添加上面全部配置。它们用于：

- 网页即时发送验证码；
- 验证后保存、更新或取消订阅；
- 自动补齐规则库外的新股票。

## 4. GitHub Actions Secrets

在仓库 `Settings → Secrets and variables → Actions` 中添加同名配置。GitHub Actions 用它们读取订阅者、生成个人报告并发送邮件。

然后在 `Settings → Actions → General → Workflow permissions` 选择 `Read and write permissions`。

## 5. 安全测试顺序

1. 打开网站，只用自己的邮箱收验证码；
2. 输入两三只股票，保存后检查“系统自动补齐的研究映射”；
3. 完成订阅；
4. 在 Actions 手动运行 morning，先保持 `send_emails=false`；
5. 数据文件生成正常后，再用 `send_emails=true` 给自己的已验证邮箱发测试邮件；
6. 同样测试 auction；
7. 最后再让其他用户订阅。

定时任务会在每个周一至周五北京时间08:45与09:27触发，并再次用上交所交易日历过滤休市日。GitHub Actions 可能排队延迟几分钟，邮件会保留真实生成时间。
