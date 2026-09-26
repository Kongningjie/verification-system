# 说明书核对系统

基于冻结方案的一期本地验证型 MVP。当前仅完成阶段 A 工程骨架：FastAPI、Vue 3、SQLite、Alembic、配置加载、健康检查和基础测试。

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

## 当前边界

- 未实现文件上传、DOCX/PDF 解析、核对清单、模型调用和报告。
- OpenAI Agents SDK 已声明为后端依赖，但阶段 A 不读取或验证真实 API Key。
- `.env` 和 `data/` 不会提交到 Git。
