# DSP Git Sync

我想做的事情其实很简单：在 Mac 上退出《戴森球计划》，换到 Windows 后，接着刚才的进度玩。存档、蓝图、Mod 都一起带过去，最好还是点 Steam 原来的“开始游戏”，不用额外记一套操作。

这个工具就是为这件事做的。源码公开，**游戏数据放在我自己的私有 GitLab 仓库里**。

**这是双向交接：两端均在启动前接收、退出后上传。**`init-download` 只表示第二台设备首次以远端为起点，不会把它变成只下载的客户端。当前为 [v0.1.0 预览版](https://github.com/Anormallylee/dsp-git-sync/releases/tag/v0.1.0)。

## 我为什么折腾这个

我平时用 MacBook Pro，通过 CrossOver 跑 Steam 版《戴森球计划》。工厂规模逐渐变大以后，我遇到了明显卡顿，甚至画面停住、音乐还在播放的情况。后来拿一台 Windows 电脑试了同一个存档，体感顺畅了不少，于是又多了一个需求：两台电脑之间怎么接着玩？

一开始我考虑过 Google Drive，后来因为那台 Windows 不是日常个人用机，不想把自己的整个网盘带过去，就换成了 OneDrive。

但真正麻烦的不是“文件能不能传过去”，而是整套流程：启动前到底有没有拿到最新进度？退出后是不是已经传完？刚下载的新蓝图会不会被另一台电脑覆盖？Mod 的配置和存档附属文件能不能一起走？

最初的方案把存档、蓝图和 Mod 打成完整 ZIP 快照。能用，但一次大约 596 MiB，压缩、上传、检查都要等。后来改成文件级增量，没变的蓝图和 Mod 不用再传了，可是我的**单个存档就有约 223 MiB**。存档一变，还是要重新传整个文件。

我当时的想法是：既然都做了启动器，为什么不直接让 Git 处理版本和差分？于是拿本地两份真实存档，建了一个私有测试仓库试了一遍。

结果确实有用，但又踩到了 GitLab 服务端的配置坑。

## 实际测到了什么

下面是用同一路径依次替换几份真实存档得到的**单文件测试**，不是整个存档目录的同步计时，也不代表其他存档或网络都能达到同样效果。

| 测试 | 数据量 / 耗时 |
|---|---:|
| 原始存档 | 约 223 MiB |
| 单个存档 ZIP 压缩（deflate level 1） | 约 98 MiB |
| Git 首次上传基线 | 95.16 MiB |
| 相邻两份存档的 Git 差分上传 | **4.46 MiB** |
| 另一份存档的差分上传 | **4.17 MiB** |
| GitLab 原配置下，同一增量下载 | 97.96 MiB / 83.7 秒 |
| 修改 GitLab 服务配置后，再下载同一增量 | **4.48 MiB / 12.6 秒** |

下载还原后，我也检查了 SHA-256，和源文件完全一致。这里的上传、下载数据量来自 Git 的传输报告，不包含全部 HTTP/TLS 协议开销。

我的结论是：**这些存档很适合 Git 差分，但不能只看上传快了，就认定下载也会一样快。服务端如何打包同样重要。**

## 不再给游戏数据打 ZIP

新流程直接保存原始目录和文件：

```text
private-data-repository / sync-v1 branch
├── .gitattributes
├── manifest.json
└── files
    ├── data
    │   ├── Save
    │   ├── Blueprint
    │   └── Blueprints
    └── game
        ├── BepInEx
        ├── winhttp.dll
        ├── doorstop_config.ini
        └── .doorstop_version
```

Git 自己处理对象、压缩和差分传输；没有每次手动打 ZIP、上传 ZIP、再解 ZIP 的环节，也不用经过 ZIP 文件名编码这一层。程序在校验与导入时仍会使用临时目录；这是为了保护现有进度，不是把游戏数据重新压成一个同步包。

中文路径按 UTF-8 处理，清单中的 Unicode 名称统一为 NFC，并检查 Windows 不接受的文件名、大小写冲突及名称归一化后的重复。Mac 上合法的文件名不一定能原样落到 Windows，所以发现这种情况会报错，不会悄悄改名。

旧同步系统留下的 ZIP 可能需要在**首次迁移**时读取一次。工具本身的安装压缩包和游戏数据的同步格式是两回事。

## 我踩到的 GitLab 配置坑

我的测试环境是 **GitLab CE 18.11.1**，运行在 Docker 中。

普通 Git 的 `core.bigFileThreshold` 默认是 512 MiB。超过配置阈值的文件会做普通压缩，但不尝试跨版本差分。GitLab 的 Gitaly 下载进程在我这里却带着 `core.bigFileThreshold=50m`。

所以我在本机上传时只传了 4.46 MiB，但另一端下载时，服务器又发回了接近 98 MiB。

### 只改仓库，没有生效

我先只对那个私有仓库设置了 `core.bigFileThreshold=512m`，重新测试，结果没有改善。直接检查进程后才确认：Gitaly 启动 Git 时传入的 50m 覆盖了仓库设置。

这一步很容易产生误判：`git config --local --get core.bigFileThreshold` 能读到 512m，并不意味着 GitLab 下载进程实际用了它。

### 修改服务配置后，实测生效

我备份了 `/etc/gitlab/gitlab.rb`，在 **Gitaly 服务级配置**里设置：

```ruby
gitaly['configuration'] = {
  git: {
    config: [
      { key: 'core.bigFileThreshold', value: '512m' }
    ]
  }
}
```

**如果已有 `gitaly['configuration']`、`git` 或 `config` 配置，要把这一项合并进去，保留其他设置，不要直接用上面的片段覆盖原配置。**也要检查 Docker 的 `GITLAB_OMNIBUS_CONFIG` 是否已经包含相关配置。

然后重新配置。我的容器名是 `gitlab`：

```sh
docker exec gitlab gitlab-ctl reconfigure
docker exec gitlab gitlab-ctl status
```

直接安装 GitLab Linux package 的环境，使用 `sudo gitlab-ctl reconfigure`。应用配置可能重载或重启服务，应在没有其他任务受影响的时候操作。

生成的 Gitaly 配置通常在 `/var/opt/gitlab/gitaly/config.toml`，可以检查是否包含设置，但**最终要以真实 fetch 的传输量和文件校验为准**。我这里重测从 97.96 MiB 降到了 4.48 MiB。

需要注意：

- 这是服务级配置，影响该 Gitaly 服务管理的仓库，并非只影响游戏存档仓库。
- 提高阈值可能增加服务器的 CPU 和内存消耗。512m 是我这次测试的值，不是所有环境都应照抄的推荐值。
- 私有仓库和 GitLab 实例本身也必须允许这么大的普通 Git 文件；差分包小，不代表原始文件小。
- 不要把这些存档切到 Git LFS。LFS 对象传输不是这里验证过的普通 Git 跨版本差分流程。
- 不要直接修改生成的 `config.toml` 当作持久配置，下一次 reconfigure 可能覆盖它。

官方文档也有一处值得留意：配置参考将该参数列为 Gitaly 自行管理、不能通过 `git.config` 覆盖；故障排查页又提供了服务级修改的示例。**我只能确认上面的方法在这次 18.11.1 部署中实测有效，不把它当作所有版本的保证。**

参考：[Git 大文件阈值](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corebigFileThreshold)、[Gitaly 管理的配置](https://docs.gitlab.com/administration/gitaly/configure_gitaly/#git-configuration-set-by-gitaly)、[GitLab 故障排查示例](https://docs.gitlab.com/administration/gitaly/troubleshooting/#error-fatal-deflate-error-0-when-downloading-repository-as-zip-file)。

### 首次上传还要看公网入口限制

完整目录的首次初始化又让我遇到一个问题：经公网地址 push 返回了 **HTTP 413**。差分测试只有几 MiB，首次基线却可能很大，这两件事不能混为一谈。

如果 GitLab 前面还有 Cloudflare 或其他反向代理，需要同时检查请求体大小限制。提高 `core.bigFileThreshold` 只影响 Git 是否尝试差分，**不会解除代理的上传上限**。可以通过已有的直连或 SSH 入口初始化；服务部署在同一台机器时，也可以通过可信本机入口导入同一个提交，再从正常远端核验。不要为了重试而强推、删基线，或把访问令牌写进 URL。

后续差分通常小得多，但新增大量 Mod、多个存档同时变化等情况仍可能产生大包。遇到限制应保留未上传状态并解决连接问题，不能把失败标记为同步成功。

如果 GitLab 就运行在 Mac 本机，Mac 的 `config.json` 可额外设置 `git_local_push_url`，指向**同一仓库**的本机回环入口，例如 `http://127.0.0.1:8081/YOUR-USER/YOUR-PRIVATE-DATA-REPO.git`。此设置只改变上传入口；启动前仍从常规 `git_remote` 检查和下载。工具从本机 Git 凭据管理器读取常规地址的授权，仅在该次上传的进程内用于本机入口，不写入配置或公开仓库。Windows 不应照搬 Mac 的回环地址；它需要能从 Windows 访问的 GitLab 入口。

这次实际游玩后，多个大存档一同变化，公网 push 再次中断并阻止下次启动。未上传提交和本地存档都保留着；我经本机入口补传原提交，确认远端与本地一致，再把 Mac 的上传入口固定到本机。这个改动解决的是当前 Mac 的上传路径；其他设备若也遇到大包限制，需要为它们解决自己的连接方式。

参考：[Cloudflare HTTP 413 与上传大小限制](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/)。

## 现在的使用流程

1. 点 Steam 原来的“开始游戏”。包装程序先让 Python 工具检查私有 Git 仓库。
2. 工具核对上次同步基线、检查冲突、验证哈希，给需要替换的文件留备份，然后启动游戏。
3. 正常退出游戏后，有变化则提交最终的存档、蓝图和 Mod 状态，再 push；没有变化则确认当前状态，不创建空提交。
4. 等同步窗口显示完成，再换另一台电脑。

游戏目录本身不是 Git 工作区；Git 缓存在另一个目录中。程序不强推，也不尝试合并二进制存档。相同存档组或 Mod 在两边都变了，会停下来，保留数据等待处理。

独立新增的蓝图可以合并；同名文本蓝图双方修改，会保留本地冲突副本。上传失败、确认丢失和导入中断都有状态记录，不能靠删掉状态文件来假装同步完成。

这不是多人同时玩的方案。**两台设备顺序交接，等同步完成再切换。**

目前启动前和退出后都需要访问 Git 远端，没有自动离线放行模式。如果 GitLab 部署在日常用的电脑上，那台电脑休眠、关机或 Docker 停止后，另一台设备就无法完成同步检查；自托管服务需要保持可达。

## 安装

当前版本面向已安装 BepInEx 和 Doorstop 的游戏，会检查加载器文件，尚未提供纯原版游戏模式。需要 Python 3.10+、Git，以及两端已经配置好的私有仓库访问凭据。凭据放 Git Credential Manager、系统钥匙串或 SSH 配置，不能写进远端 URL、config.json 或公开仓库。

- **Windows Steam：**参考 [Windows 安装与升级说明](WINDOWS-HANDOFF.md)。
- **macOS + CrossOver：**把工具放到固定本地目录，根据 `config.macos.example.json` 创建本机 `config.json`，填写游戏、存档、备份、Git 和容器路径。初次源端只在远端数据分支为空时执行 `python launcher.py init-source`；其他设备先备份、检查本地变化，再执行 `init-download`。随后执行 `python configure_macos.py`，按输出设置 Steam 启动选项。
- 工具也可以完全不经过 ZIP：`git clone https://github.com/Anormallylee/dsp-git-sync.git` 获取源码，再从 Releases 下载单独的 `SteamSync.exe` 放进工具目录。也可以安装 MinGW-w64 后运行 `./build_wrapper.sh` 自行编译。它是本项目的包装程序，不是游戏文件。

**首次 `init-download` 按远端内容初始化，会备份并替换有差异的本地同步文件，不进行已有基线上的三方合并。**请先检查本机独有的蓝图、Mod 和存档；不要把这个命令当成无改动的查看操作。后续正常交接才使用已有基线做冲突检查。

Mac 后台进程每秒检查一次本地启动请求，不持续轮询远端。Windows 由包装程序按需启动 Python worker。

从旧系统迁移时，要先确认旧系统的最新状态并保留本地新增内容。不要只按文件修改时间猜哪台电脑更新，也不要让旧、新两个同步工具同时上传。

## 同步范围与数据保留

同步：`Save/*.dsv`、`*.moddsv`、`Blueprint/`、`Blueprints/`、BepInEx 的 core/plugins/patchers/config，以及 Doorstop 加载文件。

存档范围排除 `Codex-batched-dismantle-test`、`_autosave_errored` 和 `_autosave_0` 至 `_autosave_3` 的 `.dsv` / `.moddsv` 文件，保留 `_lastexit_` 退出存档与手动存档。排除项仅留在各设备本地，不参与下载、导入、冲突检测或后续上传；旧远端仍包含这些文件时也会跳过。下一次成功上传会从最新 Git 状态移除已跟踪的排除项，不删除本地文件或重写历史。两端同步工具都应升级，否则旧客户端仍会同步这些文件。

同步范围不含游戏主程序、游戏资源、游戏显示设置、系统凭据存储和同步工具的本机配置。**Mod 配置在同步范围内，工具不会自动识别其中的敏感字段，数据仓库应保持私有。**除单独列入范围的 `.doorstop_version` 外，扫描目录中的隐藏名称项及旧诊断 StutterProbe Mod 会被排除。远端内容必须通过完整清单、路径、文件类型和 SHA-256 校验。

备份和远端提交历史会保留。下载使用 Git protocol v2 的 `blob:none` 过滤：保留提交和目录元数据用于同步基线、祖先关系及冲突检查，仅按对象 ID 获取最新状态所需且本地缺少的文件内容，跳过中间存档版本。已有完整缓存可直接迁移并复用对象，不需要删除缓存或重写远端历史。服务器必须支持 filtered fetch，否则启动前明确停止，禁止静默回退为完整历史下载。私有 GitLab 可由管理员启用 `uploadpack.allowFilter=true`；客户端要求 Git 2.50 或更新版本，以可靠禁用隐式对象下载；旧版本会明确停止。Windows 和 macOS 都需检查 `git --version`。

先验证最新 manifest 和属性，再核对文件集及实际大小，导入时逐文件验证 SHA-256。manifest 限制为 32 MiB；Git 对象 ID 请求在下载前不提供大小，因此大小限制在对象接收后、解析前执行。缓存检查、导入及整理禁用隐式下载；整理不会为了压缩缓存获取历史存档。超时限制不变。备份及已经下载的旧对象仍会占空间，清理需要单独制定保留策略。

**这个公开仓库只放工具源码。**我用 GitHub 托管源码，用私有 GitLab 放实际数据。[GitHub 普通 Git 仓库会阻止超过 100 MiB 的文件](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)，不适合直接放这些未拆分的存档；不要把本项目的 GitHub 地址当作数据远端。

## 真实设备验证（2026-09-29）

这次已经完成 Windows 和 Mac + CrossOver 的真实 Steam 交接：

- Windows 从 Steam 启动前完成接收检查，正常保存退出后自动上传；另一端核对 GitLab 提交一致。
- Mac 随后从 Steam 启动，接收 Windows 的进度，游玩并正常退出后自动上传；本地文件、同步基线与远端提交一致，无待上传状态和错误日志。
- 正式初始化的 749 个文件、约 1.39 GiB 原始数据，曾使用全新缓存经公网下载并逐文件验证 SHA-256。原始体积不等于网络传输量。

这次 Mac 退出后，从检测到游戏退出到显示同步完成约 **73 秒**，期间包含本地 Git 缓存整理。这是一次完整流程计时，不能与前面单文件下载的 12.6 秒直接比较，也不是以后每次同步的耗时保证。

这些结果只覆盖这次设备、游戏和 Mod 组合，不代表所有配置都已验证。首次全量同步仍可能较慢，后续传输量取决于变化内容及 Git 的差分效果。

## 开发与验证

```sh
python -m unittest discover -s tests -v
```

测试使用人工构造的小文件和临时裸 Git 仓库，覆盖传输、蓝图合并、删除、冲突、上传恢复、内容篡改与回滚。跨平台 CI 和这些测试不能代替真实设备上的 Steam 启动、保存、退出验证。

MIT License。欢迎反馈可复现的问题；提交日志前请移除自己的账号、路径、私有仓库地址和凭据。
