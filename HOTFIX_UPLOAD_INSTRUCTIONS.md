# Streamlit ImportError 修复说明

## 原因

仓库根目录的 `app.py` 已经是 v4.1，但 `core/preopen.py` 或其他配套文件仍是旧版本。新版 `app.py` 导入了竞价判断函数，旧版模块没有这些函数，因此启动时出现 `ImportError`。

## 上传方法

1. 解压 `A股盘前机会雷达_v4.1_Streamlit修复包.zip`。
2. 打开 GitHub 仓库 `global-macro-ai-monitor` 的根目录。
3. 将解压后的全部文件和文件夹直接拖入仓库根目录，并确认选择替换同名文件。
4. 不要再套一层 `macro_monitor_v4` 文件夹；正确路径必须是：
   - `app.py`
   - `core/preopen.py`
   - `core/providers.py`
   - `config/a_share_map.json`
   - `config/default_user_watchlist.json`
   - `scripts/generate_auction_snapshot.py`
   - `.github/workflows/auction_snapshot.yml`
5. 提交后打开 Streamlit Cloud，点击 `Manage app` → `Reboot app`。

## 快速核对

在 GitHub 打开 `core/preopen.py`，搜索：

```python
def rerank_signals_after_auction
```

能够找到该函数，才说明竞价模块与 `app.py` 已同步。
