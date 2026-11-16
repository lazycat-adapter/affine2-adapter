# 本地验证记录

日期：2026-11-16。目标平台：linux/amd64。未修改 lazycat-action。

| 项目 | 验证对象 |
| --- | --- |
| AFFiNE | v0.27.4，Git b4c8548c09da21b2898443559a5b846f0ccf5dd8 |
| AFFiNE 镜像 | sha256:c312116a134184947d98749c8a8e29f4e3bc97f4f2a51c9a3497f9baea2eec2b |
| Redis | 7.4.12，固定 amd64 摘要 |
| PostgreSQL | 16.16，pgvector/pgvector:pg16，固定 amd64 摘要 |
| Docker | 29.4.0，兼容 containerd image store 的 manifest ID |
| 执行器 | 未修改的 lazycat-action v1.9.0，远程 v1 指向同一提交 |

通过的检查：

- 17 项 Python 行为测试、3 项 Node 配置测试；工作流通过 actionlint。
- 官方镜像真实初始化数据库、创建管理员、登录、创建工作区。
- 通过真实 Socket.IO / Yjs 协议写入文档及白板形状，第二客户端收到更新。
- 真实 multipart 附件上传、读取及内容校验。
- 使用测试提供方完成 OIDC 签名、issuer/audience、PKCE 和回调登录。
- 三个容器重建后，账号、工作区、文档、白板和附件保留。
- 通过管理员 API 保存过期域名和 OIDC 凭据后重启，部署值正确刷新；
  管理员名称和自定义 OIDC claim_name 保留。
- Docker 创建返回失败但已创建资源、资源删除超时、归属检查失败及外部卷
  保护均有失败路径测试；真实验收后本轮容器、数据卷和网络均已清理。
- 转存前后无标签/空标签差异可兼容，真实运行设置或文件系统变化仍拒绝。
- 缺持久化映射、错误启动命令、错误数据库、过低系统版本及标签移动均拒绝。
- 未修改的真实执行器只读检查选中 v0.27.4，生成 0.25.7→0.27.4 提交区间日志。
- 使用真实执行器的 Manifest 编辑器验证三个服务的来源注释可被本适配器读取。
- 本地生成 tar-format LPK，检查包名、版本、512×512 图标、三个服务、动态域名、
  OIDC 回调及 content.tar；只包含生产启动脚本，不包含测试提供方或测试账号。

边界：本机没有开发者 CLI 登录，因此本地 LPK 格式检查采用隔离的临时构建配置，
其镜像为已测试的上游固定摘要，**不是商店提交包**。生产构建脚本没有放宽检查，
在官方镜像转存完成前会拒绝打包。真实镜像转存、开发者权限与送审由 GitHub
Actions 中的 LZC_API_TOKEN 完成；此记录不声称已向商店提交审核，也未在用户
微服上安装或验证真实生产 OIDC。

## 重现

```bash
python3 -B -m unittest discover -s tests -v
node --test tests/bootstrap.test.cjs
python3 -B scripts/verify_latest.py --tag v0.27.4
lazycat-action run --operation check --config lazycat-action.yml --dry-run
```

只读检查和本地验收不生成发布状态锁。首次真实工作流成功打包/提交时由通用
执行器生成并提交 `.lazycat-action.lock.yml`，不人工伪造状态。
