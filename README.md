# A股科技基金风格漂移：LangGraph 多智能体 Demo

GitHub Pages 在线版提供 `159552` 真实公开数据快照；动态分析任意六位基金代码需运行本地 Python 服务。

自主研究采用两阶段协议：知识图谱 Agent 先从文献测度、机制和局限中提出研究缺口与候选方向，并停在人工确认闸门；用户确认方向后，研究员才生成带 SHA-256 指纹的 Python 实验程序，通过白名单统计工具运行该方向的实验。审核员检查固定基线、失败假设和窗口敏感性，报告员最后写入证据绑定、数据版本、执行日志与复现成本。GitHub Pages 使用 `159552` 的预计算方向快照演示该流程；动态代码生成与真实数据计算只在本地 Python 服务执行。

## 运行

```powershell
& ".\.venv\Scripts\python.exe" -m ai4s_style_drift.graph
```

当前项目已在 `.venv` 中安装 LangGraph。验证安装及图类型：

```powershell
& ".\.venv\Scripts\python.exe" -c "from importlib.metadata import version; from ai4s_style_drift.graph import HAS_LANGGRAPH, build_research_graph; print(version('langgraph'), HAS_LANGGRAPH, type(build_research_graph()).__name__)"
```

运行测试：

```powershell
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -v
```

## 可视化研究台

启动本地服务：

```powershell
& ".\.venv\Scripts\python.exe" -m ai4s_style_drift.server --port 8765
```

浏览器访问 `http://127.0.0.1:8765`。仪表盘会直接调用 LangGraph，并展示研究节点、风格暴露、漂移距离、变化点、归因和稳健性结果。

研究台包含两种模式：

- **指定基金分析**：输入基金代码或名称，运行契约解析、风格测量、变化点、归因与稳健性研究图。
- **自主研究推理**：识别研究缺口，提出假设，执行滚动窗口敏感性与 placebo 对照实验，并生成带结论和局限性的科学实验报告。

自主研究报告还强制包含：文献测度/机制/局限抽取、主张—证据 ID 绑定、DOI 格式与元数据核验、冻结参数的样本外基线比较、失败和未检验假设、代码与数据 SHA-256 指纹、公开数据清单以及复现运行成本。当前 DOI 状态是离线种子元数据核验，并非在线解析验证。

`DEMO-TECH` 等非六位标识继续使用确定性合成夹具；六位基金代码使用公开真实数据适配器。

## 公开真实数据

输入六位基金代码时，系统自动切换到公开数据适配器。当前接入：

- 东方财富基金净值 JSON：目标基金与 ETF 代理因子的月度收益；
- 东方财富基金档案页面：季度前十大持仓；
- 东方财富规模变动页面：基金份额和资产规模记录。

原始响应缓存到 `.cache/public_fund_data/`，每页记录来源 URL、UTC 抓取时间、字节数和 SHA-256。首次同步或强制刷新需要联网：

```powershell
& ".\.venv\Scripts\python.exe" -m ai4s_style_drift.sync_data 588000 --refresh
```

因子模型为公开 ETF 代理模型 `v1`，不是正式的 CSMAR/Wind/聚宽因子库。资金流目前只取得规模原始表，尚未完成经收益调整的申赎流量估算。公开端点不是官方稳定 API，使用前应检查网站条款、抓取频率和数据许可。

## 研究图

契约解析 → 风格测量（滚动因子回归）→ 变化点检测 → 漂移归因 → 稳健性审查 → 报告。

当前数据是可重复生成的合成数据，故意模拟 2024 年起由“大盘成长科技”向“小盘/动量”漂移。将 `data.py` 的 `make_demo_data` 替换为经过授权的 NAV、持仓、基准和因子数据即可进入真实研究。

## 生产化扩展

- 将每个 Agent 包装为 AutoGen/CrewAI role，LangGraph 仍作为顶层状态机。
- 使用 MCP 暴露基金公告、行情、因子计算和回测工具。
- 为每个结论保存数据版本、代码版本、方法、证据页码和置信度。
- 对真实数据增加披露滞后、幸存者偏差、经理变更和交易成本处理。
