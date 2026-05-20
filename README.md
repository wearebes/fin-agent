# fin-agent

`fin-agent` 当前是一个面向金融研究代理的 Python scaffold。它已经具备统一配置加载、CLI/API 入口、研究流程阶段规划、以及运行结果的内存持久化骨架，但还没有接入真实的 OpenAI、Exa、YFinance provider client，也不会执行真实检索、推理或行情拉取。

## 当前能力边界

- 已实现：
  - 通过 `configs/`、`.env`、环境变量和默认值装配 `AppSettings`
  - 通过 `fin-agent research run` 生成一个 research workflow 的阶段计划结果
  - 通过 `fin-agent api` 暴露 health 和 research run API
  - 将运行结果暂存在内存 `RunStore`
- 未实现：
  - 真实 LLM 调用
  - 真实搜索调用
  - 真实市场数据调用
  - 数据库持久化

## 快速启动

```bash
conda env create -f environment.yml
conda activate fin-agent
python -m pip install -e ".[dev]"
cp .env.example .env
```

```bash
fin-agent doctor
fin-agent research run --question "Summarize AAPL positioning" --ticker AAPL
fin-agent api --reload
pytest
```

`fin-agent doctor` 负责检查当前配置树和运行时必填 secret；`research run` 和 API 目前只返回 scaffold 级别的阶段规划结果，不代表已经执行真实外部 provider 调用。

## 开发文档

仓库结构、调用链、配置优先级、占位层边界和后续扩展入口见 `docs/developer-guide.md`。
