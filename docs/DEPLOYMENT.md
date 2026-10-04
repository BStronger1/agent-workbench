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
  data/                   # 项目快照与验收截图
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

编辑 `.env`：

```dotenv
WORKBENCH_MODE=live
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=your-server-only-key
LIVE_ACCESS_TOKEN=your-random-access-token-at-least-24-characters
```

访问口令与供应商 API 密钥是两种不同凭据。用户页面仅输入访问口令。配置完后执行 `bash deploy/stop.sh` 和 `bash deploy/start.sh`。先做一条受控真实调用再运行带 `--live` 的批量评测。

## 验收、备份与更新

- 检查 `/api/workbench/config` 的模式与 browserValidation。
- 用新的浏览器上下文创建项目，执行一次“交互失败再修复”，应保留 FAILED 和 PASSED 两次尝试。
- 日志位于 `logs/server.log`，浏览器失败日志在 `data/qa/<run-id>/attempt-*/worker.log`。
- 停止服务后备份 `data`；恢复到单一实例时保留原浏览器访问凭据。`.env` 单独安全保存。
- 更新时备份旧 JAR，停止服务，替换新 JAR，启动并执行冒烟测试；保留 `data`。
- 不将服务器地址、SSH 凭据或真实 `.env` 提交到公开仓库。
