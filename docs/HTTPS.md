# 内网 HTTPS

没有域名时，可为固定内网 IPv4 地址签发专用证书，由工作台自身终止 TLS，无需修改共享反向代理。使用 HTTPS 后，原端口只接受 TLS，旧 `http://` 地址不会自动跳转，请更新书签。

## 服务器配置

在已按 DEPLOYMENT.md 安装的用户目录中执行（替换为实际内网地址）：

```bash
bash deploy/prepare-local-tls.sh PRIVATE_IPV4
# 在 .env 中设置 WORKBENCH_TLS=true
bash deploy/stop.sh
bash deploy/start.sh
```

脚本创建专用 CA、180 天服务器证书和 PKCS12 密钥库。CA 有效期为 5 年，配置限定的 IP 名称约束、DNS 名称约束以及禁止下级 CA 的约束。`tls` 目录权限为 700，文件为 600；该目录全部排除在 Git 之外。私钥、密码文件和密钥库仅留在服务器，只有 `ca.crt` 可分发给访问者。

TLS 使用 Spring Boot 的原生服务器配置，启用 TLS 1.2/1.3。参考：[Spring Boot 3.5 HTTPS](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)、[OpenSSL 证书扩展](https://docs.openssl.org/1.1.1/man5/x509v3_config/)。

## 客户端信任

此证书不由公共 CA 签发。未安装信任证书的设备仍会显示证书警告；不以跳过警告作为正常使用步骤。先通过可信文件传输获得 `ca.crt`，核对服务器输出的 SHA-256 证书指纹，再由设备使用者导入信任。

Windows 上将证书另存为 `.crt` 文件，双击 → 安装证书 → 当前用户 → 将所有证书放入下列存储 → 受信任的根证书颁发机构 → 确认。重新启动使用系统证书库的浏览器或桌面应用，再访问 HTTPS 地址。Firefox 若不使用系统证书库，需要在其证书设置中单独导入。此操作影响当前用户的证书信任，仅在确认这是本人工作台证书后执行。

工作台不会自动修改客户端信任库。移除时在 Windows 的当前用户证书管理中找到 `Agent Workbench Private CA`，核对指纹后删除。

同一主机从 HTTP 切换为 HTTPS 后，工作台沿用浏览器中原有的空间凭据，并升级 Cookie 为 Secure；不要清除 Cookie，否则会失去原空间访问凭据。

## 验证与续期

```bash
openssl x509 -in tls/ca.crt -noout -sha256 -fingerprint
openssl x509 -in tls/server.crt -noout -dates
curl --cacert tls/ca.crt https://PRIVATE_IPV4:PORT/api/workbench/config
```

到期前再次运行 `prepare-local-tls.sh`（相同 IP）并重启服务即可续期，脚本保留原 CA，无需重新导入客户端信任。续期不是定时自动执行，持续运行的实例也需要在到期前续期和重启。启动脚本会拒绝启动已过期证书。备份整个受限 `tls` 目录，并与普通项目文档分开安全保存；若 CA 私钥丢失或泄露，需重新签发并更新访问设备的信任。

需要回到 HTTP 时，在 `.env` 将 `WORKBENCH_TLS` 设为 `false` 后重启；已升级为 Secure 的 Cookie 不会通过 HTTP 发送，因此日常使用应保持 HTTPS。
