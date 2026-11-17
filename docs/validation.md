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


## 2026-11-17：GitHub 元数据读取修复

共享执行器候选版 `v1.10.0-rc.1` 的 [Runner 只读验证](https://github.com/wcaqrl/affine-adapter/actions/runs/44003686412)
通过，仍选择正式 `v0.27.4`。首次基线提交号改由 Git 读取，当前 Release 通过执行器的
受限本机通道鉴权读取，不再匿名请求旧 Release API。独立验证使用 Runner 自动 Token，
不需要开发者额外配置 GitHub PAT。构建阶段关闭持久化 Git 凭据，受保护变量在构建配置
展开前移除。24 项 Python 测试、3 项 Node 测试和工作流校验通过。
本次为读取/鉴权修复，没有重新执行上一节的完整容器验收，也没有手动触发真实送审。

## 2026-11-17：Docker 空字段兼容

运行 44005457051 在拉取官方 AFFiNE 镜像后因 `User` 缺省与空字符串误判失败。
仅对 `User`、`WorkingDir` 的缺省/null/空串作等价比较；非空值、错误类型、
命令、环境、镜像摘要及文件分层继续严格校验。27 项 Python、3 项 Node 测试通过。
本机三个真实固定镜像分别用 API 1.48、1.54 检查，六项均通过，未启动本地容器。

[Runner 容器验收 44009542621](https://github.com/wcaqrl/affine-adapter/actions/runs/44009542621)
通过：初始化、管理员登录、工作区、同步、附件、OIDC、持久化、配置刷新。
该运行保持 dry-run，不向商店送审。正式转存、打包与送审另行验证。

## 2026-11-17：正式交付验证通过

[运行 44010886589](https://github.com/wcaqrl/affine-adapter/actions/runs/44010886589)
使用 `lazycat-action v1.10.1`，三个镜像均输出逐层进度、耗时及最终官方地址，
每镜像总上限 30 分钟、无进度上限 10 分钟。官方转存镜像通过完整运行验收，
LPK 构建、提交审核、独立 GitHub Release 四个任务全部成功。

- 包名 `cloud.lazycat.app.affine`，版本 `0.27.4`，LPK 大小 49152 字节。
- SHA256：`e9ba3458988b720cefddd49c01900b2f78474ca67040b9f01edcc94eec59e80a`。
- 商店审核编号 `23359`，提交时间 2026-11-17 11:35:54（北京时间），查询时待审核。
- [Release 下载](https://github.com/wcaqrl/affine-adapter/releases/tag/v0.27.4)
  只有一个手动上传资产 `.lpk`，其 GitHub 资产 SHA256 与商店记录一致。
- 自动提交的版本、官方镜像 Manifest 和审核状态锁已同步到本机，不手工改写锁。
