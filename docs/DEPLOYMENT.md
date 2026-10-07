# 用户目录部署

目录建议：`~/apps/agent-workbench`。用户运行环境与系统 Java/Node 分离。

```text
agent-workbench/
  app.jar
  .env                    # chmod 600; 不提交
  deploy/start.sh
  deploy/stop.sh
  qa/                     # npm ci 安装 playwright
  runtime/jre/            # Java 21 JRE
  runtime/node/           # Node 22
  runtime/browsers/       # Playwright Chromium
  data/                   # 项目快照、验收截图与加密模型配置
  logs/
```

1. 本地执行 README 构建命令，复制 JAR 为服务器的 `app.jar`，上传 `qa` 和 `deploy`。
2. 安装与服务器架构对应的 Java 21 JRE、Node 22，校验官方 SHA256，分别放到 `runtime/jre` 和 `runtime/node`。
3. 在服务器执行：

```bash
cd ~/apps/agent-workbench
export PATH="$PWD/runtime/node/bin:$PATH"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/runtime/browsers"
cd qa && npm ci && npx playwright install chromium
cd ..
cp .env.example .env
chmod 600 .env
bash deploy/start.sh
curl -f http://127.0.0.1:18123/api/workbench/config
```

`start.sh` 默认绑定本机回环地址；在已确认的受控内网需要访问时设置 `BIND_ADDRESS=0.0.0.0`。公网部署应添加 HTTPS 反向代理，限制请求体和请求速率，再开启真实 API。

启动脚本使用 nohup，可跨 SSH 断开继续运行。它**不会保证服务器重启后的自动启动**。提供了用户级 systemd 样例，但只有服务器用户 systemd manager 可用且完成环境变量配置后才适用。不要将 start.sh 和 systemd 同时用于同一进程。

## API 配置

没有域名的内网部署可按 [内网 HTTPS](HTTPS.md) 配置专用证书。访问设备需要导入该证书后才能获得无警告的连接。

默认保持 `WORKBENCH_MODE=demo`，用户在网页侧栏“模型配置”自行填写 Base URL、模型名和 Key，保存并启用后即可生成，不需要重启。保存本身不调用模型；可点击“测试已保存配置”进行一次少量 Token 的连接测试。模型需要兼容 Chat Completions 接口。

配置按浏览器空间保存在 `data/providers`，AES-256-GCM 主密钥位于 `.master-key`，Linux 权限为目录 700、文件 600。必须将该目录和主密钥一同备份，不能只复制密文。API 不回传完整 Key。清除 Cookie 会失去原空间访问凭据，当前没有账户找回功能。

默认接口域名列表见 `src/main/resources/application.properties`。若使用其他兼容服务，可在 `.env` 设置逗号分隔的 `PROVIDER_ALLOWED_HOSTS`（替换整份列表），重启后生效；只允许 HTTPS 和标准端口。公网访问需配置 HTTPS；未启用 TLS 的 HTTP 入口只适合可信网络或 SSH 隧道。

如需提供**服务器共享模型**，部署者可选编辑 `.env`：

```dotenv
WORKBENCH_MODE=live
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=your-server-only-key
LIVE_ACCESS_TOKEN=your-random-access-token-at-least-24-characters
```

共享模式的访问口令与供应商 API 密钥是两种不同凭据。没有启用个人配置的用户使用共享模型时需要输入访问口令。配置完后执行 `bash deploy/stop.sh` 和 `bash deploy/start.sh`。先做一条受控真实调用再运行带 `--live` 的批量评测。

## 验收、备份与更新

- 检查 `/api/workbench/config` 的模式与 browserValidation。
- 用新的浏览器上下文创建项目，执行一次“交互失败再修复”，应保留 FAILED 和 PASSED 两次尝试。
- 日志位于 `logs/server.log`，浏览器失败日志在 `data/qa/<run-id>/attempt-*/worker.log`。
- 停止服务后备份 `data`；恢复到单一实例时保留原浏览器访问凭据。`.env` 单独安全保存。
- 更新时备份旧 JAR，停止服务，替换新 JAR，启动并执行冒烟测试；保留 `data`。
- 不将服务器地址、SSH 凭据或真实 `.env` 提交到公开仓库。


## AI 工作流部署

图编排版已完成内网 HTTPS 部署及真实模型、RAG 验证。Python/FastAPI、PostgreSQL/pgvector、本地向量模型的安装与启动顺序见 [AI 升级部署](AI-UPGRADE.md)，实测范围见 [真实工作流报告](GRAPH-LIVE-RESULTS.md)。
