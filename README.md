# 说明书核对系统

基于冻结方案的一期本地验证型 MVP。当前完成阶段 3：确认动态核对清单后，系统在本地串行调度任务，匹配材料内证据，执行确定性规则、文本/视觉判断与风险分级独立复核，并提供可追溯结果。

## 环境要求

- Python 3.12 或 3.13
- Node.js 20+
- npm 10+

## 后端启动

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

访问：`http://127.0.0.1:8000/docs`。

## 前端启动

```powershell
Set-Location frontend
npm install
npm run dev
```

访问：`http://localhost:5173`。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
Set-Location frontend
npm run type-check
npm run build
```

## 阶段 1～3 API

- `POST /api/v1/tasks`：multipart 创建并解析任务。
- `GET /api/v1/tasks`：查询任务列表。
- `GET /api/v1/tasks/{task_id}`：查询任务、材料、告警和 `DocumentGraph`。
- `GET /api/v1/tasks/{task_id}/check-items`：查询生成的核对清单。
- `PATCH /api/v1/tasks/{task_id}/check-items/{item_id}`：按项目版本号编辑核对项。
- `POST /api/v1/tasks/{task_id}/check-items/confirm`：按清单修订号确认并冻结快照。
- `GET /api/v1/tasks/{task_id}/results`：查询并按结论、执行器、严重等级筛选结果。
- `GET /api/v1/tasks/{task_id}/results/{result_id}`：查询结论、证据与运行审计详情。
- `POST /api/v1/tasks/{task_id}/cancel`：取消排队或执行中的任务。
- `POST /api/v1/tasks/{task_id}/retry-errors`：只重跑技术错误项。
- `GET /api/v1/tasks/{task_id}/events`：接收最小 SSE 进度事件。

创建任务使用以下 multipart 字段：

- `name`：任务名称。
- `manual`：待核对说明书 DOCX。
- `template`：含批注要求的模板 DOCX。
- `project`：符合 `schema_version=1.0` 的项目 JSON。
- `evidence_files`：可重复提交的 PDF、PNG、JPG 或 JPEG 依据材料。

解析成功后系统合并通用规则与模板批注动态要求，任务停在 `AWAITING_CHECKLIST_CONFIRMATION`。清单确认后进入本地串行执行槽，单任务内的模型项按配置并行。前端确认页路径为 `/tasks/{task_id}/checklist`，基础结果页为 `/tasks/{task_id}/results`。

## 当前边界

- 尚未实现人工改判、Excel/JSON 报告和完整结果交互页面。
- 动态批注核对项通过无工具、无 Handoff、无 Session 的 OpenAI Agents SDK Agent 生成；普通自动测试使用确定性的 Fake Agent。
- 仅规则任务无需模型配置；动态批注、语义或视觉项执行前必须在 `.env` 配置 `OPENAI_API_KEY` 与 `OPENAI_MODEL`。模型与 Base URL 由服务端配置，前端不接触密钥。
- 模型只能引用系统生成的候选 `evidence_id`；未知 ID 属于技术错误。所有关键模型项及普通级首次 FAIL 均执行第二次隔离判断。
- 扫描型 PDF 不执行 OCR；作为可选依据时产生告警并忽略。
- `.env` 和 `data/` 不会提交到 Git。
