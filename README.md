# Privacy & TOS AI Analyzer · 隐私政策与用户协议 AI 智能分析器

> Lightweight Edge/Chrome extension + local Python backend that uses LLMs to analyze privacy policies and Terms of Service: legal-dimension scoring, unfair-clause flags, radar chart.
> 轻量级 Edge/Chrome 插件 + 本地 Python 后端：用大模型分析《隐私政策》与《用户协议》，按法律维度打分、标出霸王条款、生成雷达图。

## Features · 核心功能

- One-click extraction of the current page text; backend pre-checks whether it is really a policy/TOS, with forced analysis as a fallback.
  一键提取当前页面文本；后端先判断是否为协议内容，必要时可强制执行。
- 3 evaluation rounds per document; median scores reduce AI scoring fluctuation.
  同一份协议评估 3 次，取中位数，降低 AI 打分波动。
- Weighted dimension scores, penalty flags, overall trust score, SVG radar chart.
  加权维度评分、特殊扣分项、综合信任分与 SVG 雷达图。
- Evaluation history is persisted locally as JSON.
  评测历史以 JSON 形式保存到本地。

## Architecture · 架构

- `popup.html` / `popup.js` — Edge/Chrome Manifest V3 extension.
- `server.py` — local HTTP server on port 8000.
- `python_script/evaluator.py` — LLM evaluation logic (DeepSeek by default).
- `python_script/sec.md` / `cont.md` and `sec.json` / `cont.json` — scoring criteria for privacy policy and ToS.

Provider: DeepSeek by default; switch in `python_script/config.yaml` (`llm_provider`, `base_url`, `model`, API keys) or via env vars (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `ORCAROUTER_API_KEY`).
模型供应商：默认 DeepSeek；可在 `python_script/config.yaml` 或环境变量中切换（如 OrcaRouter）。

## Quick Start · 快速开始

Backend / 后端：

1. `pip install openai`
2. Set `DEEPSEEK_API_KEY` or edit `python_script/config.yaml`.
   配置 API Key（环境变量或 `config.yaml`）。
3. `python server.py` — serves http://localhost:8000.
   启动本地服务。

Extension / 扩展：

1. Open `edge://extensions` (or `chrome://extensions`), enable Developer mode.
   打开扩展管理页并开启开发者模式。
2. "Load unpacked" and select this folder (contains `manifest.json`).
   选择"加载解压的扩展程序"，指向本目录。
3. Open a privacy policy / ToS page, click the extension icon, and choose 隐私政策智能评估 or 用户协议智能评估.
   打开协议页面，点击插件图标，选择"隐私政策智能评估"或"用户协议智能评估"。

Results are appended to `python_script/sec_evaluation_result.json` (privacy) and `python_script/cont_evaluation_result.json` (ToS).
分析结果会追加保存到 `python_script/sec_evaluation_result.json`（隐私政策）和 `python_script/cont_evaluation_result.json`（用户协议）。

## License · 许可证

CC0 — free to use, modify and redistribute. / 放弃一切权利，可自由使用、修改与再分发。
