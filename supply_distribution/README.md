---
type: Guide
title: 供应链能力分发验收
---

# 能力分发验收

这是独立验收工具，不是新的预测或补货引擎，不重复Claude正在开发的`supply_copilot`。

```powershell
uv run python -m supply_distribution audit --repo . --out D:/private/candidate.json
uv run python -m supply_distribution audit --repo . --git-ref origin/main --out D:/private/main.json
```

读取指定工作区或Git树，不切分支、不执行被审代码、不读取.env、不联网。检测能力模块、打包遗漏、Agent技能发现和限定范围硬编码路径。退出码2为blocked，1为partial；静态结果永不宣称endtoend_success。

用自己的EN凭证测试还需运行候选发布集的联网doctor；本工具没有替代权限/分页/业务语义验收。

私有ZIP完整性验收见`python -m supply_distribution.bundle --help`及[发布契约](docs/release-contract.md)。
