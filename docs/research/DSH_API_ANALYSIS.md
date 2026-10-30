# DSH 插件机制与 Agent/Session API 审计（DSH_API_ANALYSIS）

> 审计对象：当前机器上真实安装并真实运行的 DeepSeek Harness（DSH）。
> 审计方式：**只读**。未修改 DSH 安装目录、未修改任何 profile、未安装/卸载任何插件。
> 审计时间：依据本次会话的安装快照（会话时间 2026-10-30）。
> 对应任务书：`D:\桌面\new_idea\DSH Voice Assistant — 完整工程开发任务书.md` 第 207–230 行「任务 C：分析 DSH 插件机制」。

---

## 0. 路径约定与证据等级（必读）

本文件所有证据均标注真实路径与行号。为可读性，先约定 6 个路径前缀（均为绝对路径的缩写，不是猜测路径）：

| 前缀 | 绝对路径 | 含义 |
|---|---|---|
| `P\` | `C:\Users\lenovo\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\node_modules\@deepseek-ai\` | npm 全局安装的 DSH 依赖闭包（`C:\Users\lenovo\.dsh\profiles\node_modules\@deepseek-ai\` 是指向它的 Junction）。239 个包，**带 `lib/types/**/*.d.ts` 与 README**，是本审计的一级证据。 |
| `A:` | `D:\DeepSeekHarness\resources\app.asar` | **当前正在运行的 Host**（桌面版）的 asar 归档。虚拟路径，普通文件系统/ripgrep/node 无法直接读；本次先用自写的只读 asar 读取器（按 JSON 头偏移读单文件，不解包、不写入）读取。**归档内只有 `lib/*.js`，没有 `.d.ts`**。 |
| `R\` | `D:\桌面\new_idea\.cache\dsh-asar\dsh\node_modules\@deepseek-ai\` | 上级代理把 `app.asar` **完整解包**到工作区后的只读镜像，即 **0.2.1-rc.3 的真实运行时代码**（`lib/*.js` + 保留的 JSDoc，**无 `.d.ts`**）。**本文件对「运行中的 Host」的行号引用一律用 `R\`**，它是 `A:` 的可检索等价物。 |
| `Q\` | `C:\Users\lenovo\.dsh\profiles\desktop\node_modules\` | desktop profile 内真实安装的第三方插件（`dsh-video-skin@0.1.1`、`dsh-channel-wechat@0.2.6`）。 |
| `J\` | `C:\Users\lenovo\.dsh\profiles\jarvis\` | jarvis profile（只有 profile 配置，无第三方插件）。 |
| `W\` | `D:\桌面\new_idea\` | 本工程工作区。 |

证据等级标记：

- **[T]** 已安装包的 TypeScript 类型声明（最强，逐行可核）。
- **[R]** 包内 `README.md`（官方文档，随包发布）。
- **[S]** 真实插件源码（第三方插件或 DSH 自身 `lib/*.js` 实现）。
- **[I]** 运行时只读 Inspect（`cordis_inspect_*`，反映**当前运行中的 Host**）。
- **[?]** 无法确认 → 一律写「待验证」，不做推断性断言。

> **审计纪律说明**：`P\` 下的 README 内部链接（例如 `P\dsh-agent\README.md:67` 指向 `../../../docs/subsystems/core.md`）指向源码 checkout 的 `docs/`，**安装包内并不包含该目录**（对照 `P\dsh-agent\package.json` 的 `files` 与包内文件列表）。因此：
> 1. 同一版本内，README 与 `.d.ts` 冲突时以 `.d.ts` 为准；
> 2. 跨版本比较时，以 `R\`（0.2.1-rc.3 实现）为准（理由见 §1.1、§1.3）；
> 3. README 只用于「能力边界/设计意图」这类 `.d.ts` 不表达的陈述（例如 §1.2 的「不支持流式识别与语音合成」），此时会明确标注来源是 README。

---

## 1. 两个安装的事实分歧（本次审计最重要的前置结论）

### 1.1 磁盘上有两套 DSH，版本不同

- **结论**：机器上存在两套 DSH；**正在运行的是桌面版 0.2.1-rc.3**，而 npm 全局安装的是 0.1.5-rc.x。任务书里「已安装 DSH 版本 0.1.5-rc.2」只对 npm 那套成立，**不是**当前 Host 的真实版本。
- **证据**：
  - npm meta 包版本 `0.1.5-rc.1`：`C:\Users\lenovo\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\package.json` 的 `"version"`。
  - 其子包版本 `0.1.5-rc.2`：`P\dsh-client-ui-renderer\package.json`（`"version": "0.1.5-rc.2"`）。
  - 运行中的桌面版：`R\..\..\package.json` → `"name": "@deepseek-ai/dsh-desktop-runtime"`、`"version": "0.2.1-rc.3"`（等价 asar 路径 `A:/dsh/package.json`）；`R\dsh-agent\package.json` → `0.2.1-rc.3`。
  - 进程证据：`Get-Process` 显示 7 个 `DeepSeek Harness` 进程，路径 `D:\DeepSeekHarness\DeepSeek Harness.exe`（**没有** node.exe 承载的 `dsh` CLI）。
  - 环境变量：`DSH_HOME=C:\Users\lenovo\.dsh`、`DSH_PROFILE=desktop`、`DSH_PROFILE_DIR=C:\Users\lenovo\.dsh\profiles\desktop`、`DSH_WEB_URL=http://127.0.0.1:31979`。
  - 包数量差异：`P\` 239 个包；`R\`（=asar）307 个包。
- **对 Voice Assistant 的含义**：
  1. 「按已安装 d.ts 写插件」与「在运行中的桌面上真正生效」**不是同一件事**。本文件对每个关键 API 都在 `P\`（0.1.5 类型）与 `R\`（0.2.1 真实实现）两侧做了交叉核对，凡只在一侧存在的都显式标注。
  2. 结论优先级：`R\`（真正跑起来的那套，`.js` 实现 + JSDoc）> `P\`（可读类型）。两者冲突时以 `R\` 为准，并记录冲突；已发现的第一处冲突见 §11.2（`sessionController.prompt` 的第二个形参在 0.1.5 是 `signal`、在 0.2.1 是 `source`）。
  3. 只有 `P\` 有 `.d.ts`，所以「类型形状」引用 `P\`；「行为/时序」引用 `R\`。两者都给的条目 = 交叉验证通过。
  3. 语音插件若要发布，`engines.dsh` 应写 `>=0.2.0-rc.1`（依据：`Q\dsh-channel-wechat\package.json:25-28` 的 `"engines": { "dsh": ">=0.2.0-rc.1" }`），而不是 0.1.5。

### 1.2 桌面版已内置「实验性语音输入」子系统（必须先看，否则重复造轮子）

- **结论**：运行中的 DSH **已经**内置一套实验性语音输入（STT）子系统，且明确**只做「整段录音转写」**：没有流式识别、没有语音合成、没有唤醒词、没有自动发送。这正是本工程可以切入的空隙，也意味着 STT 层应优先复用而非自建。
- **证据**：
  - 包存在：`R\dsh-experimental-speech-to-text\`、`R\dsh-experimental-speech-to-text-sensevoice\`、`R\dsh-experimental-api-speech-to-text\`、`R\dsh-experimental-client-ui-voice-input\`、`R\dsh-experimental-voice-input-bundle\`（这 5 个包在 `P\`（0.1.5）中**完全不存在**，是 0.2.x 新增）。
  - 服务名：`R\dsh-experimental-speech-to-text\README.md:12` — 「selects named speech recognizers through `ctx.speechToText`」。
  - 能力边界：同文件 `:70` — 「Only complete-recording transcription is supported. Streaming recognition and speech synthesis have no service methods.」
  - UI 边界：`R\dsh-experimental-client-ui-voice-input\README.md:68` — 「No automatic send, always-on microphone, wake word, streaming captions or speech synthesis.」
  - 打包方式（真实 bundle 样例）：`R\dsh-experimental-voice-input-bundle\cordis.patch.yml:1-13`，4 行 `insert`：`speech-to-text` / `speech-to-text-sensevoice` / `api-speech-to-text` / `ui-voice-input`，其中 `dataRoot: !!js dshHomePath('speech-to-text', 'sensevoice')`。
  - 运行时确认：Host Inspect `Service.listService` 的服务目录里存在 `speechToText`（见 §3.9）。
- **对 Voice Assistant 的含义**：
  1. **不要**再实现一套 SenseVoice 整段转写；但也不要把它当成流式 ASR 的替代。它是「点一下、录一段、转一段」的 one-shot 通道，**不提供** continuous capture / partial / endpoint。本工程的常驻唤醒 + 流式 ASR 必须留在 Voice Runtime；`ctx.speechToText` 只作为可选的「按住说话/单段听写」补充入口，或用于把 Runtime 的最终文本送进 DSH 的既有 UI 流程（见 §3.9）。
  2. 本工程的真正增量 = 常驻唤醒 + 流式 ASR + 句子级 TTS + 打断（barge-in）+ 桌宠联动。这四条在 DSH 侧**没有**对应 API（§13 会全部登记为「不存在/待验证」）。
  3. 语音插件与 `dsh-experimental-*` 同属「实验性」，命名与 `engines` 需与之对齐，避免版本互斥。

### 1.3 两版差异核对表（本次已逐条核对的项）

| 项目 | 0.1.5-rc.x（`P\`，有 `.d.ts`） | 0.2.1-rc.3（`R\`，真实运行） | 是否一致 |
|---|---|---|---|
| `ctx.agents` 的 `get/list/roots/create/resume` | `P\dsh-agent\lib\types\index.d.ts:279/287/341/355/362` | `R\dsh-agent\lib\index.js:596/614/623`（+ Registry 的 create/resume） | ✅ 一致 |
| `agent.followup/steer/inject/cancel/whenIdle` | `P\dsh-agent\lib\types\runtime-types.d.ts:157/164/186/192/200/209` | `R\dsh-agent-loop\lib\index.js:800-821`、`:870-875` | ✅ 一致（实现更明确：三方法都是 `send(msg, target, wakeup)` 的薄封装） |
| `cancel(cause,{keepInbox:true})` | `P\dsh-agent\lib\types\runtime-types.d.ts:32-39` | `R\dsh-agent-loop\lib\index.js:815-821` | ✅ 一致 |
| `agent/assistant-stream` 帧 | `P\dsh-agent\lib\types\runtime-types.d.ts:106-137` | `R\dsh-agent-loop\lib\index.js:355-447`、`:1079-1081` | ✅ 一致 |
| `session/event` 发布 | `P\dsh-session\lib\types\index.d.ts:62` | `R\dsh-session\lib\index.js:1587` | ✅ 一致 |
| `sessionController.prompt` 第二形参 | `signal: AbortSignal`（`P\...\index.d.ts:138`） | `source`（`R\...\lib\index.js:925`、`...\commands.js:302`） | ❌ **不一致**（见 §11.2） |
| `ctx.speechToText`（整段 STT） | **不存在**（`P\` 无 speech 包） | 存在（5 个 `dsh-experimental-*` 包 + [I]） | ❌ 0.2.x 专有 |
| `ctx.configForms`（Client 表单服务） | **不存在** | 存在（`Q\dsh-channel-wechat\lib\client.js:1089` 依赖它） | ❌ 0.2.x 专有 |
| HMR 行/包名 | `cordis-plugin-hmr`（`P\cordis-plugin-hmr\README.md`） | Loader 行名 `@deepseek-ai/dsh-hmr`（[I] `include:hmr`） | ⚠️ 名称不同、行为描述一致（实现是否同源待验证） |
|「当前活动会话」API | 无 | 无 | ✅ 一致（**两版都没有**，见 §11.1） |

### 1.4 结论的适用边界（重要）

本文件中的**行为结论**（取消语义、assistant-stream 时序、sentence 边界缺失、无 active-session API）以 `R\`（0.2.1-rc.3）为准；**类型形状**以 `P\` 为准。若未来 DSH 再升级，只需重跑 §14.3 的 `Select-String` 命令即可复核这些行号是否漂移。

### 1.5 已存在的 STT 服务契约（`ctx.speechToText`，0.2.1 实测）

- **结论**：`ctx.speechToText` 是一个可扩展的**整段转录**服务：第三方插件可以 `register(provider)` 注册自己的识别器，也可以 `resolve()/transcribe()` 消费别人的。它**不提供**流式识别、VAD、唤醒词或语音合成。
- **证据（全部来自 `R\dsh-experimental-speech-to-text\lib\index.js`）**：
  - 服务身份：`:6`（`var SpeechToText = class extends Service`）、`:18`（`super(ctx, "speechToText")`）。
  - 配置：`:8-11`（`defaultProvider` 必填且 `volatile`；`language` 默认 `"auto"` 且 `volatile`）。
  - 注册：`:35-51`（`register(provider)`；`:37` 同 id 重复注册**抛错**；返回 `async` 幂等 disposer，`:52-59` 卸载时 abort 并 `allSettled(pending)`）。
  - Provider 契约（从调用点反推，均为硬要求）：`provider.info.id`、`provider.info.languages`（`:135` 校验）、`provider.preparation?.subscribe/prepare/cancel`（`:42`、`:146`、`:156`）、`provider.transcribe({ audio, language }, signal)`（`:185-188`）。
  - 名录/观察：`:64-66`（`listProviders()`）、`:75-80`（`follow(caller)` 异步迭代快照）。
  - 选择与执行：`:163-171`（`resolve(request)`：`providerId`/`language` 缺省回落到 config，返回 `{ provider, audio, language }`）、`:178-198`（`transcribe(spec, signal)`：provider 被替换则抛 `Resolved speech provider is no longer registered`，并把 caller signal 与注册生命周期 `AbortSignal.any` 合并）。
  - 准备：`:143-157`（`prepare(id, options)` / `cancelPreparation(id)`）。
  - 与 Loader/Settings 的耦合：`:20`（`ctx.fiber.entry?.options.id` 拿本行 entry id，供 Settings 定位）、`:21-23`（监听 `loader/volatile-update` 后 `changed()`）。
  - 音频格式（README 声明）：`R\dsh-experimental-speech-to-text\README.md:44` — canonical 16 kHz mono PCM16 WAV，头/长度不一致会被拒绝。
- **对 Voice Assistant 的含义**：
  1. **可复用点**：把本工程的流式 ASR 之外的「一次性转写」能力以 provider 形式注册进 `ctx.speechToText`，可与内置 SenseVoice 并存（不同 id），且能复用它的 GUI 页面与设置。
  2. **不可复用点**：唤醒词、VAD、流式分片、TTS、打断——该服务都没有（README `:70`）。
  3. **风险**：该服务是 `experimental`，且**没有 `.d.ts`**；本工程必须用一个 adapter 隔离它，若上游改签名只改 adapter 一处。
  4. `ctx.fiber.entry` 在 0.2.1 存在（`:20`），但**不在** 0.1.5 的公开 `Fiber` 类型里（§13.2 登记）——又一个「只能用 0.2.x」的证据。

---

## 2. 插件 manifest、入口、package.json 约定与安装/启用

### 2.1 Host 插件入口：模块导出约定（不是 `plugin.json`）

- **结论**：DSH 插件**没有**独立的 `plugin.json` 清单文件；Host 半边的「manifest」就是 npm 包的 ESM 导出 + `package.json` 的 `dsh` 字段。可识别的入口形态有三种：函数插件 `(ctx, config) => ...`、类插件 `new (ctx, config)`、对象插件 `{ apply(ctx, config) }`。真实插件统一采用「具名导出 `name` / `inject` / `Config` / `apply`」。
- **证据**：
  - 三种形态：`P\cordis\lib\types\registry.d.ts:48`（`Plugin<T> = Function | Constructor | Object`），`:71-81`（`Function` 为 `(ctx, config)`，`Constructor` 为 `new (ctx, config)`，`Object` 为 `apply(ctx, config)`）。
  - 元数据字段：`P\cordis\lib\types\registry.d.ts:52-63`（`name` / `Config` / `inject` / `provide` / `intercept`）。
  - 真实对象插件：`Q\dsh-channel-wechat\lib\index.d.ts:18`（`declare const name = "channel-wechat"`）、`:155`（`declare const inject: readonly ["cmdlineArgs","credentials","agents","commands","agentDefaultModel"]`）、`:160`（`declare function apply(ctx: Context, config: Config): void`）。
  - 真实函数插件（无 Config）：`Q\dsh-video-skin\index.js:31`（`export const name = 'video-skin'`）、`:34`（`export const inject = []`）、`:173`（`export function apply(ctx)`）。
- **对 Voice Assistant 的含义**：
  1. 任务书 §五 的 `packages/plugin/plugin.json` **不应**作为 DSH 清单去实现——DSH 不读它。若要保留，只能作为本工程自己的元数据文件，且必须在文档里注明「DSH 不消费」。
  2. 语音插件 Host 半边建议：`export const name = 'voice-assistant'`、`export const inject = ['agents','sessions','commands','settings']`（按需最小化）、`export const Config = z.object({...})`、`export function apply(ctx, config)`。
  3. `inject` 是「服务就绪才加载」的栅栏：`P\cordis\lib\types\registry.d.ts:57-58` 明确「it only loads while all are available」；因此**不要把可选服务写进 `inject`**（`dsh-video-skin` 就刻意留空，用 `ctx.inject` 迟到接入，见 §3.8）。

### 2.2 `package.json` 的 `dsh` 字段（bundle / profile / client）

- **结论**：`package.json.dsh` 是唯一的包级清单，共 6 个角色键：`bundle`、`profile`、`client`、`configTrees`、`sessionFormatMigration`、`moduleFallback`（最后一个由 launcher 生成，不是作者配置）。插件包通常用 `bundle.patch` + `client` 两个。
- **证据**：
  - `P\dsh-package-manifest\lib\types\types.d.ts:7-23`（`DshManifest` 全部字段与注释）。
  - bundle：同文件 `:25-28`（`DshBundleManifest.patch` 是「相对声明包根的 patch 文件路径」）。
  - profile：同文件 `:30-37`（`bundles: string[]` 有序层列表；`patchReload: 'live' | 'startup'`）。
  - client：同文件 `:39-52`（`platform`、`inject`、`immediately`、`external`；`:42` 明确 `inject` 是「Informational package-name dependencies, not Cordis service injection」）。
  - 真实值：`Q\dsh-channel-wechat\package.json:52-62`（`bundle.patch: "./cordis.patch.yml"` + `client: { platform: "web", inject: ["@deepseek-ai/dsh-client-ui-settings"] }`）；`Q\dsh-video-skin\package.json:60-64`（只有 `bundle.patch`，没有 client，因为它用注入行而非 Client 插件）。
- **对 Voice Assistant 的含义**：
  1. 语音插件需两条 manifest：`dsh.bundle.patch`（Host 行）+ `dsh.client`（麦克风/设置页 UI，`platform: "web"`）。
  2. `client.inject` 只写**包名**（用于 factory 到达顺序与 Cordis 组合），不写服务名；服务依赖写在 Client 插件的 `inject` 数组里（§9.2）。

### 2.3 bundle patch 的方言（YAML 数组 + insert + id 覆盖 + `!!js`）

- **结论**：bundle patch 与 profile patch 是同一种方言：**顶层 YAML 数组**，元素是 `PatchOptions`，字段 `id / insert / name / config / group / disabled / inject / intercept / isolate`。`insert` 追加新行；给 `id` 则按 id 覆盖既有行（改 config / disabled / inject）。`!!js` 标量是表达式节点，由 Loader 在条目激活时求值。补丁匹配不到任何行时**只 warn 并跳过**（这正是「插件没生效却不报错」的常见原因）。
- **证据**：
  - 方言与语义：`P\cordis-plugin-include\lib\types\index.d.ts:26`（`applyEntryPatches` 是「THE patch semantics」，被挂载与 `dsh --dump-config` 共用）、`:28-39`（`PatchOptions` 全字段）、`:10`（`entryListSchema`：`!!js` 标量往返为表达式节点）。
  - 「匹配不到就 warn 并跳过」：同文件 `:20`。
  - 行字段：`P\cordis-plugin-loader\lib\types\config\entry.d.ts:6-19`（`EntryOptions`：`id/name/config/group/disabled/inject`；`:8` `name` 是「Module specifier imported by the entry tree」）。
  - 真实 profile patch（覆盖既有行 + `!!js`）：`J\cordis.patch.yml:2-8`（`id: acp` 覆盖 `config.provider/model`）、`:14-19`（`!!js process.env.HOME + '/.jarvis/skills'`）。
  - 真实 bundle patch（insert）：`Q\dsh-video-skin\cordis.patch.yml:13-15`；`Q\dsh-channel-wechat\cordis.patch.yml:10-13`。
  - 注释中的关键实践经验：`Q\dsh-video-skin\cordis.patch.yml:8-9` —「`name` 必须与安装的包名一致，否则 loader 只 warn 然后跳过这一行 —— 表现就是『插件没生效但不报错』」。
- **对 Voice Assistant 的含义**：
  1. 语音包必须自带 `cordis.patch.yml` 并提供 `dsh.bundle.patch`，否则用户装了包也不会挂载。
  2. 音色/后端地址/端口这类部署参数**不要**硬编码进 patch：`config` 是**整行替换而非深合并**（`Q\dsh-video-skin\cordis.patch.yml:10-11` 明确记录），patch 里写死会覆盖用户在 GUI 里的设置。

### 2.4 profile 的组装顺序（bundle 层 → 用户 patch 层 → launcher 层）

- **结论**：profile 目录 = `package.json`（`dsh.profile.bundles` 有序层 + out-of-tree 依赖）+ `cordis.patch.yml`（用户自己的 patch 层）。组装顺序：空列表 → 依次应用每个 bundle 的 patch → 应用 profile 自己的 patch → 应用 launcher 层（`--patch` 文件与 flag 派生 patch）。模块解析是**双锚点**：先从 dsh 安装目录解析 bundle 名，再从 profile 目录解析；profile 的 `node_modules` 中由 pnpm 管理的条目优先。
- **证据**：
  - `P\dsh-app-boot\lib\types\profile.d.ts:5-13`（模块级文档，完整描述上面这个顺序与双锚点）。
  - `:29`（`PROFILES_DIR = "profiles"`）、`:31`（`PROFILE_PATCH_FILENAME = "cordis.patch.yml"`）、`:47-56`（`ProfileLayer`：`packageName/packageDir/patchPath/patches`）。
  - `:180`（`composeEntries(layers, warn)`：与启动时同一个 `applyEntryPatches` 调用）。
  - 真实 profile：`J\package.json:5-13`（`bundles: ["@deepseek-ai/dsh-base","@deepseek-ai/dsh-acp-app"]`、`patchReload: "startup"`）；`C:\Users\lenovo\.dsh\profiles\desktop\package.json:3-16`（`dependencies` 三个第三方插件 + `bundles` 五个，含 `dsh-video-skin`、`dsh-channel-wechat`）。
  - 根 `cordis.yml` 是空列表：`J\cordis.yml:1-4`（注释「an empty entry list. The tree is composed as patches」，正文 `[]`）。
- **对 Voice Assistant 的含义**：
  1. 语音插件的 Host 行既可以由自己的 bundle patch 插入（推荐，随包分发），也可以由用户 profile 的 `cordis.patch.yml` 插入（本地调试）。
  2. 若要**改**别人已插入的行（例如给 `agent-loop` 加 config），必须用 `- id: <既有行 id>` 而不是再 insert 一次，否则 `Entry` 的 `id` 冲突（`P\cordis-plugin-loader\lib\types\config\entry.d.ts:7`：`id` 是「Stable id inside the containing entry tree」）。

### 2.5 安装与启用方式（plugin_manager，不是手工改 profile）

- **结论**：安装/启用插件走 `plugin_manager` 工具：`install_bundle`（传入**工作区内的绝对包目录**，它负责写 profile 的 `package.json`、`cordis.patch.yml`、跑代理安装）、`set_plugin`（enable/disable）、`set_bundle`。手工写 profile 的 `package.json`/`cordis.patch.yml`、或直接在 profile 里跑 pnpm，都属于绕过该流程（需要单独审批且容易与 launcher 竞争）。
- **证据**：
  - 技能 `cordis-plugin-development`（本次已加载）正文第 1 段：「use ordinary workspace files to author a bundle, then `plugin_manager` with `action: install_bundle` and the absolute package directory as `target`… Do not write the profile's `package.json` or `cordis.patch.yml`, create packages under `$DSH_HOME`, or run pnpm in the profile directory」。
  - 工具自身的 `applyEntryPatches` 语义要求 patch 与 mount 同源（§2.3 的 `P\cordis-plugin-include\lib\types\index.d.ts:26`）。
  - 真实 profile 里插件三处落点（安装后可见的事实）：`C:\Users\lenovo\.dsh\profiles\desktop\package.json:3-6`（dependencies）、`:8-14`（bundles）、`C:\Users\lenovo\.dsh\profiles\desktop\cordis.patch.yml` 若需覆盖行再加。
- **对 Voice Assistant 的含义**：CI/文档里应写「用 `plugin_manager.install_bundle` 安装本文工作区路径」，而不是「复制文件到 profile」；否则用户环境的 `pnpm-lock` 与模块回退链接（`P\dsh-app-boot\lib\types\profile.d.ts:103-115`）会与文档不一致。

### 2.6 禁用插件与 HMR

- **结论**：禁用有两条路径：行的 `disabled: true`（`EntryOptions.disabled`，支持 `!!js` 表达式），或 `plugin_manager.set_plugin(enabled:false)`（改写 patch 层）。热更新分两层：Host 侧 `cordis-plugin-hmr`（watch 源码 → 清模块缓存 → 只重载受影响条目，框架级依赖变更退化为 `loader.exit()` 即进程重启）；profile 的 patch 文件生命周期由 `dsh.profile.patchReload`（`'live' | 'startup'`）决定。
- **证据**：
  - `disabled`：`P\cordis-plugin-loader\lib\types\config\entry.d.ts:15-16`、`:38-42`（`!!js` 表达式对 loader context 求值）。
  - HMR：`P\cordis-plugin-hmr\README.md:1-14`（watch/trace/clear/reload 与 fallback 到 `loader.exit()`）、`:29-36`（`config`：`root`/`ignored`/`debounce`）、`:48-53`（`hmr/change`、`hmr/reload` 事件）。
  - patch 生命周期：`P\dsh-package-manifest\lib\types\types.d.ts:36-37`（`ProfilePatchReload = 'live' | 'startup'`）、`:33`（`patchReload` 省略时自定义 profile 默认 `live`）。
  - 运行中的 HMR 行：Host `Config.listConfigs` 中 `include:hmr` → `@deepseek-ai/dsh-hmr`（注意：desktop 版的行名与 npm 包名 `cordis-plugin-hmr` 不同，属 §1.1 的版本分歧）。
- **对 Voice Assistant 的含义**：语音插件的 Python Runtime **不在** HMR 覆盖范围（HMR 只重载 Loader 条目与模块图）；插件↔Runtime 的 WebSocket 重连必须在「插件被重载」时优雅恢复（`ctx.effect` 的 disposer 里主动 close + 重连指数退避）。

---

## 3. Plugin Context 可用服务（逐项核实）

> 方法：以 `P\` 的 `declare module '@deepseek-ai/cordis' { interface Context { ... } }` 合并声明为一级证据，并用 Host Inspect `Service.listService`（[I]）确认「当前 Host 真的提供该 key」。

### 3.1 `ctx.agents` —— **存在**

- **结论**：存在，是 `AgentRegistry` 实例，提供 `create / resume / get / list / roots / isOwnedBy / register / enter / announce / setFactory / withInitiator / withoutInitiator / currentInitiator / requireInitiator`。**没有** `agents.activeSession`、`agents.cancelAll`、`agents.onEvent` 之类的便捷方法。
- **证据**：`P\dsh-agent\lib\types\index.d.ts:18-22`（`interface Context { agents: AgentRegistry }`）、`:199`（`export declare class AgentRegistry extends Service`）、`:279`（create）、`:287`（resume）、`:341`（get）、`:350`（isOwnedBy）、`:355`（list）、`:362`（roots）、`:267`（setFactory）。**0.2.1 实现**：`R\dsh-agent\lib\index.js:491`（`register`）、`:512`（`enter`）、`:596`（`get`）、`:614`（`list`）、`:623`（`roots`）。运行时：[I] Host 服务目录含 `key: "agents"`，签名与上述一致（含 `create/get/list/roots`）。
- **对 Voice Assistant 的含义**：这是 `DshAgentBridge` 的唯一 Agent 入口；`getActiveSession()` 不能直接映射到 `agents`（见 §11.1）因为在 Host 侧「活动会话」不是 registry 概念。

### 3.2 `ctx.sessions` —— **存在**

- **结论**：存在，是 `SessionStore`（内存 store），提供 `create / prepare / enter / announce / flush / get / list / fork`。Session 本身是普通类 `Session`（不是 Service），有 `id / header / append / deriveMessages / snapshotEvents / requestHeader / requestContext / surface`。
- **证据**：`P\dsh-session\lib\types\index.d.ts:24-27`（`interface Context { sessions: SessionStore }`）、`:317`（`class SessionStore extends Service`）、`:342`（create）、`:362`（prepare）、`:419`（get）、`:424`（list）、`:439`（fork）、`:411`（flush）；`:103`（`class Session`）、`:121`（`get id()`）、`:238`（append）、`:285`（deriveMessages）。运行时：[I] Host 服务目录含 `key: "sessions"`。
- **对 Voice Assistant 的含义**：语音侧只应**读** `ctx.sessions.get(id)`；**不要**用 `ctx.sessions.create()` 新建语音专用会话——Agent 与 Session 必须由 `ctx.agents.create()` 一体创建（`:144-147` 的 `AgentHandle` 语义），否则 Agent 拿不到 handle，无法释放。

### 3.3 `ctx.tools` —— **存在**

- **结论**：存在，`ToolRuntime`，提供 `register / restrict / guard / get / schemas / execute / executionMode / presentAs`。
- **证据**：`P\dsh-tools\lib\types\index.d.ts:24-27`（`interface Context { tools: ToolRuntime }`）、`:494`（类）、`:601`（register）、`:609`（restrict）、`:620`（guard）、`:655`（get）、`:676`（schemas）、`:730`（execute）。运行时：[I] Host 服务目录 `key: "tools"`。
- **对 Voice Assistant 的含义**：语音控制（「小声点」「停止播报」）适合做成 tool 让 Agent 调用，但**不要**把 TTS 播放放进 tool 的同步路径（tool 有 `timeoutMs` 与 `exec.signal` 语义，`P\dsh-tools\lib\types\index.d.ts:139`、`:119`）；用 tool 只发「意图事件」给 Runtime。

### 3.4 `ctx.commands` —— **存在**

- **结论**：存在，`CommandRuntime`，提供 `register / list / find / execute / registerFileReceiptResolver`。命令是「不经模型」的人类命令，执行会写入 `command/run` + `command/done` 两条 log-only 事件。
- **证据**：`P\dsh-commands\lib\types\index.d.ts:60-64`（`interface Context { commands: CommandRuntime }`）、`:91`（register）、`:103`（list）、`:110`（find）、`:139`（execute）、`:37-52`（`CommandDefinition`：`name/description/input/recordInput/handler`）；事件 `P\dsh-commands\lib\types\types.d.ts:84`（`commands/change`）、`:99`（`command/run`）、`:111`（`command/done`）。运行时：[I] Host 服务目录 `key: "commands"`。
- **对 Voice Assistant 的含义**：`/voice`（开关常驻听）、`/voice-status` 这类命令用 `ctx.commands.register` 实现，天然与 GUI 斜杠命令共享，不需要自造一套。

### 3.5 `ctx.server` / `ctx.http` —— **不存在**；真实名字是 `ctx.webServer`

- **结论**：Host 侧**没有** `ctx.server`，也**没有** `ctx.http`。HTTP 扩展点是 `ctx.webServer`（`WebServer` 服务）：`register(route)` / `registerUpgrade(route)` / `registerFallback(handler)` / `tapIndex(transform)` / `renderIndex` / `collectIndexInjections`；页面注入则监听 `webserver/index-inject` 事件，把行 push 进 table。
- **证据**：`P\dsh-host-webserver\lib\types\index.d.ts:16-18`（`interface Context { webServer: WebServer }`）、`:20-27`（`webserver/index-inject` 事件，载荷是**可变行表** `IndexInjection[]`）、`:33-39`（`WebRoute { kind: 'exact' | 'prefix'; path; handler }`）、`:90`（register）、`:97`（registerUpgrade）、`:106`（registerFallback）、`:114`（tapIndex）。真实用法：`Q\dsh-video-skin\index.js:201`（`ctx.on('webserver/index-inject', (table) => { ... table.push(...rows) })`）、`:219`（`ctx.inject(['webServer'], (child) => ...)`）、`:225-232`（`child.webServer.register({ kind: 'exact', path: CONFIG_ROUTE, handler })`）、`:393-401`（返回 disposer 数组统一释放）。
- **对 Voice Assistant 的含义**：
  1. Runtime 的 HTTP/WS 端点**不要**挂在 DSH 的 `webServer` 上（会把语音可用性与 DSH 生命周期耦合，违反「Voice Runtime 必须可脱离 DSH 运行」）。Runtime 自带 localhost 服务；如果确实要借道 DSH 暴露（例如浏览器端麦克风需要同源），才用 `registerUpgrade` 挂 `/voice/ws`。
  2. `webserver/index-inject` 只在索引渲染/worker boot 时 emit，注入行必须**同步**注册（`dsh-video-skin` 的注释就记录了「桌面壳只在宿主启动时收集一次」`Q\dsh-video-skin\index.js:10-13`）。

### 3.6 `ctx.settings`（配置）与插件 `Config`（schema）

- **结论**：两者并存且语义不同。① `ctx.settings` 是**用户设置文档**服务：插件 `register(ns, schema, options)` 得到一个 `SettingsScope`（`get / watch / update / replace`），写入落到用户文档并 emit `settings/updated` / `settings/document-updated`。② 插件 `Config` 是 **Cordis entry config**：`static Config = z.object(...)`，由 Loader 在 fiber 启动前按标准 schema 校验。GUI 只会把 **`Volatile<T>` 标注的字段**投影成可编辑表单。
- **证据**：
  - `P\dsh-settings\lib\types\index.d.ts:111-115`（`interface Context { settings: SettingsProvider }`）、`:216`（`register<Namespace, T>(ns, schema, options)`）、`:84-110`（`SettingsScope`：`get`/`watch`/`update`/`replace`）、`:236`（describe）、`:256`（update）、`:282`（mutate）、`:121-134`（`SettingsConflictError`）。
  - 事件：`P\dsh-settings\lib\types\types.d.ts:89`（`settings/updated`）、`:101`（`settings/document-updated`）。
  - Config 校验：`P\cordis\lib\types\fiber.d.ts:31`（`resolveConfig`）、`:157`（`effect`），`P\cordis\lib\types\registry.d.ts:56`（`Config?: StandardSchemaV1`）。
  - `Volatile` 的 GUI 语义：`Q\dsh-channel-wechat\lib\index.d.ts:19-33`（「Both fields are `volatile`, which is what makes them editable from the GUI: the settings service projects only volatile fields into a form, and a non-volatile field is *absent* from that projection rather than read-only」）、`:42`（`cwd: Volatile<string>`）、`:114-132`（真实 `Config` 的 schemastery 泛型形态）。
  - 真实 3 参数：`Q\dsh-channel-wechat\lib\index.d.ts:181-185`（`permissionApplierOf` 通过 `ctx.permissionPresets.set` 落到 session，而不是写全局默认）。
- **对 Voice Assistant 的含义**：
  1. 插件侧配置（Runtime URL、默认音色、唤醒词）应同时存在于 **entry config**（部署默认，patch 可覆盖）与 **settings namespace**（用户可改，GUI 可渲染）。DSH 的既有范式是「entry config 作 base 层，settings 覆盖」（`P\dsh-settings\lib\types\index.d.ts:23-27` 的 `base` 字段 + `:216` 的 `options`）。
  2. 可编辑字段必须包 `Volatile<T>`，否则 GUI 里**根本不出现**该字段（不是灰显）。
  3. 密钥类字段用 `role('secret')`（`P\dsh-settings\lib\types\types.d.ts:41-42` 的 `secrets` 视图），且**不要**把 TTS 云服务 key 写进 session（会进日志）。

### 3.7 `ctx.events` 与 `ctx.effect` / dispose

- **结论**：
  - 事件总线存在：`ctx.events` + 混入 `ctx.on / once / emit / parallel / serial / bail / waterfall`；五种派发模式 `emit | parallel | serial | bail | waterfall`；监听器可带 `{ prepend, global }`。
  - **`ctx.effect()` 存在**（Cordis 把 `Fiber.effect` 挑到 Context 上），是最重要的生命周期原语：立即执行 body，把返回的 disposer 收集起来，fiber 卸载或手动调用时**逆序**释放。
  - **`ctx.dispose` 不存在**。可用的等价物：`ctx.fiber.dispose()`（异步，卸载整个插件）、或 `ctx.effect(() => () => {...})` 返回的 disposer、或 `ctx.fiber.update(config)`。
  - **`ctx.provide(name, value)` 与 `ctx.get(name, strict?)` 存在**：`provide` 在本 scope 提供一个服务/值并返回 disposer（只能由提供者 `set`），`get` 读取（未提供时返回 `undefined`，`strict` 时按 Cordis 语义报错/严格解析）。插件之间共享自定义能力时用这一对，而不是挂在 `globalThis`。
- **证据**：
  - `P\cordis\src\context.ts:16-33`（Context 接口：`events` / `logger` / `reflect` / `registry` / `root` / `baseUrl`）、`:26`（events）、`:99`（extend）、`:121`（isolate）、`:141`（intercept）。
  - `P\cordis\src\events.ts:32`（`DispatchMode` 五值）、`:97`（`on`）、`:106`（`once`）、`:112-117`（`EventOptions`）、`:288`（`on` 实现，`assertActive` + effect 注册）。
  - `P\cordis\lib\types\fiber.d.ts:7-12`（`interface Context extends Pick<Fiber, 'effect'> { fiber: Fiber }`）、`:157`（`effect(execute, label?)`）、`:41`（`Disposable`）、`:49-51`（`Effect` 可为单 disposer / Promise / 迭代器）、`:112`（`readonly dispose: () => Promise<void>`）、`:187`（`restart`）、`:199`（`update`）。
  - `P\cordis\lib\types\reflect.d.ts:16`（`get(name: string, strict?: boolean): any`）、`:41`（`provide<K extends string & keyof this>(name: K, value: undefined | this[K]): () => void`）、`:43`（`provide(name: string, value?: any): () => void`）、`:20-21`（「Only the fiber that provided the service may set it; setting an unprovided name throws」）。真实用法：`R\dsh-experimental-speech-to-text\lib\index.js:18`（`super(ctx, "speechToText")` 即 Service 构造期 provide）、`:20`（`ctx.fiber.entry?.options.id`）。
- **对 Voice Assistant 的含义**：所有外部资源（WebSocket、子进程、定时器、麦克风）必须包在 `ctx.effect` 里返回 disposer；否则插件重载/禁用时会**泄漏**，且 HMR 下会叠加多个监听（`Q\dsh-channel-wechat\lib\index.js:6696-6710` 的注释专门记录了「不要靠 context 生命周期，要显式返回 disposer」这个坑）。

### 3.8 `ctx.inject(deps, cb)`（可选服务的迟到接入）

- **结论**：`ctx.inject(deps, cb)` 是「等服务可用再跑，服务变化就卸载重跑」的语法糖，等价于 `ctx.plugin({ inject, apply: cb })`。可选能力（例如 `webServer`）用它接入，避免把插件整体阻塞。
- **证据**：`P\cordis\lib\types\registry.d.ts:101-111`（`inject(deps, callback)`，`:103-107` 注释「the callback is unloaded and re-run whenever a required service changes」）；真实用法 `Q\dsh-video-skin\index.js:219`。
- **对 Voice Assistant 的含义**：语音插件对 `speechToText`（若复用）、`webServer`、`permissionPresets` 都应走 `ctx.inject`，而 `agents`（硬依赖）走静态 `inject`。

### 3.9 `ctx.slots` / `ctx.locale` / `ctx.uiRenderer` —— **仅 Client 侧存在**（Host 无）

- **结论**：`ctx.slots`（`SlotRegistry`）、`ctx.uiRenderer`、`ctx.locale`（`LocaleRuntime`）都是**浏览器侧**（Client Cordis runtime）的服务，由 Client 插件包声明；Host 侧**没有** `slots`、`locale`、`uiRenderer` 这三个 key。`speechToText` 则是 Host 侧服务。
- **证据**：
  - `P\dsh-client-ui-renderer\lib\types\client\index.d.ts:24-29`（`interface Context { slots: SlotRegistry; uiRenderer: UiRendererService }`）——注意文件在 `lib\types\client\` 子目录，即 Client 面。
  - `P\dsh-client-locale\lib\types\client\index.d.ts:55-58`（`interface Context { locale: LocaleRuntime }`），同在 `client/` 子目录。
  - `R\dsh-experimental-speech-to-text\README.md:12`（Host 服务 `ctx.speechToText`）；其 Client 对端：`R\dsh-experimental-api-speech-to-text\README.md:12`（「The `speech` Remote connects browser recordings to `ctx.speechToText`」）。
  - 反证：[I] `Service.listService`（Host）目录中**没有** `slots` / `locale` / `uiRenderer` / `configForms`；有 `speechToText` / `sessions` / `settings` / `sessionController` / `sessionProjections`。
- **对 Voice Assistant 的含义**：任何「注册 UI slot」的代码**必须**是 Client 插件（`dsh.client` + `<pkg>/client` 导出），Host 半边写 `ctx.slots` 会直接抛「service not found」。反之任何「创建 Agent/发消息」的代码必须是 Host 插件。

### 3.10 Context 服务总表（本次核实结果）

| 任务书清单项 | 真实 API | 结论 | 证据 |
|---|---|---|---|
| `ctx.agents` | `AgentRegistry` | 存在 | `P\dsh-agent\lib\types\index.d.ts:20` |
| `ctx.sessions` | `SessionStore` | 存在 | `P\dsh-session\lib\types\index.d.ts:26` |
| `ctx.tools` | `ToolRuntime` | 存在 | `P\dsh-tools\lib\types\index.d.ts:26` |
| `ctx.commands` | `CommandRuntime` | 存在 | `P\dsh-commands\lib\types\index.d.ts:62` |
| `ctx.server` / `ctx.http` | 无 | **不存在** | 全 `P\` 无此 key；Host [I] 无 |
| `ctx.webServer`（HTTP 真实入口） | `WebServer` | 存在 | `P\dsh-host-webserver\lib\types\index.d.ts:17` |
| `ctx.slots` / UI | `SlotRegistry` | 仅 Client | `P\dsh-client-ui-renderer\lib\types\client\index.d.ts:26` |
| `ctx.settings` | `SettingsProvider` | 存在 | `P\dsh-settings\lib\types\index.d.ts:113` |
| 插件 `Config` schema | `static Config = z(...)` | 存在 | `P\cordis\lib\types\registry.d.ts:56` + `Q\dsh-channel-wechat\lib\index.d.ts:114` |
| `ctx.events` | `EventsService` + 混入方法 | 存在 | `P\cordis\src\context.ts:26`；`P\cordis\src\events.ts:97` |
| `ctx.effect` | `Fiber.effect` | 存在 | `P\cordis\lib\types\fiber.d.ts:8`、`:157` |
| `ctx.dispose` | 无（用 `ctx.fiber.dispose()`） | **不存在** | `P\cordis\lib\types\fiber.d.ts:112` |
| `ctx.locale` | `LocaleRuntime` | 仅 Client | `P\dsh-client-locale\lib\types\client\index.d.ts:57` |
| `ctx.speechToText`（额外发现） | 语音识别服务 | 存在（仅 0.2.x 桌面版） | `R\dsh-experimental-speech-to-text\README.md:12` + [I] |
| `ctx.sessionController`（额外发现） | `SessionController` | 存在 | `P\dsh-api-session-controller\lib\types\index.d.ts:17` |
| `ctx.permissionPresets` | `PermissionPresetService` | 存在 | `P\dsh-permission-presets\lib\types\index.d.ts:21` |
| `ctx.approval` | `ApprovalService` | 存在 | `P\dsh-user-approval\lib\types\index.d.ts:13` |

---

## 4. Agent API（create / resume / get / list 与 AgentHandle）

### 4.1 `create` / `resume` 的入参是「选项对象」，返回 `AgentHandle`

- **结论**：`ctx.agents.create({ sessionId, meta?, seed?, agentOptions?, parentAgent?, setup?, signal? })` 与 `ctx.agents.resume({ resumeSessionId, agentOptions?, parentAgent?, setup?, signal? })`，二者都返回 `Promise<AgentHandle>`，`AgentHandle = { agent: Agent; dispose(): Promise<void> }`。`dispose()` 会停 loop → 等收敛 → 注销 agent → 删 session → 回卷 scoped context。
- **证据**：`P\dsh-agent\lib\types\index.d.ts:48-105`（`CreateAgentOptions` 全字段）、`:110-129`（`ResumeAgentOptions`）、`:144-147`（`AgentHandle`）、`:131-143`（dispose 的完整语义注释）；`:279`、`:287`（两个方法）。
- **对 Voice Assistant 的含义**：
  1. `resume` 只能用于**已持久化**的 session（`P\dsh-agent\lib\types\index.d.ts:177-180`：必须 `ctx.sessionPersistence` 存在）。语音「固定会话」策略需要先判断 session 是否存在（见 §11.1）。
  2. `sessionId` 必须由调用方提供（`Branded<'SessionId'>`，`P\dsh-session\lib\types\types.d.ts:5`），不能用 `ctx.sessions.create()` 的自动 id 再塞给 agent——那会绕过 factory 的事务。
  3. 语音插件应持有 `AgentHandle`（不是裸 `Agent`）吗？**不建议**：handle 的 disposer 是「能力」，只能由创建者持有（`:131-143`）。语音绑定**既有** session 时应只用 `ctx.agents.get(id)` 的裸 `Agent`，把销毁权留给原创建者（GUI/ACP）。

### 4.2 `get` / `list` / `roots` / `isOwnedBy`

- **结论**：`get(id)` 返回裸 `Agent | undefined`；`list()` 返回全部存活 Agent（注册顺序）；`roots()` 只返回无父的顶层 Agent；`isOwnedBy(id, owner)` 判断运行期父子关系（与 session 的持久 lineage 无关）。**没有** `getByTitle`、`findByCwd`、`active()`。
- **证据**：`P\dsh-agent\lib\types\index.d.ts:341`（get）、`:355`（list）、`:362`（roots）、`:350`（isOwnedBy）、`:336-362` 的逐条注释；README 同义表述 `P\dsh-agent\README.md:32`。
- **对 Voice Assistant 的含义**：语音侧枚举「可绑定的会话」= `list()`；但「用户当前在看哪个会话」不在 Host（§11.1）。

### 4.3 Agent 的实时字段与方法

- **结论**：`Agent` 的实时面为：`id`、`options`（provider/model/reasoningEffort/maxTokens）、`session`（`Session`）、`inbox`（`Inbox`）、`status`（`'idle' | 'running'`）、`ctx`（agent 作用域 Context，注册的工具/prompt/监听器只对该 agent 生效）；方法：`cancel(cause, options?)`、`whenIdle()`、`runMaintenance(task)`、`send(message, target, wakeup)`、`followup(message)`、`steer(message)`、`inject(message)`。
- **证据**：`P\dsh-agent\lib\types\runtime-types.d.ts:138-211`（declare module 的 Agent 增补：`:141` options、`:143` session、`:145` inbox、`:147` status、`:149` ctx、`:157` cancel、`:164` whenIdle、`:174` runMaintenance、`:186` send、`:192` followup、`:200` steer、`:209` inject）；`:90`（`AgentStatus = 'idle' | 'running'`）；基础 `Agent` 只有 `id`：`P\dsh-agent\lib\types\types.d.ts:11-14`。
- **对 Voice Assistant 的含义**：`status` 是语音侧「Agent 是否正在思考」的唯一可靠实时信号（配合 `agent/status` 事件），用于桌宠状态与 barge-in 判定；但注意 status 只表示「有没有 driver 在跑」，**不**表示「是否正在流式输出」（用 assistant-stream 判定）。

---

## 5. Agent 事件（`agent/*`）：真实名称与载荷

> 全部来自 `P\dsh-agent\lib\types\runtime-types.d.ts` 的 `declare module '@deepseek-ai/cordis' { interface Events { ... } }`（`:212-417`）。每个声明上都带 `@mode`（`emit` / `waterfall` / `serial`），这是派发语义的唯一权威描述。

| 事件名（**全名，逐字**） | 载荷 | 模式 | 证据行 |
|---|---|---|---|
| `agent/created` | `{ agent }` | emit | `:224-226` |
| `agent/disposed` | `{ agent }` | emit | `:235-237` |
| `agent/status` | `{ agent, status: 'idle' \| 'running' }` | emit | `:247-250` |
| `agent/inbox/inserted` | `{ agent, message }` | emit | `:258-261` |
| `agent/inbox/claimed` | `{ agent, message, turn }` | emit | `:272-276` |
| `agent/inbox/discarded` | `{ agent, message }` | emit | `:284-287` |
| `agent/session-start` | `{ agent, source: 'startup'\|'resume'\|'clear'\|'compact' }` | emit | `:298-301` |
| `agent/pre-step` | `{ agent, messages, turn, step, signal }` + `next()` → `PreStepDecision` | **waterfall** | `:313-319` |
| `agent/request` | `{ agent, turn, step, signal }` + `next()` → `LlmCallConfig` | **waterfall** | `:336-341` |
| `agent/request-error` | `{ agent, turn, step, provider, failure, retryPolicy, signal }` + `next()` → `{ kind:'retry' } \| undefined` | **waterfall** | `:357-365` |
| `agent/assistant-stream` | `{ agent, frame: AssistantStreamFrame }` | emit | `:375-378` |
| `agent/turn-stopping` | `{ agent, turn, signal }` | **serial** | `:396-400` |
| `agent/error` | `{ agent, turn, step, error: unknown }` | emit | `:411-416` |

- **0.2.1 实现证据（事件真的被发出，不是只有类型）**：`R\dsh-agent-loop\lib\index.js:1079-1081` — 每个 model attempt 构造 `AssistantStreamAttempt` 并把 `(frame) => this.dispatch.emit("agent/assistant-stream", { frame })` 作为发布器；`agent/status` 在 `:794-799`（`setPhase` 里仅当状态真变才发）；`agent/error` 在 `:880-885`。
- **结论 1（正向）**：**不存在**名为 `assistant-stream` 或 `session/assistant-stream` 的事件；**正确全名是 `agent/assistant-stream`**。同理不存在 `agent/turn-start`、`agent/turn-end`、`agent/step-start`、`agent/message`——这些是**持久化 session 事件**（`turn/start`、`turn/end`、`step/start`、`step/end`、`assistant/message`），走 `session/event` 通道，不是 `agent/*` 通道。
- **结论 2（scope 过滤）**：所有 `agent/*` 事件的 `this` 是 `Scoped<Agent>`，**scope 过滤分发**——在 `agent.ctx` 上注册的监听器只收到该 agent 的事件；在宿主 root context 上注册则收到全部（`P\dsh-agent\lib\types\runtime-types.d.ts:221`、`:232`、`:244` 等每条的「Scope-filtered dispatch」说明）。
- **证据**：上表逐行；另外 `P\dsh-agent\README.md:67` 用文字总结同一批事件（`agent/pre-step` 可拒绝/替换、`agent/request-error` 可重试、`agent/turn-stopping` 可 steer 续命、`agent/assistant-stream` 是 start/chunk/end 三帧）。
- **对 Voice Assistant 的含义**：
  1. 语音侧**只应监听** `agent/assistant-stream`（低延迟文本）、`agent/status`（忙闲）、`agent/error`（失败播报）、`agent/turn-stopping`（可选：句末追加「还需要我说吗」）——**不要**监听 `agent/pre-step` 做语音逻辑，它是控制面，误用会改变模型输入。
  2. 过滤：插件在 root context 上 `ctx.on('agent/assistant-stream', ...)` 会收到**所有**会话的流；必须先按 `payload.agent.id === boundSessionId` 过滤，否则多会话时会把别人的回答念出来。

---

## 6. Session API

### 6.1 会话 ID 与持久化

- **结论**：`SessionId` 是 branded string（`Branded<'SessionId'>`），由调用方提供或 store mint（`session-<n>`）。持久化**不在** `dsh-session` 里：`dsh-session` 只提供 append-only log + 内存 store，持久化由插件订阅 `session/event` 并在 `session/flush` 时落盘（真实实现：`dsh-session-persistence-jsonl`）。Session 的 `header`（version/id/createdAt/cwd/parentSession/isSeeded/origin/delegationDepth/agentPreset）是存储元数据，**不在**事件日志里。
- **证据**：`P\dsh-session\lib\types\types.d.ts:5-11`（`SessionId` 与 brand 函数）、`:54`（`SESSION_FORMAT_VERSION = 3`）、`:58-95`（`SessionHeader`）；`P\dsh-session\lib\types\index.d.ts:1-7`（模块文档：persistence is a plugin concern：「subscribe to `session/event`, drain on `session/flush`」）、`:342`（`create(id?)`，省略 id 时 mint `session-<n>`）、`:117`（`readonly header`）。
- **对 Voice Assistant 的含义**：语音插件**不要**自己写 session 文件；要恢复上下文就用 `ctx.agents.resume({ resumeSessionId })`，让持久化插件负责读盘。

### 6.2 消息流与订阅方式

- **结论**：订阅有两个真实通道，语义不同：
  1. **持久化通道**：`ctx.on('session/event', (session, event) => ...)` —— post-commit、fire-and-forget、**每个 append 都会触发**，载荷是完整 `SessionEvent`（含 `type/seq/time/data`）。这是唯一能拿到「已提交事实」的通道。
  2. **实时展示通道**：`ctx.on('agent/assistant-stream', ...)`（§7）—— process-local、**不持久**、可能丢帧（晚订阅看不到之前的 chunk）。
  另有 `session/created` / `session/disposed` / `session/flush`（awaited durability checkpoint）。
- **证据**：`P\dsh-session\lib\types\index.d.ts:40`（`session/created`）、`:50`（`session/disposed`）、`:62`（`session/event`，`:52-61` 注释明确「Post-commit, fire-and-forget append feed」）、`:71`（`session/flush`，`@mode parallel`）；`:411`（`flush(session)` 是唯一 flush 入口）。
  真实用法：`Q\dsh-channel-wechat\lib\index.js:6711-6715`（`events.on('session/event', (session, event) => this.onSessionEvent(String(session.id), event, session.header?.cwd))`，注释说明「without this subscription the model's answer has no route back」）。
- **对 Voice Assistant 的含义**：语音播报应**双通道**：`agent/assistant-stream` 做低延迟增量（首字延迟），`session/event` 的 `assistant/message` 做最终一致性（避免漏句、保证打断后仍能补全）。只订阅其中一个都会出错。

### 6.3 会话内消息事件类型（持久层）

- **结论**：`session/event` 里与语音相关的关键 `type`：`turn/start`、`turn/end`（含 `reason`）、`step/start`、`step/end`、`user/message`、`assistant/message`（含 `stream`、`usage?`、`interrupted?: true`）、`assistant/attempt`（未产生可见消息的尝试）、`tool/call`、`tool/result`、`request/header`、`request/context`、`system/message`、`session/end-seed`。
- **证据**：`P\dsh-session\lib\types\types.d.ts:249`（turn/start）、`:260`（turn/end）、`:265`（step/start）、`:270`（step/end）、`:281`（user/message）、`:309-317`（assistant/message + `interrupted?`）、`:323`（assistant/attempt）、`:333`（tool/call）、`:351`（tool/result）、`:366`（request/header）、`:378`（request/context）、`:401`（session/end-seed）；`TurnEndReasonMap` 在 `:165-199`（`completed` / `aborted` / `blocked` / `error` / `max-tokens` / `interrupted`）。
- **对 Voice Assistant 的含义**：`turn/end.reason.kind` 是语音侧「本轮结束原因」的唯一权威来源：`completed` → 正常播完；`aborted` → 用户打断（不要再念剩余）；`error` → 念一段失败提示；`max-tokens` → 提示被截断。

---

## 7. Assistant Stream 的真实事件/增量形态

### 7.1 帧结构（process-local）

- **结论**：`agent/assistant-stream` 的 `frame` 是三态判别联合，字段固定为：
  - `{ type: 'start', attemptId, revision, turn, step }`
  - `{ type: 'chunk', attemptId, revision, index, time, chunk }`（`index` 是**attempt 内从 0 开始的稠密序号**）
  - `{ type: 'end', attemptId, revision, index, outcome: { kind:'committed', eventType:'assistant/message'|'assistant/attempt', seq } | { kind:'abandoned' } }`（`end.index` = 已发出的 chunk 帧数量）
- **证据**：`P\dsh-agent\lib\types\runtime-types.d.ts:106-137`（`AssistantStreamFrame` 完整定义与逐字段注释）、`:366-372`（事件注释：「Chunk frames are transient; the loop appends one final v2 `assistant/message` or `assistant/attempt` with the same stream before a committed end frame」）。**0.2.1 实现**：`R\dsh-agent-loop\lib\index.js:355`（`var AssistantStreamAttempt`）、`:386-394`（`start()` 发 start 帧）、`:396-410`（`push()` 发 chunk 帧）、`:416-436`（`settle()` 发 committed end 帧）、`:438-447`（`abandon()` 发 abandoned end 帧）、`:766-767`（`assistantStreamRevision = 0; assistantAttemptCounter = 0;`）。
- **对 Voice Assistant 的含义**：
  1. `attemptId` 才是「同一次尝试」的标识（形如 `<sessionId>:<n>`，`R\dsh-agent-loop\lib\index.js:383`）；`revision` 是**每帧自增**的计数器（`() => ++this.assistantStreamRevision`，`:1079`，`:390/:405/:428/:443` 每发一帧取一次），不是「attempt 的版本号」——**不要**用 revision 判定重连。
  2. `index` 是 chunk 的稠密序号（`:406` `index: this.index++`），可用于检测丢帧（缺口 = 错过了 chunk）。

### 7.2 增量内容是什么

- **结论**：`chunk` 是 LLM 层原始 `StreamChunk`，判别值为：`block-start`、`text-delta`（`{ index, text }`）、`reasoning-delta`（**内部推理**）、`tool-call-delta`（`{ index, id, name?, argumentsDelta }`）、`block-end`（`{ index, block }`，block 已组装完）、`usage`、`finish`（`{ reason, replayState? }`）。
- **证据**：`P\dsh-llm\lib\types\types.d.ts:359-389`（`StreamChunk` 全定义，逐分支行号见 `:360/364/368/372/378/382/385`）。**0.2.1 实现**：模型流的 chunk 原样进入发布器——`R\dsh-agent-loop\lib\index.js:1088-1091`（`for await (const chunk of stream) { signal.throwIfAborted(); live.push(chunk); }`），`push()` 不修改 chunk（`:396-401`）；`text-delta` 的字面量定义亦可在 `R\dsh-llm\lib\index.js` 的 `StreamChunk` JSDoc 处核对。
- **对 Voice Assistant 的含义**：
  1. **只能念 `text-delta` 与 `block-end(text)`**；`reasoning-delta` 属于「隐藏推理」，任务书 §九 明确禁止播报（AGENTS.md 规则 5 同样禁止）。
  2. `tool-call-delta.argumentsDelta` 是**内部工具参数**，绝不能进 TTS（安全 + 体验）。
  3. `block-end` 的 `block` 是一个完整 `ContentBlock`，适合作为「一段完整文本」的切分锚点。

### 7.3 句子边界：DSH **不提供**

- **结论**：DSH 的流式增量**不携带任何句子/分句/标点边界信息**，也不提供句子切分工具或 `sentence` 事件。`text-delta` 是模型 token 级切片，切点任意（可能切开一个汉字/一个英文单词）。句子边界必须由语音侧自行累积与切分。
- **证据**：`P\dsh-llm\lib\types\types.d.ts:364-367`（`text-delta` 只有 `text: string` 与 block `index`，无边界字段）；`P\dsh-llm\lib\types\assistant-stream.d.ts:71`（`expandAssistantStream` 只还原**原始 delta 边界**，不新增语义边界）、`:154`（`joinAssistantStreamText` 只是按序拼接）。
- **可复用的真实实现（非 DSH API，但是官方插件里的成熟做法）**：`Q\dsh-channel-wechat\lib\index.js:5313-5319` 的切分优先级正则：`/\n\n+/` → `/\n/` → `/[。！？!?；;]/` → `/[，,、]/` → `/\s+/`，并处理未闭合代码围栏（`:5320-5325`）。
- **对 Voice Assistant 的含义**：需要自建 `SentenceSegmenter`：CJK 句末标点（。！？；…）+ 英文句末（. ! ? 后接空白）+ 最小/最大长度阈值 + 首句低延迟阈值（例如 12 字就切，避免长首句卡顿）。这是本工程必须实现、且 DSH 不会代劳的一层。

### 7.4 流的「可重放性」边界

- **结论**：assistant-stream 帧是**展示数据，不是重放源**；真正重放靠 `assistant/message.stream`（`AssistantStreamRecord[]` 紧凑记录，可 `expandAssistantStream()` 还原）。`end.outcome.kind === 'abandoned'` 表示「这次尝试没有落任何持久事件」（失败/取消且无可提交内容）。
- **证据**：`P\dsh-agent\lib\types\runtime-types.d.ts:129-136`（outcome 两态）、`:366-372`（「the live event remains presentation data rather than the replay source」）；`P\dsh-session\lib\types\types.d.ts:313-314`（`assistant/message.stream`：「Exact timed model stream, compacted without joining delta boundaries」）；`P\dsh-llm\lib\types\assistant-stream.d.ts:16-40`（`AssistantStreamRecord` 四态：`text-chunks` / `reasoning-chunks` / `tool-call-chunks` / `chunk`）、`:71`（expand）。**0.2.1 实现（可对照取消行为）**：`R\dsh-agent-loop\lib\index.js:1096-1112`（被 abort 时先 `live.interruptedBlocks()`，非空则 commit `assistant/message` 且带 `interrupted: true`，随后 `live.settle(...)`）、`:1113-1122`（没有可见内容则 commit `assistant/attempt`，只有 stream）。
- **对 Voice Assistant 的含义**：断线重连/插件热重载后，**不能**指望「补发 assistant-stream」；必须用 `assistant/message.stream` + `expandAssistantStream` 或直接读 `assistant/message.message.content` 重建文本。

---

## 8. 取消（cancel）与 steer 的精确语义

### 8.1 cancel 的签名与三个关键语义

- **结论**：`agent.cancel(cause, options?)`：
  1. **cause 是必需参数**，四种：`{ kind:'user' }` / `{ kind:'parent' }` / `{ kind:'hook', reason }` / `{ kind:'disposed' }`。**第一次 cause 生效**（对同一活动）。
  2. **默认清空 inbox**（排队消息 + steering 全丢）；`cancel(cause, { keepInbox: true })` 只中止当前 turn、保留 pending 工作。**没有**「只中止当前 step、保留 turn」的粒度。
  3. 没有活动活动时 cancel 是**空操作**，且不会「预置」给后续工作。
  4. **`cancel` 只发起中止、立即返回**（返回 `void`，不 await 任何东西）；要等「真的停下来」必须 `await agent.whenIdle()`，且 `whenIdle()` 是**循环等待**——它会在活动被替换（新的 `activityDone`）时继续等，直到没有 driver / maintenance 为止。
- **证据**：`P\dsh-agent\lib\types\runtime-types.d.ts:150-157`（方法注释逐条）、`:32-39`（`CancelOptions.keepInbox` 注释：「The active turn is still aborted, but un-started and pending work survives for a later turn and no canceled inbox splice is logged」）；`P\dsh-agent\README.md:175`（Known Limitations：「`cancel()` clears the inbox by default … `cancel(cause, { keepInbox: true })` aborts only the turn … there is no step-only abort that keeps the turn running」）；cause 联合类型：`P\dsh-session\lib\types\types.d.ts:148-157`。**0.2.1 实现（决定语义的地方）**：`R\dsh-agent-loop\lib\index.js:815-821`（`cancel(cause, options = {})`：`!keepInbox` → `inbox.clear()` + 清 `wakeRequested`；非 idle 才 `phase.abort.abort(cause)`）、`:800-805`（`send` 的 `wakingAfterAbort` 把「中止后唤醒」重定向到 `next-turn`）、`:806-813`（followup→next-turn+wake、steer→next-step+wake、inject→next-step+不唤醒）、`:870-875`（`whenIdle()` 的 do/while 等待 `activityDone` 稳定）、`:790-792`（`status` getter：`maintenance` 也算 `idle`）。
- **对 Voice Assistant 的含义**：
  1. 「用户说停」有两种产品语义，必须显式选：**硬停**（丢排队）用 `cancel({kind:'user'})`；**只停当前播报/当前轮**用 `keepInbox: true`。语音场景建议 `keepInbox: true`（用户往往只是要打断这句，不想丢掉自己刚说的话）。
  2. 打断 TTS ≠ 取消 Agent：任务书 AGENTS.md 规则 5 要求区分。TTS 中断只在语音侧丢弃播放队列，**不应**默认调用 `agent.cancel`。

### 8.2 取消的可观测性（怎么知道取消了）

- **结论**：取消有三处可观测证据：① 持久层 `turn/end` 的 `reason: { kind:'aborted', reason: <cause> }`；② 若已流式输出部分文本，`assistant/message` 会带 `interrupted: true`（且只含已交付的前缀）；③ 实时层 `agent/assistant-stream` 的 `end.outcome.kind === 'abandoned'`，以及 `agent/status` 回到 `idle`。**没有** `cancel()` 的返回值（返回 `void`），也**没有** `agent/cancelled` 事件。
- **证据**：`P\dsh-session\lib\types\types.d.ts:171-176`（`aborted` 变体）；`:309-317`（`assistant/message` 的 `interrupted?: true`，注释：「A turn cancelled mid-stream finalizes its delivered text/reasoning prefix as this event with `interrupted: true` … An aborted turn with no such event streamed no visible content」）；`P\dsh-agent\lib\types\runtime-types.d.ts:157`（`cancel` 返回 `void`）；`:129-136`（abandoned）。**0.2.1 实现**：`R\dsh-agent-loop\lib\index.js:1010-1026`（catch 里 `abortedCancelCause(signal)` → `turnEnds = { kind:'aborted', reason: cause }`）、`:1027-1036`（`finally` 里 append `turn/end`，含 `reason`）、`:1096-1112`（有可见前缀才 commit `assistant/message` + `interrupted: true`）、`:1001-1007`（关轮前 `serial` 派发 `agent/turn-stopping`）。
- **对 Voice Assistant 的含义**：语音侧判定「本轮被取消」的**唯一稳定方法**是等 `turn/end` 的 reason，或用 `assistant-stream` 的 abandoned 帧做快速路径。若只听 abandoned，会遇到「无可见内容」的取消（此时不会 commit `assistant/message`）——所以两者都要处理。

### 8.3 steer 的语义

- **结论**：`agent.steer(message)` 提交「最近一个 step 的输入」：idle 时它会**开启**一个 turn；running 时在**下一个 step 边界**被消费。被拒绝的 step 会让 steering **留在 inbox** 等到下次唤醒；取消或 dispose 可能丢弃 pending steering。`inject(message)` 则是「不唤醒 driver 的模型可见上下文」，running 时在最近的下一个 step 边界被取用，idle 时一直挂着。`followup(message)` 会排队成**独立的下一轮**并唤醒 driver。
- **证据**：`P\dsh-agent\lib\types\runtime-types.d.ts:191-209`（三个方法的逐条注释：`:192-199` steer、`:209` inject、`:186-191` followup）；`:41-82`（`Inbox` 结构与 `nextTurn`/`nextStep` 两个列表）；`P\dsh-agent\README.md:47`（三个方法的一句话总结）。
- **对 Voice Assistant 的含义**：
  1. 「用户中途补充一句」应映射到 `steer`（在同轮内生效，符合「语音插话」的直觉）；若用户在 Agent 已完成后说话，则 `steer` 会自己开新轮，行为与 followup 近似。
  2. 「本轮附加上下文」（例如把用户环境/当前页面信息塞进去）用 `inject`，不会打扰 driver 的节流。

### 8.4 `keepInbox` 在真实代码里的用法差异（重要先例）

- **结论**：DSH 官方 GUI 的「停止」按钮走 `sessionController.cancel`，它**强制 `keepInbox: true`**；而微信通道的 `/stop` 走 `agent.cancel({ kind:'user' })`（**清空 inbox**）。两种都是合法产品选择，但语义不同。
- **证据**：
  - GUI/Remote 路径：`P\dsh-api-session-controller\lib\types\commands.js:451-460`（`cancel(request)`），其中 `:459` `agent.cancel({ kind: 'user' }, { keepInbox: true })`；桌面版同实现：`R\dsh-api-session-controller\lib\types\commands.js:466`（`cancel(request)`）+ `:474`（同一行 `keepInbox: true`），以及 Controller 的公开面 `R\dsh-api-session-controller\lib\index.js:1061-1065`。
  - 语义声明：`P\dsh-api-session-controller\lib\types\index.d.ts:151-156`（「Cancel one active Agent turn without dropping its pending inbox」）。
  - 通道路径：`Q\dsh-channel-wechat\lib\index.js:5535-5542`（`agent.cancel({ kind: "user" })`，无 options）。
- **对 Voice Assistant 的含义**：语音「停止」默认应对齐 GUI（`keepInbox: true`），并在文档里说明与「清空队列」是两个动作；不要因为微信先例而默认清空。

---

## 9. UI 扩展：Host vs Client、Slot、设置页、面板、命令

### 9.1 Host 与 Client 的边界（两条独立 Cordis 树）

- **结论**：DSH 的 UI 扩展跑在**浏览器里的第二条 Cordis 运行时**上，与 Host 完全隔离：Client 插件是**另一个入口文件**（包导出 `<pkg>/client`），由 `package.json.dsh.client` 声明，由 `dsh-client-modules` 组装成 `window.__DSH_BOOT__` 图，再由页面的 Loader 加载。Client 与 Host 之间**没有**直接对象共享，只有 ①Remote（Typert 生成的 `ctx.remote.*`）②`connection`/`fetch` ③宿主注入的 HTML 行。
- **证据**：
  - Client 清单：`P\dsh-package-manifest\lib\types\types.d.ts:39-52`（`platform` / `inject` / `immediately` / `external`）。
  - 启动图与加载器：`P\dsh-client-modules\lib\types\client\manifest.d.ts:46-59`（`WebBootEntry`：id=包名、url、rev、inject、immediately、external）、`:74-85`（`WebBootGraph`）、`:110-118`（`BootManifest`）、`:147-157`（`ClientBundleRegistration`：`window.__ModuleLoader__.load({ id, factory })`）、`:175-184`（`ClientModuleLoaderTarget`：queue→live 的注册门面）、`:186-191`（`DshWindow`：`__DSH_BOOT__` + `__ModuleLoader__`）、`:208-246`（`ClientModuleLoader`：`import/prefetch/invalidate`）。0.2.1 实证：`R\dsh-client-modules` 的 `lib/*.js` 中 `__ModuleLoader__` 出现于 page-global facade 与 boot 注入处（`Select-String` 命中行 1/17/693/758）。
  - 加载顺序的事实：`P\dsh-client-modules\lib\types\client\manifest.d.ts:9-25`（bundle 执行只**注册 factory**，模块体副作用——包括 CSS 注入——在 factory 内、materialize 时才跑；`require` 走同一张表并递归 materialize）。
  - 真实双半包：`Q\dsh-channel-wechat\package.json:30-36`（`"./client": "./lib/client.js"` 导出）、`:52-62`（`dsh.client.platform = "web"`），Host 入口 `lib/index.js`、Client 入口 `lib/client.js`。
  - 只有 Host 的插件：`Q\dsh-video-skin\package.json:6-10`（`main: index.js`，无 `dsh.client`），靠 `webserver/index-inject` 注入脚本（`Q\dsh-video-skin\index.js:201-216`）。
- **对 Voice Assistant 的含义**：
  1. 语音插件若要「点麦克风说话」「在设置页调音色」，必须出 **Client 半边**；若要「把识别结果变成 Agent 消息」，必须出 **Host 半边**。两侧通过 Remote（DSH 生成）或插件自建 HTTP/WS 通信。
  2. Client 半边**不能** `import` Host 的 `ctx.agents`——跨不过去。

### 9.2 Client 插件形态与 Slot 注册（真实可用 API）

- **结论**：
  - Client 插件的模块导出：`{ inject?: string[], apply(ctx) }`（与 Host 同形，但跑在浏览器）。
  - Slot 注册签名（0.2.1 实测的真实形态）：`ctx.slots.register(options, Component)`，`options` 含 `name`（Slot key）、`id`（list slot 内唯一/用于 `entries()` 读出）、`order`、`label`（函数，返回本地化标题）、`locale`（字典命名空间）、`inject`（函数，返回注入给组件的 `hooks` 与动作）、`children`（声明子 Slot 及其 `kind`/`scope`）。
  - `ctx.slots.inject(key, cb)` 用于「等 Slot 声明存在后再注册」；`ctx.slots.entries(key)` / `subscribe(key, fn)` / `getVersion(key)` 用于读取/订阅。
  - 本地化：`ctx.locale.register(ns, { zh, en })`、`ctx.locale.bind(ns)`。
- **证据**：
  - 注册 API 的类型面：`P\dsh-client-ui-renderer\lib\types\client\registry.d.ts:46`（`class SlotRegistry extends Service`）、`:84`（`readonly register: SlotCore['register']`）、`:100`（`inject(key, callback)`）、`:154`（`entries(key)`）、`:164`（`entriesOfSlot`）、`:190`（`spec`）、`:197`（`subscribe`）、`:203`（`getVersion`）、`:182`（`onEntryError`）、`:170`（`snapshot`）。
  - 真实注册（0.2.1 内置插件）：`R\dsh-client-ui-settings-plugins\lib\client.js:162`（`const inject = ["slots", "locale"]`）、`:169`（`ctx.locale.register(NS, { zh, en })`）、`:201-212`（`ctx.slots.inject("settings.section", () => ctx.slots.register({ name:"settings.section", id:"plugins", order:15, label:()=>t("nav"), locale:NS, inject: sectionInjected, children: { "settings.plugins.tab": { kind:"list", scope:"root" } } }, PluginsSettingsSection))`）、`:183`（`ctx.slots.entries("settings.plugins.tab")`）、`:193`（`ctx.slots.subscribe(...)`）。
  - 真实注册（第三方，0.2.x）：`Q\dsh-channel-wechat\lib\client.js:1089`（`inject: ['slots','locale','configForms']`）、`:1092`（`ctx.locale.register(LOCALE_NS, DICT)`）、`:1107`（`ctx.locale.bind(LOCALE_NS)`）、`:1123-1145`（`ctx.configForms.whileServed([NS], () => ctx.slots.inject('plugins.bundle.config', () => ctx.slots.register({ name:'plugins.bundle.config', key: PLUGIN_ID, locale: LOCALE_NS, inject: () => ({ hooks, ...actions }) }, WechatPage)))`）。
  - 样式标签约定：`Q\dsh-channel-wechat\lib\client.js:1097-1105`（`<style data-plugin data-plugin-css>`，插件卸载时移除）。
- **对 Voice Assistant 的含义**：
  1. 「设置页」有两条不同 Slot：`settings.section`（Settings 侧栏的**一个页面**，0.2.1 内置插件用）与 `plugins.bundle.config`（**插件详情页**里的配置面板，wechat 用；key 必须等于 bundle 包名，否则「注册了但永不渲染且不报错」——`Q\dsh-channel-wechat\lib\client.js:1119-1122` 明确记录了这个坑）。
  2. `ctx.configForms` 在 `P\`（0.1.5）里**不存在**，只在 0.2.x 的 Client 面存在（§1.1 分歧）→ 语音插件若要在插件页嵌表单，必须 `engines.dsh >= 0.2.0-rc.1`，或用更稳的 `settings.section`。
  3. 任何 Client 插件都必须自己管样式（`<style data-plugin>`）与本地化字典，DSH 不提供 CSS 注入 API。

### 9.3 更轻的 UI 扩展：`webserver/index-inject`（无需 Client 插件）

- **结论**：不写 Client 插件也能改页面外观：监听 `webserver/index-inject`，往 `table` 里 push `IndexInjection` 行（`kind: 'script' | 'script-src' | 'style' | ...`）。`dsh-video-skin` 就是这么做的（视频背景 + 开机动画）。
- **证据**：`P\dsh-host-webserver\lib\types\index.d.ts:20-27`（事件与可变 table）、`P\dsh-host-webserver\lib\types\injections.d.ts`（`IndexInjection` 与 `IndexInjectionPlacement` 定义，同包 `:13-14` 再导出）；真实用法 `Q\dsh-video-skin\index.js:201-216`、行构造 `Q\dsh-video-skin\lib\injections.js`（`buildInjectionRows`）。
- **对 Voice Assistant 的含义**：语音「悬浮球/波形条」这类纯视觉层可以用注入行实现（零 Client 插件、零构建）；但一旦需要与 Host 交互（把识别文本送进 composer），就必须 Client 插件（注入行拿不到 Cordis 服务）。取舍应写进 ARCHITECTURE。

### 9.4 命令（斜杠命令）作为 UI 入口

- **结论**：命令是「Human-command registry」：`ctx.commands.register({ name, description, input?, recordInput?, handler })`，`handler` 收到 `{ commandId, agent, rawInput, attachments, signal }`，返回 `{ kind:'success'|'error', text? }`。**不经模型**，执行前后自动写 `command/run` / `command/done`。
- **证据**：`P\dsh-commands\lib\types\index.d.ts:18-35`（`CommandInvocation`）、`:37-52`（`CommandDefinition`）、`:114-139`（execute 的生命周期日志与附件准入）；真实用例：`Q\dsh-channel-wechat\lib\index.js:6762-6775`（把命令路由到 `executeNative`，用 `this.peers.sessionFor(peerId)).agent` 拿 agent）。
- **对 Voice Assistant 的含义**：`/voice on|off|status` 用命令实现最省事（GUI 与语音共用同一实现），且天然带审计事件。

### 9.5 三个目标 Slot 的实测声明（0.2.1）与会话作用域

- **结论**：语音 UI 需要的三个 Slot 都真实存在；`settings.section` 是 root 作用域，另外两个是**会话作用域**：

| Slot key | kind | scope | 证据 |
|---|---|---|---|
| `settings.section` | **list** | root | 声明 `R\dsh-client-ui-settings-general\lib\client.js:1264-1267`（`"settings.section": { kind: "list", scope: "root" }`）；注册用法 `R\dsh-client-ui-settings-plugins\lib\client.js:201-212`（`ctx.slots.register({ name:"settings.section", id, order, label, locale, inject, children })`） |
| `conversation.composer.dock` | **list** | **session** | 声明 `R\dsh-client-ui-conversation\lib\client.js:20113-20116` |
| `conversation.input.right` | **list** | **session** | 声明 `R\dsh-client-ui-conversation\lib\client.js:20101-20104` |

- **会话作用域 Slot 如何拿到 sessionId**：**框架把 `sessionId` 作为 `inject` 的参数传进来**——`R\dsh-client-ui-conversation\lib\client.js:19963`（`inject: (sessionId) => ({ hooks: { composerBlock: sessionId === void 0 ? ABSENT_BLOCK : composerBlocks.storeFor(sessionId) }, ... })`）与 `:20118`（`inject: (sessionId) => { if (sessionId === void 0) return {...} ... }`）。所以插件**不需要自己上报 sessionId**；在 `inject(sessionId)` 里用它即可。
- **真实注册样例（可直接照抄的形态）**：`R\dsh-experimental-client-ui-voice-input\lib\client.js:2919-2922`（`ctx.slots.inject("conversation.input.activity", () => ctx.slots.register({ name:"conversation.input.activity", ... inject: () => actions }, Component))`）、`:2924-2928`（`plugins.bundle.config`）、`:2930-2934`（`plugins.bundle.activation`）。
- **同一父级下的其他 Slot（便于选点）**：`conversation.composer`（chain/session，`:19930-19933`）、`conversation.composer.bar`（single/session-maybe，`:19934-19937`）、`conversation.input.dock`（list/session，`:19938-19941`）、`conversation.input.plan` / `.model` / `.activity`（single/session，`:20097-20112`）。
- **`plugins.bundle.config` 的声明方已确认**：`R\dsh-client-ui-plugin-manager\lib\client.js:4440`（SlotMap 增补）、渲染点 `:2964`（`renderSlot("plugins.bundle.config", { view:"page" }, { entryKey: pkg.name })`）→ key 必须等于 **bundle 包名**。
- **对 Voice Assistant 的含义**：
  1. 麦克风按钮应注册进 `conversation.input.right`（list/session）；**不要**用 `conversation.composer.bar`（single，会被覆盖），也不要抢 `conversation.input.activity`（内置语音输入已占用）。
  2. **sessionId 上报方案**：Host 侧拿不到「当前会话」（§11.1），但 **Client 侧的 session 作用域 Slot 能拿到 sessionId**。推荐：Client 插件在 `inject(sessionId)` 里把 sessionId 通过插件自己的 Remote/HTTP 上报给 Host，Host 用它作为 `boundSessionId`。这是把 §11.1 的「策略 A/C」落地的最短路径。
  3. 若需要「随会话切换的语音状态」（每会话一个语音开关），把状态挂在 session 作用域 Slot 的 `hooks` 上，而不是全局单例。


---

## 10. 插件权限/审批、配置 schema、生命周期、HMR

### 10.1 插件本身**没有**权限声明字段

- **结论**：`DshManifest` 与 Cordis 的 `Plugin.Base` 都**没有** `permissions` / `capabilities` 字段。DSH 的权限模型是**会话级**的两个旋钮：`sandbox` 模式 + `approval` 策略，由 `permissionPresets` 组合成「预设」，按 **session** 生效（可覆盖），不是按插件生效。插件只能①使用 `ctx.approval.request()` 主动询问，②在 `tools/pre-execute` 里返回 `{ kind:'ask' }` 让工具调用走审批。
- **证据**：
  - 无权限字段：`P\dsh-package-manifest\lib\types\types.d.ts:7-23`（`DshManifest` 全部键）；`P\cordis\lib\types\registry.d.ts:52-63`（`Plugin.Base` 全部键）。
  - 会话级预设：`P\dsh-permission-presets\lib\types\index.d.ts:21`（`permissionPresets`）、`:158`（`set(session, name)`）、`:38`（`permission/preset` 事件）、`:95`（`defaultPreset`）。
  - 审批：`P\dsh-user-approval\lib\types\index.d.ts:46`（`ApprovalPolicy = 'ask' | 'never'`）、`:108`（`setPolicy(agent, policy)`）、`:127`（`request(req)`，`:122-126` 注释：`allowed-once` 是唯一放行）、`:26-31`（`approval/policy` 事件）；工具侧 `ask`：`P\dsh-tools\lib\types\index.d.ts:419-427`（`PreToolDecision`）、`:781-792`（`serviceAsk`：没有 approval 服务时 `ask` **降级为 deny**，失败关闭）。
  - **answerer 的真实入口（0.2.1 已证实）**：审批问题是一个名为 **`approval/request`** 的 waterfall 事件——`R\dsh-user-approval\lib\index.js:176`（`this.ctx.waterfall(scopeTarget(req.agent, req.agent), "approval/request", req, () => Promise.resolve("unavailable"))`）；合法返回值只有 4 个：`R\dsh-user-approval\lib\index.js:30-35`（`OUTCOMES = ["allowed-once","rejected","cancelled","unavailable"]`），非法值被归一化为 `"unavailable"`；没有 answerer 时默认就是 `"unavailable"`（失败关闭）。会话级日志事件是 `approval/asked` / `approval/decided`：`:132`、`:139`。
- **对 Voice Assistant 的含义**：
  1. 语音**不能**绕过权限：`agent.followup()` 触发的工具调用仍受该 session 的 sandbox + approval 约束（AGENTS.md 规则 5「Never bypass DSH permissions」因此天然满足）。
  2. 语音侧的「危险操作需确认」应利用 `ask` → GUI/语音卡片回答，而**不是**自己在插件里写确认逻辑后再绕过审批。
  3. 若要让语音通道**直接回答**审批（说「可以」= 放行一次），实现方式是 `ctx.on('approval/request', async (req, next) => ...)`：自己处理时返回 `'allowed-once' | 'rejected' | 'cancelled'`（不要调 `next()`），否则 `return next()` 交回 GUI。**注意**：`allowed-once` 只对该次调用有效；语音回答必须能关联到具体 `req.agent` 与 `req.callId`（`P\dsh-user-approval\lib\types\index.d.ts:60-81` 的 `ApprovalRequest` 字段），否则会造成「一次同意、处处放行」的错觉。
  4. **安全边界（本项目决策）**：语音 answerer 只允许 L1/L2 且必须带「操作短码 + 明确确认短语 + TTL」；L3（sudo、磁盘、系统关键配置）**必须保留屏幕确认**，语音只播报、不返回 `allowed-once`。任何模糊词（「好」「可以」「都行」「你看着办」）一律不批准；`req` 与 `sessionId + callId + args hash` 不一致时 `return next()`。这条比「语音可以直接回答」更严格，优先级高于 §527 的通用能力描述。

### 10.2 配置 schema（schemastery）与默认值

- **结论**：`Config` 用 `@deepseek-ai/schemastery` 的 `z` 定义；Loader 在 fiber 启动前校验（`resolveConfig`），失败则该 fiber 进入 `FAILED` 并报错。GUI 可编辑性由 `Volatile<T>` 决定。`Config` 也可由 patch 层覆盖（整行替换）。
- **证据**：`P\cordis\lib\types\fiber.d.ts:31`（`resolveConfig`）、`:24-29`（`ValidationError`）、`:157`（effect 前的校验时机）；`Q\dsh-channel-wechat\lib\index.d.ts:114-132`（真实 `Config` 声明形态）、`:19-33`（`Volatile` 的语义）、`:42-55`（`Volatile<string>` / `Volatile<'wechat'|'both'>`）。
- **对 Voice Assistant 的含义**：Runtime 地址、端口、音色选择等都要有 schema 默认值（`z.string().default(...)`），否则用户 patch 不写就 undefined；不要把「端口」写成固定值（AGENTS.md 规则 3 禁止硬编码端口）。

### 10.3 生命周期（fiber 状态机 + effect 逆序释放）

- **结论**：fiber 状态：`PENDING`（等服务）→ `LOADING` → `ACTIVE`，或 `FAILED`；卸载时 `UNLOADING` → `DISPOSED`（不可重启）。`ctx.effect()` 收集的 disposer 在卸载时**逆序**执行；`ctx.on()` 注册的监听器本身也是一个 effect，随 fiber 卸载自动移除。`fiber.update(config)` 会先跑 `internal/update` waterfall（HMR/持久化可 veto），再重启插件。
- **证据**：`P\cordis\lib\types\fiber.d.ts:59-74`（`FiberState` 全枚举与注释）、`:157`（effect）、`:41-40`（`Disposable` 逆序）、`:199`（update）、`:187`（restart）、`:180`（await，重抛启动错误）；`P\cordis\src\events.ts:254-260`（`register` 把监听器包成 effect）、`:294`（`on()` 里 `assertActive`）。
- **对 Voice Assistant 的含义**：所有「连接 Runtime」的动作必须可重复执行且可逆（幂等 connect / 幂等 close）；`FAILED` 状态不会自动重试，因此连接失败不要 `throw`（应记日志并重试），否则整个语音插件变成 FAILED。`dsh-video-skin` 的「任何一步出错只 warn 并跳过」正是这个原则（`Q\dsh-video-skin\index.js:18`）。

### 10.4 HMR 的两侧

- **结论**：Host 侧 HMR 是 `cordis-plugin-hmr`（或桌面版的 `dsh-hmr`），Client 侧是 `dsh-client-hmr`，两者都是**开发期**能力；`patchReload: 'live'` 时用户 patch 文件变化会在长驻进程中生效。生产插件不应依赖 HMR 语义。
- **证据**：`P\cordis-plugin-hmr\README.md:1-14`、`:48-53`；运行时 [I] `include:client-hmr` → `@deepseek-ai/dsh-client-hmr`；`P\dsh-package-manifest\lib\types\types.d.ts:36-37`。
- **对 Voice Assistant 的含义**：开发期可用 HMR 快速迭代插件代码；但 Python Runtime 的代码改动**不会**被 HMR 感知，必须显式重启（写进 DEVELOPMENT.md）。

---

## 11. 对 Voice Assistant 的 `DshAgentBridge` 映射建议

> 任务书第 556–572 行要求定义 `getActiveSession / sendMessage / steerMessage / cancelCurrentTurn / subscribe`，且「具体实现必须映射到经过源码核实的 DSH 官方 API」。

### 11.1 `getActiveSession()`

- **结论（明确缺口）**：Host 侧**没有**「当前活动会话」这个 API——没有 `agents.activeSession()`、没有 `sessionController.current()`、没有 `currentSessionId`。这是一个**必须由 Voice 插件自己定义的策略缺口**，不是「我们还没找到」。可行的三种真实映射：
  - **A（推荐，语义最接近 GUI）**：`ctx.sessionController.list({})` 拿 `SessionSummary[]`（含 `running`、`updatedAt`、`cwd`、`agentPreset`），再取 `running === true` 或 `updatedAt` 最大的那条，最后 `ctx.sessionController.resolveAgent(sessionId)` 或 `ctx.agents.get(sessionId)` 得到 `Agent`。
  - **B（最轻）**：`ctx.agents.roots()`（无父的顶层 agent）+ `agent.status` 过滤。
  - **C（显式绑定，工程最稳）**：语音插件自己持久化一个 `boundSessionId`（settings namespace 或 storage），由用户/GUI 命令显式选择；**不猜测**活动会话。
- **证据**：
  - `list`：`P\dsh-api-session-controller\lib\types\index.d.ts:73`（`list(request, signal)`）、`P\dsh-api-session-controller\lib\types\types.d.ts:145-154`（`SessionSummary`，含 `running: boolean`）。
  - `resolveAgent`：`P\dsh-api-session-controller\lib\types\index.d.ts:59`；其内部去重与 resume 策略：`P\dsh-api-session-controller\lib\types\agent.d.ts:66-95`（`resolveAgent` / `ensureSession`）。
  - `agents.roots()`：`P\dsh-agent\lib\types\index.d.ts:362`。
  - **反证（强证据）**：在 `R\` 的 4 个相关包（`dsh-agent`、`dsh-agent-loop`、`dsh-session`、`dsh-api-session-controller`）全部 `*.js` 中检索 `activeSession` / `currentSessionId` / `currentSession`，**命中 0 条**（命令记录见 §14.3）；`P\`（0.1.5）全树同样无此声明；Host [I] 服务目录也无此键。
  - **补充（本次 Inspect 实测，推荐 D）**：Client 的 session-scoped Slot 有 `sessionId` 这个 standardProp。实测 `cordis_inspect_query(platform:'client', provider:'Slots', method:'listSubTree', input:{root:'conversation.composer.dock'})` 返回 `standardProps` 含 `sessionId: SessionId`；`conversation.input.right` 同理。让 Client 半侧挂一个零渲染/极轻组件，在挂载与切换时把 `sessionId` 上报 Host，是语义上最接近「用户当前在看哪个会话」的方案（不依赖 `updatedAt` 猜测）。
    - 证据：`cordis_inspect_query` 的 `Slots.listSubTree` 结果（2026-10-30，本机运行中的 Host）；`R\dsh-client-ui-renderer\lib\types\client\registry.d.ts` 的 Slot 注册类型面。
    - 代价：Client 半侧必须存在；纯 Host/无页面场景仍需 C 或 A 回退。
- **对 Voice Assistant 的含义**：任务书 §九 的「默认 active-session 策略」在 Host 侧需自己实现语义；建议 **D（Client 上报）为主 + C（固定绑定）为兜底 + A（最近活动）为无页面回退**，并把「无法确定活动会话」做成显式状态（语音提示「请先在界面选择一个会话」），而不是静默绑定第一个。

### 11.2 `sendMessage(text)`

- **结论**：两种官方等价路径：
  - **Host 直连（推荐给语音插件）**：`ctx.agents.get(sessionId)` → `agent.followup(createUserMessage({ content: [{ type:'text', text }], source: { kind:'user' } }))`。
    ⚠️ **0.2.1 的类型修正**：运行中的 0.2.1-rc.3 `MessageSourceMap` 只有 `user` / `model` / `tool` / `system-prompt`，**没有** 0.1.5 里的 `plugin` 变体（`R\dsh-llm\lib\types\message.js` 的 source 类型已被裁剪；`R\dsh-agent-instructions\lib\index.js` 用 `kind:'agent-instructions'` + 模块增补自行扩展）。因此：
    - 最稳妥：`source: { kind:'user' }`（与 dsh-channel-wechat 的做法一致，`Q\dsh-channel-wechat\lib\index.js:5062`）；
    - 若要保留「语音来源」标记：在本插件自己的 `.d.ts` 里 `declare module '@deepseek-ai/dsh-llm' { interface MessageSourceMap { 'voice-assistant': { kind:'voice-assistant'; plugin:'dsh-voice-assistant' } } }`，运行时 `session.append` 只做 JSON 校验，自定义 `kind` 可保留；但这依赖「source 是 merge-extensible」的未写死契约，**P5 先用 `user`，再评估增补**。
  - **走 Remote 业务层（与 GUI 完全同构）**：`ctx.sessionController.prompt(...)` → 返回 `{ accepted: true }`。它会做「模型可路由性检查、附件准入、去重（同 requestId 幂等）、fileUploads 绑定」等更安全的校验。**但它不是稳定第三方 API**：0.1.5 的类型是 `prompt(request, signal)`，0.2.1 的实现是 `prompt(request, source)`——第二个形参从「取消信号」变成了「要写进消息的 `user-rpc` source」，由 Remote 层负责构造。语音插件若直接调用，必须自己构造 source 且随版本漂移。
- **证据**：
  - `followup`：`P\dsh-agent\lib\types\runtime-types.d.ts:186-192`；消息构造：`P\dsh-llm\lib\types\message.d.ts:180-183`（`createUserMessage`）、`:94-104`（`MessageSourceMap`：`user` / `plugin` / `model` / `tool`；`plugin` 需 `plugin: string` 且可带 `form`）。0.2.1 实现：`R\dsh-agent-loop\lib\index.js:806-808`（`followup(input) { this.send(input, "next-turn", true) }`）。
  - `prompt`：0.1.5 类型 `P\dsh-api-session-controller\lib\types\index.d.ts:132-138`；请求体 `P\dsh-api-session-controller\lib\types\types.d.ts:291-300`；0.2.1 实现 `R\dsh-api-session-controller\lib\index.js:925`（`async prompt(request, source)`）、`R\dsh-api-session-controller\lib\types\commands.js:302`（同样的 `prompt(request, source)`，注释 `:295-301` 明确「the Remote method has already validated the content and built the durable message source」）、`:325-328`（`mode === 'steer'` → `agent.steer(message)`，否则 `agent.followup(message)`）、`:304-305`（`hasPromptRequest` → 直接 accepted，请求级幂等）。
  - 真实先例：`Q\dsh-channel-wechat\lib\index.js:5073-5076`（`deliverInbound` → `agent.followup(buildUserMessage(input))`，并在投递前做 `isLive` 检查）。
- **对 Voice Assistant 的含义**：
  1. 用 `source: { kind:'user' }`（0.2.1 的稳定变体）；若后续在插件内做 `MessageSourceMap` 增补，再用 `{ kind:'voice-assistant', plugin:'dsh-voice-assistant' }` 区分「语音输入」与「键入」，且不冒充人类。若产品要求完全等价于手打，`user` 也是正确选择（wechat 就这么做：`Q\dsh-channel-wechat\lib\index.js:5062`）。
  2. 投递前必须做 liveness 检查（`ctx.agents.get(id) === agent`），否则消息会被接受后静默丢弃（wechat 的注释 `Q\dsh-channel-wechat\lib\index.js:5070-5071` 明确记录了这一点）。

### 11.3 `steerMessage(text)`

- **结论**：`agent.steer(createUserMessage(...))`；或 `sessionController.prompt({..., mode:'steer'})`。语义差异见 §8.3（idle 时 steer 会开新轮）。**注意**：`sessionController.updateQueue` 里的 `action: 'steer'` 是「把**已排队**的消息改成 steering」，不是发新消息（`P\dsh-api-session-controller\lib\types\commands.js:436-439`、`:418-420` 还要求 `target === 'next-turn'` 且 `agent.status === 'running'`，否则 `session/steer-unavailable`）。
- **证据**：`P\dsh-agent\lib\types\runtime-types.d.ts:200`；`P\dsh-api-session-controller\lib\types\types.d.ts:296`（`mode: 'queue' | 'steer'`）、`:135-143`（`QueueAction`）。
- **对 Voice Assistant 的含义**：语音「插话」用 `steer` 即可；若用户说的是「把刚才那句改一下」，才需要 `updateQueue({action:'edit'})`。

### 11.4 `cancelCurrentTurn()`

- **结论**：`agent.cancel({ kind: 'user' }, { keepInbox: true })`（对齐 GUI）或 `sessionController.cancel({ sessionId })`（同样是 keepInbox: true）。`cancel` 无返回值、无专属事件；结果通过 `turn/end.reason.kind === 'aborted'` / `assistant/message.interrupted` / `assistant-stream end.outcome = abandoned` 观察（§8.2）。
- **证据**：`P\dsh-agent\lib\types\runtime-types.d.ts:157`；`P\dsh-api-session-controller\lib\types\commands.js:459`（`keepInbox: true`）；`R\dsh-api-session-controller\lib\types\commands.js:474`（桌面版同实现）、`R\dsh-api-session-controller\lib\index.js:1061-1065`（Controller 公开面）。
- **对 Voice Assistant 的含义**：`cancelCurrentTurn()` 应在**至少一次**状态确认后才回复用户「已停止」（等 `agent/status` 变 `idle` 或 `turn/end`），否则会出现「说停了但还在念」的竞态——因为 cancel 是异步收敛的。

### 11.5 `subscribe(handler)`

- **结论**：需要订阅三类，缺一不可：
  1. **增量**：`ctx.on('agent/assistant-stream', ({ agent, frame }) => ...)`，先按 `agent.id` 过滤；只吃 `chunk.type === 'text-delta'` 与 `block-end`。
  2. **事实**：`ctx.on('session/event', (session, event) => ...)`，取 `assistant/message`（最终文本 / `interrupted`）、`turn/start` / `turn/end`（轮次边界与结束原因）、`tool/call` / `tool/result`（工具状态播报）。
  3. **状态**：`ctx.on('agent/status', ({ agent, status }) => ...)`（忙闲、桌宠状态）。
  可选：`agent/error`（失败播报）。**不要**监听 `agent/pre-step` / `agent/request` 做语音逻辑。
- **证据**：`P\dsh-agent\lib\types\runtime-types.d.ts:375`（assistant-stream）、`:247`（status）、`:411`（error）；`P\dsh-session\lib\types\index.d.ts:62`（session/event）；0.2.1 实现：`R\dsh-agent-loop\lib\index.js:1079-1081`（assistant-stream emit）、`:794-799`（agent/status emit）、`R\dsh-session\lib\index.js:1587`（`session/event` 发布）、`:1910`（`session/created`）、`:1956`（`session/flush`）；真实先例：`Q\dsh-channel-wechat\lib\index.js:6711-6737`（只订阅 `session/event`，并在 `onSessionEvent` 里过滤 `assistant/message`）、`:5097-5109`（判断「带 tool 的 assistant/message 是旁白而不是答案」这一重要经验）。
- **对 Voice Assistant 的含义**：`subscribe(handler)` 应返回**幂等 disposer**，且在插件 `ctx.effect` 内注册（否则重载后叠加多份 → 一句话念两遍）。多会话时必须按绑定 session 过滤。

### 11.6 映射总表

| Bridge 方法 | 首选真实 API | 备选 | 关键风险 |
|---|---|---|---|
| `getActiveSession()` | Client Slot 上报的 `sessionId`（D）+ `ctx.agents.get(id)`；或自有 `boundSessionId`（C） | `ctx.sessionController.list()` 取 `running/updatedAt`；`ctx.agents.roots()` | Host 无「活动会话」概念；猜测会绑错会话 |
| `sendMessage(text)` | `agent.followup(createUserMessage({content, source:{kind:'user'}}))`（0.2.1 稳定） | `ctx.sessionController.prompt(...)`（**签名随版本变化，见 §11.2**） | 未做 liveness 检查会静默丢消息 |
| `steerMessage(text)` | `agent.steer(createUserMessage(...))` | `prompt({mode:'steer'})` | idle 时 steer 会开新轮（可能非预期） |
| `cancelCurrentTurn()` | `agent.cancel({kind:'user'},{keepInbox:true})` | `sessionController.cancel({sessionId})` | 无返回值；结果需异步观测；默认会清 inbox |
| `subscribe(handler)` | `agent/assistant-stream` + `session/event` + `agent/status` | `sessionController.follow({assistantStream:true})`（Remote 流） | 帧是 process-local，不可重放；先按 agent.id 过滤 |

### 11.7 参考实现骨架（仅示意签名，不含业务）

```ts
// Host 半边，只读事实 + 官方 API，不引入第二套 Agent Brain
export function apply (ctx: Context, config: Config) {
  let bound: SessionId | undefined = config.sessionId
  const agentOf = (id: SessionId) => {
    const agent = ctx.agents.get(id)              // P\dsh-agent\lib\types\index.d.ts:341
    return ctx.agents.get(id) === agent ? agent : undefined   // liveness：同引用才算活着
  }
  const send = (text: string, mode: 'followup' | 'steer') => {
    const agent = bound && agentOf(bound)
    if (!agent) throw new Error('voice: no live bound session')
    const message = createUserMessage({ content: [{ type: 'text', text }], source: { kind: 'user' } })
    mode === 'steer' ? agent.steer(message) : agent.followup(message)
  }
  const cancel = () => bound && agentOf(bound)?.cancel({ kind: 'user' }, { keepInbox: true })

  ctx.effect(() => ctx.on('agent/assistant-stream', ({ agent, frame }) => {
    if (agent.id !== bound) return                  // 多会话必须过滤
    if (frame.type === 'chunk' && frame.chunk.type === 'text-delta') feedTts(frame.chunk.text)
  }))
  ctx.effect(() => ctx.on('session/event', (session, event) => {
    if (session.id !== bound) return
    if (event.type === 'assistant/message') settle(event.data.interrupted === true)
    if (event.type === 'turn/end') finish(event.data.reason)
  }))
  ...
}
```

---

## 12. 对 Voice Assistant 的架构结论（基于以上事实）

1. **Agent 执行核心唯一**：只能通过 `ctx.agents` / `ctx.sessionController` 驱动（不存在第二套 brain 的入口）。
2. **会话绑定必须显式**：Host 无「活动会话」概念（§11.1），必须持久化 `boundSessionId`，并在每次使用前做 `ctx.agents.get(id)` 同引用校验。
3. **播报数据源双通道**：`agent/assistant-stream`（低延迟、不可重放）+ `session/event` 的 `assistant/message`（最终、可重放）。句子切分必须自建（§7.3）。
4. **打断分层**：TTS 打断 ≠ Agent 取消（§8.1）；取消要等 `turn/end.reason` 收敛后再对用户宣称「已停止」（§8.2）。
5. **STT 优先复用**：桌面版已有 `ctx.speechToText`（整段、SenseVoice、可注册 provider），语音插件应通过 provider 注册扩展而不是自建并行 STT 通道（§1.2、§3.9）。
6. **Runtime 独立**：Runtime 的 HTTP/WS 不挂 DSH `webServer`（§3.5），DSH 侧只做「Host 插件 + 可选 Client UI」。
7. **无插件级权限**：权限只在会话级（sandbox + approval），语音不得绕过（§10.1）。
8. **UI 有两条路**：轻量视觉用 `webserver/index-inject`，需要交互则必须出 Client 半边（§9.1/9.3）。
9. **版本要按 0.2.x 规划**：`ctx.configForms`、`speechToText` 等只存在于 0.2.1-rc.3（§1.1、§9.2），`engines.dsh` 应写 `>=0.2.0-rc.1`。

---

## 13. 「不存在或未验证」的 API 清单（明确登记）

### 13.1 确认**不存在**（有反证）

| 声称/期望的 API | 结论 | 反证 |
|---|---|---|
| `ctx.agents`（任务书要求「重点验证」） | **存在**（不是不存在，特此澄清） | `P\dsh-agent\lib\types\index.d.ts:20` |
| `ctx.server` / `ctx.http` | 不存在 | §3.5；Host [I] 服务目录无此键 |
| `ctx.dispose()` | 不存在 | `P\cordis\lib\types\fiber.d.ts:8`（Context 只挑 `effect`）；dispose 在 `fiber` 上（`:112`） |
| `assistant-stream` / `session/assistant-stream` 事件 | 不存在；真实名是 `agent/assistant-stream` | §5 表；`P\dsh-agent\lib\types\runtime-types.d.ts:375` |
| `agent/turn-start`、`agent/turn-end`、`agent/step-start`、`agent/message` | 不存在（这些是 **session 事件**） | `P\dsh-session\lib\types\types.d.ts:249/260/265/281/309` |
| `agent/cancelled` 事件、`cancel()` 返回值 | 不存在 | §8.2；`P\dsh-agent\lib\types\runtime-types.d.ts:157` |
| `session.subscribe()` 方法 | 不存在（用 `ctx.on('session/event')` 或 `sessionController.follow`） | `P\dsh-session\lib\types\index.d.ts:103-293`（Session 类无 subscribe） |
| `agents.activeSession()` / `agents.current()` / `currentSessionId` | 不存在 | `R\` 的 `dsh-agent` / `dsh-agent-loop` / `dsh-session` / `dsh-api-session-controller` 全部 `*.js` 检索 `activeSession|currentSessionId|currentSession` **0 命中**（§11.1、§14.3） |
| 句子边界 / `sentence` 事件 / 分句工具 | 不存在 | §7.3 |
| 插件级 `permissions` 清单字段 | 不存在 | §10.1 |
| Host 侧 `ctx.slots` / `ctx.locale` / `ctx.uiRenderer` / `ctx.configForms` | 不存在（仅 Client） | §3.9；Host [I] 无此键 |
| `plugin.json` 清单 | DSH 不消费 | §2.1 |

### 13.2 存在但**本次无法完全验证**（待验证）

| 项目 | 状态 | 说明 / 下一步 |
|---|---|---|
| `ctx.speechToText` 的精确方法签名与 `SpeechProvider` 注册契约 | **已验证（0.2.1）** | `R\dsh-experimental-speech-to-text\lib\index.js:6/18`（服务）、`:35-51`（register）、`:64`（listProviders）、`:75`（follow）、`:143-157`（prepare/cancelPreparation）、`:163-171`（resolve）、`:178-198`（transcribe）。Provider 必须具备 `info.id` / `info.languages`（`:135`）、可选 `preparation`（`:42/146/156`）、`transcribe({audio,language}, signal)`（`:185-188`）。**仍未验证**：`info` 的完整字段、`Transcript` 的返回形状。 |
| `speechToText` 由哪一行/哪一包提供 | **部分验证** | 服务由 `R\dsh-experimental-speech-to-text` 的 `SpeechToText extends Service` 提供（`:6/18`）；它由 `R\dsh-experimental-voice-input-bundle\cordis.patch.yml:2-5` 的行 `speech-to-text` 挂载。但 [I] `Config.listConfigs`（198 行）里**没有**该行 → 说明该 bundle **当前未启用**，Host 里存在的是另一条路径（可能是桌面壳内置挂载）。**待验证**：桌面版是否在 Loader 之外直接栽了该服务。 |
| approval 的「answerer」注册 API（让语音通道回答审批卡片） | **已验证（0.2.1）** | 事件名就是 `approval/request`，waterfall：`R\dsh-user-approval\lib\index.js:176`；合法返回 4 值 `:30-35`；无 answerer 时默认 `"unavailable"`（同一行的默认 `next`）。语音侧注册方式见 §10.1 含义 3。 |
| `plugins.bundle.config` Slot 的声明方（哪个包 declare 了这个 key） | **已验证（0.2.1）** | `R\dsh-client-ui-plugin-manager\lib\client.js:4440`（SlotMap 增补）、`:2964`（渲染，`entryKey: pkg.name`）、`:32`（key 清单）。0.1.5（`P\`）无此包，故当时无法确认。 |
| Client 侧 Slot 树的运行时快照 | **待验证** | 本次 `cordis_inspect_query(platform: "client", provider: "Slots", method: "listSubTree")` 超时（10s），提示需要已连接页面。建议在浏览器打开 GUI 后重试，用其结果核对 `settings.section` / `plugins.bundle.config` / `shell.overlay` 的真实层级与 props。 |
| `shell.overlay` 等具体 Slot key 的完整目录 | **待验证** | 仅从 `P\dsh-client-ui-renderer\lib\types\client\registry.d.ts:19-37` 得知 `root` 与「shell.overlay 是 list slot、click-through」的文字说明，未拿到完整 SlotMap 声明表。 |
| 0.1.5 与 0.2.1 的 `agent/*` / `session/event` 是否有新增事件 | **待验证** | 已抽查 4 个关键点（`agent/assistant-stream` 的 emit 点 `R\dsh-agent-loop\lib\index.js:1080`、`cancel(..., {keepInbox:true})` 的 `R\dsh-api-session-controller\lib\types\commands.js:474`、`session/event` 的 `R\dsh-session\lib\index.js:1587`、`prompt` 的 steer/queue 分派 `R\dsh-api-session-controller\lib\types\commands.js:325-328`）两侧一致；**未**逐事件比对全量 Events 表。 |
| 桌面版是否把 `dsh-hmr` 与 `cordis-plugin-hmr` 视作同一实现 | **待验证** | [I] 中行名为 `@deepseek-ai/dsh-hmr`，而 `P\` 内包名为 `cordis-plugin-hmr`；行为描述一致但实现可能分叉。 |

---

## 14. 证据索引（便于复核的命令与文件）

### 14.1 包清单与版本

- `Get-ChildItem "C:\Users\lenovo\.dsh\profiles\node_modules\@deepseek-ai" | Select-Object Name,LinkType,Target`（Junction 指向 npm 全局安装）。
- `Get-Content -Raw "C:\Users\lenovo\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\package.json"` → `0.1.5-rc.1`。
- `Get-Content -Raw "D:\桌面\new_idea\.cache\dsh-asar\dsh\package.json"` → `@deepseek-ai/dsh-desktop-runtime@0.2.1-rc.3`（= `A:/dsh/package.json`）。
- `Get-ChildItem "R\" -Directory` → 307 个包；`P\` → 239 个包。

### 14.2 运行中 Host 的服务/配置（只读 Inspect）

- `cordis_inspect_query { platform: "host", provider: "Service", method: "listService" }` → 含 `agents`/`sessions`/`settings`/`sessionController`/`sessionProjections`/`speechToText`/`tools`/`commands`/`webServer`/`approval`/`permissionPresets`。
- `cordis_inspect_query { platform: "host", provider: "Config", method: "listConfigs" }` → 198 行，含 `dsh-video-skin`（absent）/`channel-wechat`（schema）等。

### 14.3 运行中 Host（0.2.1-rc.3）的行为核对（`R\`）

- 「无 active-session API」的检索（0 命中）：
  `Get-ChildItem -Path "$R\dsh-agent","$R\dsh-api-session-controller","$R\dsh-session","$R\dsh-agent-loop" -Recurse -File -Include *.js | Select-String -Pattern 'activeSession|currentSessionId|currentSession\b'`
  → 无输出（= 0 命中）。
- Agent 方法实现：`Select-String -Path "$R\dsh-agent-loop\lib\index.js" -Pattern '^\s+(send|followup|steer|inject|cancel|runMaintenance|whenIdle)\('` → `:800/:806/:809/:812/:815/:822/:870`。
- `ctx.agents` 注册表：`Select-String -Path "$R\dsh-agent\lib\index.js" -Pattern '^\s+(get|list|roots|create|resume)\('` → `:596/:614/:623`。
- assistant-stream 发布点：`Select-String -Path "$R\dsh-agent-loop\lib\index.js" -Pattern 'agent/assistant-stream'` → `:1080`。
- 取消语义：`Select-String -Path "$R\dsh-api-session-controller\lib\types\commands.js" -Pattern 'keepInbox'` → `:474`；公开面 `R\dsh-api-session-controller\lib\index.js:1061-1065`。
- 注入表：`Select-String -Path "$R\dsh-host-webserver\lib\index.js" -Pattern 'webserver/index-inject'` → `:524`（emit 处）。
- Slot 注册：`Select-String -Path "$R\dsh-client-ui-settings-plugins\lib\client.js" -Pattern 'slots.inject\(|slots.register\(|const inject = '` → `:162`、`:201`。

### 14.4 关键类型文件（`P\` 前缀，仅 0.1.5 有 `.d.ts`）

- `dsh-agent\lib\types\index.d.ts`、`dsh-agent\lib\types\runtime-types.d.ts`、`dsh-agent\lib\types\types.d.ts`、`dsh-agent\README.md`
- `dsh-session\lib\types\index.d.ts`、`dsh-session\lib\types\types.d.ts`
- `dsh-llm\lib\types\types.d.ts`、`dsh-llm\lib\types\assistant-stream.d.ts`、`dsh-llm\lib\types\message.d.ts`
- `dsh-api-session-controller\lib\types\index.d.ts`、`...\types.d.ts`、`...\commands.js`、`...\agent.d.ts`
- `dsh-tools\lib\types\index.d.ts`、`dsh-commands\lib\types\index.d.ts` + `types.d.ts`
- `dsh-host-webserver\lib\types\index.d.ts`、`dsh-settings\lib\types\index.d.ts` + `types.d.ts`
- `dsh-user-approval\lib\types\index.d.ts`、`dsh-permission-presets\lib\types\index.d.ts`
- `cordis\src\context.ts`、`cordis\src\events.ts`、`cordis\lib\types\fiber.d.ts`、`cordis\lib\types\registry.d.ts`
- `dsh-package-manifest\lib\types\types.d.ts`、`dsh-app-boot\lib\types\profile.d.ts`
- `cordis-plugin-include\lib\types\index.d.ts`、`cordis-plugin-loader\lib\types\config\entry.d.ts`、`cordis-plugin-hmr\README.md`
- `dsh-client-ui-renderer\lib\types\client\index.d.ts` + `client\registry.d.ts`、`dsh-client-locale\lib\types\client\index.d.ts`、`dsh-client-modules\lib\types\client\manifest.d.ts`

### 14.5 真实插件样例（`Q\` 前缀）

- `dsh-video-skin\{package.json, cordis.patch.yml, index.js}`
- `dsh-channel-wechat\{package.json, cordis.patch.yml, lib\index.d.ts, lib\index.js, lib\client.js}`

### 14.6 profile 配置

- `J\{package.json, cordis.yml, cordis.patch.yml}`
- `C:\Users\lenovo\.dsh\profiles\desktop\{package.json, cordis.patch.yml}`（`desktop` 是**当前运行**的 profile：`DSH_PROFILE=desktop`）

---

## 15. 本文件的审计边界（诚实声明）

- 本文件**没有**运行任何插件、**没有**安装/卸载/启用/禁用任何插件、**没有**修改 DSH 安装目录与任何 profile。本次审计只新建了本文与 `docs/research/` 目录，并在 `%TEMP%` 写过一个只读 asar 读取脚本 `C:\Users\lenovo\AppData\Local\Temp\dsh-asar\asar.js`（仅 `fs.readSync`，不解包、不写归档）。
- `R\`（`D:\桌面\new_idea\.cache\dsh-asar`）是**上级代理**为只读分析而解包的镜像，不是本审计解包的结果；本审计只是读取它。它是 `A:`（`app.asar`）的等价物，且可被 `Select-String`/`grep` 检索，因此所有 0.2.1 行号都引用它。
- `P\` 中只有 `cordis` 包自带 `src/*.ts`；其余包只有 `lib/*.js` 与 `lib/types/*.d.ts`，因此「实现细节」的证据以 `.d.ts` 注释 + 少量 `lib/*.js` 为准。
- 桌面版（0.2.1-rc.3）**没有** d.ts 随包发布，本文件对它的结论来自：随包 README、`lib/*.js`（含保留的 JSDoc）、以及 Host Inspect 的运行时目录。凡是这三者之外的推断，一律进 §13.2 的「待验证」。
- 未覆盖范围（不在任务 C 要求内，故未审计）：`dsh-acp`/`dsh-sdk-*` 的 ACP 与 SDK 协议、`dsh-subagent` 的委派协议、`dsh-mcp-client` 的 MCP 接入、CLI 子命令全集、`dsh-experimental-*` 语音子系统的完整实现（只核对了 README 与运行时服务目录）。
