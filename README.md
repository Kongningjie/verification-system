# 说明书核对系统

基于冻结方案的一期本地验证型 MVP。当前完成阶段 1：任务材料接入、安全校验、DOCX/PDF/图片解析、项目 JSON 标准化，以及统一 `DocumentGraph` 持久化。

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

## 阶段 1 API

- `POST /api/v1/tasks`：multipart 创建并解析任务。
- `GET /api/v1/tasks`：查询任务列表。
- `GET /api/v1/tasks/{task_id}`：查询任务、材料、告警和 `DocumentGraph`。

创建任务使用以下 multipart 字段：

- `name`：任务名称。
- `manual`：待核对说明书 DOCX。
- `template`：含批注要求的模板 DOCX。
- `project`：符合 `schema_version=1.0` 的项目 JSON。
- `evidence_files`：可重复提交的 PDF、PNG、JPG 或 JPEG 依据材料。

解析成功后任务停在 `GENERATING_CHECKLIST`，等待阶段 2 实现清单生成。

## 当前边界

- 尚未实现核对清单、证据匹配、模型调用、结论判断、人工复核和报告。
- OpenAI Agents SDK 已声明为后端依赖，但阶段 1 不读取或验证真实 API Key。
- 扫描型 PDF 不执行 OCR；作为可选依据时产生告警并忽略。
- `.env` 和 `data/` 不会提交到 Git。
