# 说明书核对系统

基于冻结方案的一期本地验证型 MVP。当前完成阶段 2：在阶段 1 的材料解析能力上，使用版本化通用规则和模板批注动态生成核对清单，并支持编辑、停用、乐观锁与不可变版本确认。

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

## 阶段 1～2 API

- `POST /api/v1/tasks`：multipart 创建并解析任务。
- `GET /api/v1/tasks`：查询任务列表。
- `GET /api/v1/tasks/{task_id}`：查询任务、材料、告警和 `DocumentGraph`。
- `GET /api/v1/tasks/{task_id}/check-items`：查询生成的核对清单。
- `PATCH /api/v1/tasks/{task_id}/check-items/{item_id}`：按项目版本号编辑核对项。
- `POST /api/v1/tasks/{task_id}/check-items/confirm`：按清单修订号确认并冻结快照。

创建任务使用以下 multipart 字段：

- `name`：任务名称。
- `manual`：待核对说明书 DOCX。
- `template`：含批注要求的模板 DOCX。
- `project`：符合 `schema_version=1.0` 的项目 JSON。
- `evidence_files`：可重复提交的 PDF、PNG、JPG 或 JPEG 依据材料。

解析成功后系统合并通用规则与模板批注动态要求，任务停在 `AWAITING_CHECKLIST_CONFIRMATION`。清单确认后进入 `QUEUED`，阶段 2 不会启动正式核对。前端确认页路径为 `/tasks/{task_id}/checklist`。

## 当前边界

- 尚未实现证据匹配、正式结论判断、人工复核和报告。
- 动态批注核对项通过无工具、无 Handoff、无 Session 的 OpenAI Agents SDK Agent 生成；普通自动测试使用确定性的 Fake Agent。
- 创建任务前必须在 `.env` 配置 `OPENAI_API_KEY` 与 `OPENAI_MODEL`；模型与 Base URL 由服务端配置，前端不接触密钥。
- 扫描型 PDF 不执行 OCR；作为可选依据时产生告警并忽略。
- `.env` 和 `data/` 不会提交到 Git。
