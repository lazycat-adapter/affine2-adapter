# AFFiNE → 懒猫微服

监控 [AFFiNE](https://github.com/toeverything/AFFiNE) 正式稳定 Git 标签，将
官方服务端镜像适配为 `cloud.lazycat.app.affine2`，自动生成 LPK 并提交懒猫
官方应用商店审核。通用执行器固定引用
[`wcaqrl/lazycat-action@v1`](https://github.com/wcaqrl/lazycat-action)。

需要懒猫系统 **1.5.0+**（tar 格式 LPK v2）。本地验证记录见
[docs/validation.md](docs/validation.md)。

## 首次使用

1. 在本仓库 Settings → Secrets and variables → Actions → Repository secrets
   配置 **`LZC_API_TOKEN`**，使用下划线；首次送审前，开发者平台须已有
   `cloud.lazycat.app.affine2` 应用记录，且对应账号是其开发者或协作者。
2. 打开 Actions → **Update AFFiNE for LazyCat** → **Run workflow**。
3. 保留 `dry-run` 勾选，只检查更新；同时勾选 `verify-image` 可运行真实容器测试。
4. 取消 `dry-run` 勾选，才会转存镜像、验证、打包并提交审核。

Push 仅检查，不送审。定时任务每六小时自动检查并发布，通常在北京时间
02:17 / 08:17 / 14:17 / 20:17 执行，GitHub 可能延迟；不需要
`LAZYCAT_AUTO_PUBLISH`。新包以 `0.27.5` 为版本基线，首次正式打包时由执行器
分配下一版本并生成 `.lazycat-action.lock.yml`。旧包的审核状态保存在 Git 历史中。

## 版本和镜像

- 只选择 `v数字.数字.数字` 稳定标签，排除 Canary、Beta、RC，不跟踪开发分支。
- Git 标签 `v0.27.4` 对应 `ghcr.io/toeverything/affine:0.27.4`。打包前再次
  确认其 GitHub Release 已发布且不是预发布版本。
- 使用 `{source_version}` 获取上游镜像；重新提交被拒绝版本时，LPK 的补丁
  版本可能递增，不能用它寻找上游镜像。
- AFFiNE、Redis 7.4、PostgreSQL 16/pgvector 共三个镜像，均针对 `linux/amd64`。
  数据库和 Redis 固定摘要，升级依赖需要单独修改、测试，不跟随浮动标签更新。
- 当前 executor 的 `command` 准备模式不能同时绑定多个镜像。本项目采用其
  现有 `images` 模式；官方转存后，`lzc-build.yml` 执行真实运行测试，通过后
  才允许打包。

GitHub 元数据读取依赖 `lazycat-action >= v1.10.0`。Runner 自动提供的
`GITHUB_TOKEN` 由执行器保管，适配脚本通过受限的本机只读通道查询当前上游仓库；
首次升级的 `v0.25.7` 基线通过 Git 查询提交号，不再请求旧 Release API。
可信的独立验证步骤显式使用同一自动 Token，不需要另配 GitHub PAT。
共享模块对限流和暂时错误作有界重试，不能把权限错误当成限流忽略。

镜像转存依赖 `lazycat-action >= v1.10.1` 的进度与超时支持。本仓库每张镜像
总上限为 30 分钟，连续 10 分钟没有分层进展则失败；转存日志每 15 秒显示状态。
所有分层完成后继续等待官方服务返回最终镜像地址。运行配置校验兼容 Docker
API 1.48/1.54 对空 `User`、`WorkingDir` 的不同表示，实际配置和分层变化仍拒绝。

## 数据与登录

本适配器的首次新版按全新安装设计，**不读取或迁移旧版 0.25.7 的目录**。
旧目录不自动删除。后续由本适配器产生的数据仍然持久保存：

| 内容 | 懒猫应用持久化目录 |
| --- | --- |
| 附件 | `/lzcapp/var/affine/storage` |
| 配置和密钥 | `/lzcapp/var/affine/config` |
| PostgreSQL | `/lzcapp/var/affine/postgres` |
| Redis | `/lzcapp/var/affine/redis` |

首次访问按照向导创建管理员。应用原生支持懒猫 OIDC，回调地址为
`/oauth/callback`；外部域名使用安装时的 `.S.AppDomain`。管理员账户和懒猫
账户是否绑定取决于 AFFiNE 的账号规则，首次创建的管理员账户应保留。
本版本以懒猫内网页使用为验证范围，不宣称原生客户端或匿名分享已适配。

每次启动更新动态域名和 OIDC 凭据；自定义 OIDC 声明映射、SMTP、额度等用户设置保留。AI、邮件需要
自行配置；Indexer 关闭，不额外部署搜索服务。数据库端口不向宿主机发布。
正式部署不设置测试账号或测试 OIDC 服务。

## 验证与发布边界

```bash
cd /home/www/affine-adapter
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -B -m unittest discover -s tests -v
node --test tests/bootstrap.test.cjs
.venv/bin/python -B scripts/verify_latest.py --tag v0.27.4
```

最后一条需要 Docker，会启动有内存/CPU 限制的临时容器，验证首次初始化、
管理员登录、真实工作区、Yjs 文档与白板、双客户端同步、附件读写、OIDC
签名/PKCE 回调及三个容器重建后的持久化；始终清理本轮创建的容器与数据卷。
它只读取上游镜像，不转存、不打包、不送审。报告在 `.lazycat-action/` 中。

正式打包使用 `lzc-cli project build`，必须先通过通用工作流完成镜像转存。
打包脚本拒绝上游占位镜像、缺失的来源摘要、不一致的转存内容或测试失败。
本地未完成官方转存的检出版本不能直接作为应用商店提交包。

通用执行器记录已处理的源版本与审核状态，拒绝后不会定时重复提交同一源版本；
修复后手动使用 `retry-rejected`。更高上游版本可以替代较旧的待审核版本。
不要伪造或删除状态锁来强制发布。

更新日志来自前一源提交至当前提交之间的 Git log，最多 60 条近期非合并提交，
不抓取整个 CHANGELOG 或 Release 正文。语言处理沿用官方平台和通用执行器。
GitHub Release 由通用工作流独立发布，只上传版本化 `.lpk`；其失败不阻断送审。

## 上游资料

- [部署文档](https://docs.affine.pro/self-host-affine/install/docker-compose-recommended)
- [配置文档](https://docs.affine.pro/self-host-affine/install/configuration)
- [OIDC 文档](https://docs.affine.pro/self-host-affine/administer/oauth-2-0)
- [上游许可证](https://github.com/toeverything/AFFiNE/blob/v0.27.4/LICENSE)

上游前端与服务端采用不同许可；本适配器沿用官方镜像，不改变其授权、订阅或
商业功能限制。首次图标提取自该包原商店 LPK（512×512 PNG）。
