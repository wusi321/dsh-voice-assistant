# dsh-pet 源码审计（任务 B）

> **审计对象**：`D:\桌面\new_idea\dsh-pet`（上游 GitHub：`PC2005-cloud/dsh-pet`）
> **审计 commit**：`38306ec`（完整 `38306ec87993fce3c0495933ba5d52f0e7bf1797`），标题 `feat(config): 新增桌宠人物占屏宽百分比（Refs #234）`，作者 `pc2005`，提交时间 `2026-10-30 20:21:36 +0800`
> **工作树状态**：`git status --porcelain` 输出为空；本次审计**只读**，未修改、未 checkout、未执行任何 git 写操作。
> **包版本**：`dsh-pet@0.3.8`，许可 `MIT`（`dsh-pet/LICENSE:1`、`dsh-pet/dsh-pet/package.json:2,99`）
> **审计时间**：2026-10-30 21:53 起（Asia/Shanghai，UTC+8），约 2 小时
> **审计方法**：`git log/status` → 逐目录读源码（`src/host/**`、`src/client/**`、`src/shared/**`、`src/standalone/**`、`src/app/**`、`runtime/electron-helper/**`）→ 读 `openapi.yaml` / `cordis.patch.yml` / `package.json` → 用 `grep` 交叉核对调用点与类型声明 → 文档与源码逐条互证。README / API.md / CORDIS.md **只作为线索**，凡与源码不一致处一律以源码为准并在第 15 节标出。
> **行号约定**：路径相对工作区根 `D:\桌面\new_idea`。包内源码形如 `dsh-pet/dsh-pet/src/host/voice/registry.ts:42`；仓库根文档形如 `dsh-pet/openapi.yaml:19`。
> **目录事实（先记住）**：本仓库**仓库根 ≠ npm 包根**。仓库根 `dsh-pet/` 放 `README.md`、`API.md`、`CORDIS.md`、`CORDIS-API.md`、`openapi.yaml`、`LICENSE`、`prompts/`、`tools/`、`scripts/`；真正发布到 npm 的包是**内层** `dsh-pet/dsh-pet/`（`package.json` 在那里）。
> **规模**：`src/**` 共 486 个 `.ts`（328 个实现 + 158 个同目录测试）；`host` 178、`client` 168、`shared` 94、`standalone` 41、`app` 5；桌面侧另有 28 个 `.js`（`runtime/electron-helper/`）。

---

## 0. 一页结论（TL;DR）

1. dsh-pet 是**纯展示型 Avatar 插件**：宿主只听 DSH 的 `session/event` 折叠出 6 档工作状态，**不调用 Agent、不建 Session、不发送用户消息**；它自己的"对话"走 `ctx.llm.stream()` 直连模型（`dsh-pet/dsh-pet/src/host/whisper.ts:142`、`dsh-pet/dsh-pet/src/host/chat.ts:2-6`）。因此**没有任何"Agent Bridge"能力可复用**。
2. 对外只有一个**前缀 HTTP 路由** `/dsh-pet-7340`，挂在 DSH 自己的 Web 服务上，**插件层零鉴权**（`dsh-pet/openapi.yaml:19`；`dsh-pet/dsh-pet/src/host/plugin/http-route.ts:72-113` 无任何凭据校验），端口 = `ctx.webServer.port`。
3. 数据是**单一出口 `GET /state`**：一份内存快照 S，`{counter, sections, pets}`；动作端点只回 `{ok}`，写进 S 由消费端 1s 长轮询发现（`dsh-pet/dsh-pet/src/host/state.ts:35-39`）。
4. **业务失败一律 HTTP 200 + `{ok:false, reason}`**，只有协议错误才用 400/405/413/500（`dsh-pet/dsh-pet/src/host/routes/result.ts:71-105`）。任何按 `res.ok` 判成败的客户端都会读错。
5. 有**占用锁（租约）**：per-pet 单槽，TTL 缺省 2 分钟、范围 1s~30min，**懒判过期、无定时器**，5 个动作端点需带 `?lock=`（`dsh-pet/dsh-pet/src/host/lock.ts:21-23,162-175`）。
6. 有**第三方 TTS Provider 注册**：Host 侧 Cordis 服务 `petApi7340.voice.register`，**单槽、后注册覆盖先注册**、返回 mp3 `Uint8Array`、单次 15s 超时、文本 ≤500 字符、串行队列上限 3（`dsh-pet/dsh-pet/src/host/voice/registry.ts:39-49`；`.../speak.ts:16-27`）。
7. TTS 播放**不在宿主**：`/voice/speak` 只产出 mp3 文件，播放由两端各自的 `HTMLAudioElement` 完成（`dsh-pet/dsh-pet/src/shared/voice.ts:151-175`）。与"Voice Runtime 独占播放"存在架构冲突。
8. 动画点播 `/anim` 只接受**该宠物配置池内的名字**或 **http(s) `url`**（`dsh-pet/dsh-pet/src/host/anim.ts:121-171`）；名字即文件名，播放端对不存在名字无兜底。
9. **桌面模式与 Web 模式是两套渲染端**：Web 端是页面内 React overlay 消费 `/state`；桌面端是 Electron 子进程，经自定义 scheme `dsh-pet-bridge://` + 宿主管道转发**同一个** `handlePetRoute`（`dsh-pet/dsh-pet/src/host/plugin/desktop/spawn.ts:126-137`；`dsh-pet/dsh-pet/runtime/electron-helper/constants.js:134-135`）。
10. 文档与实现存在**三处确定漂移**（默认音色、`/sleep` 的 `?lock=` 契约、插件 `name` 与 patch `id` 不一致）与两处疑似死代码/死分支，已在第 15 节逐条列出。

---

## 1. 插件目录结构

**结论**

- 双入口包：Host 半侧 `lib/index.js`（ESM，Cordis 插件四件套 `name/inject/apply`）、Client 半侧 `lib/client.js`（经典脚本，向 `window.__ModuleLoader__` 注册工厂）；另有第三/第四入口 `lib/standalone.js`、`lib/app.js`（无 DSH 的独立运行）。
- `src/` 按**运行容器**分层，而不是按技术类型分层：`host/`（宿主进程）/ `client/`（DSH 页面）/ `shared/`（两端共用纯逻辑）/ `standalone/`（无 DSH 的 CLI 与设置页）/ `app/`（Electron 独立应用）。
- 有一条硬约束贯穿全仓：**Host 半侧不 import `src/shared`**（DSH 单文件加载限制），导致状态形状、朝向、档位等类型被**故意写两份**，改动必须两边同步。

**证据**

| 位置 | 内容 |
| --- | --- |
| `dsh-pet/dsh-pet/package.json:44` | `"main": "lib/index.js"`（Host 入口） |
| `dsh-pet/dsh-pet/package.json:48-60` | `exports`：`.` → `lib/index.js`；`./client` → `lib/client.js`；`./src/*` → `./src/*`（**源码随包发布**，`files` 含 `src`，见 `:63`） |
| `dsh-pet/dsh-pet/package.json:61-74` | `files` 白名单：`lib`、`src`、`assets/webm`、`runtime/electron-helper`、字体/图片/表情包/音效、`assets/config.jsonc`、`cordis.patch.yml`；**不含 `openapi.yaml`** |
| `dsh-pet/dsh-pet/tsdown.config.mjs:36-110` | 四份产物：`client`（IIFE 包裹）、`index`（ESM）、`standalone`（es2022）、`app`（Electron，含 zod/openai/anthropic） |
| `dsh-pet/dsh-pet/src/host/state.ts:5` | 注释明说"不 import src/shared（DSH 单文件加载约束），状态形状因此与共享层各写一份" |
| `dsh-pet/dsh-pet/src/host/anim.ts:6-8` | 同上：动画白名单"自包含实现一份"，靠两侧守卫测试钉口径 |
| `dsh-pet/dsh-pet/src/host/surface.ts:6` | 注释："只有宿主用得到，所以不与 src/shared 各写一份" |
| `dsh-pet/dsh-pet/src/client/index.ts:10-20` | Client 入口是"普通副作用脚本，不能有顶层 ESM import/export"，只做 `window.__ModuleLoader__.load({id:'dsh-pet', factory})` |
| `dsh-pet/dsh-pet/runtime/electron-helper/index.html:332-342` | 桌面渲染端 11 个经典 `<script>`：`shared-core.js` → `constants.js` → `sprite*.js` → `events.js` → `renderer.js` |
| `dsh-pet/dsh-pet/scripts/build-desktop-core.mjs:1-8` | `shared-core.js` 由 `src/shared/index.ts` 打成 IIFE 挂 `window.PetShared`（`file://` 下 ESM 有 CORS 限制） |
| `dsh-pet/dsh-pet/package.json:89` | 测试用 `node --experimental-strip-types --test "src/**/*.test.ts"`，测试与源码同目录 |

**目录速览（按职责）**

```
dsh-pet/dsh-pet/
├── package.json            # 版本 0.3.8；dsh.bundle / dsh.client / dsh.compatibility
├── cordis.patch.yml        # bundle patch：insert id=dsh-pet, name='dsh-pet'
├── src/host/               # 宿主半侧（178 文件）
│   ├── index.ts            # Cordis 插件：name/inject/apply
│   ├── plugin/             # 装配（setup/http-route/lifecycle/loops/session-watch/desktop-helper/…）
│   ├── routes/             # 领域路由（state/motion/interaction/voice/playback/menu/config/todos/…）
│   ├── voice/              # TTS：registry/edge/speak/cache/voices
│   ├── lock.ts anim.ts motion-cue.ts work-status.ts state.ts surface.ts broadcast.ts
│   └── helper/ + helper-process.ts   # 桌面 Helper 子进程与管道
├── src/client/             # 页面半侧（168 文件）：pet overlay、设置页、对话面板、通知
├── src/shared/             # 两端共用纯逻辑（94 文件）：state.ts/voice.ts/work-status.ts/pickers.ts/physics
├── src/standalone/         # 无 DSH 的 CLI、伪 ctx、本机 HTTP 服务与安全门（41 文件）
├── src/app/                # Electron 独立应用入口（5 文件）
├── runtime/electron-helper/ # 桌面渲染端与主进程（28 个 .js，手工维护、非构建产物）
├── assets/                 # config.jsonc 默认配置、webm 动画、表情包、音效、字体
└── scripts/                # 构建、prepack 门禁（含 check-openapi.mjs）、测试
```

**对 Voice Assistant 的含义**

- 若 VA 以 **DSH 插件**形式存在，可参考但不建议复制其"Host 不 import shared"的妥协：VA 的 TS 插件与 Python Runtime 本来就分离，协议类型应放独立 `packages/protocol`（任务书 §五），而不是两端各写一份。
- `exports` 暴露了 `./src/*`，意味着可以直接 `import 'dsh-pet/src/host/...'`，但那是**内部实现**（无兼容承诺，且是 `.ts` 源），**不得**作为 VA 的集成面；集成面只能是 HTTP + Cordis 服务。
- `files` 不含 `openapi.yaml`：**契约文件不随包发布**，只存在于仓库。VA 不能假设用户机器上有 openapi.yaml。

---

## 2. 插件生命周期

**结论**

- 安装层：`package.json` 声明 `dsh.bundle.patch` → DSH 把 `cordis.patch.yml` 叠进配置树 → `insert` 一行 `id: dsh-pet / name: 'dsh-pet'`（模块名解析到 `lib/index.js`）。因为还声明了 `dsh.client`，DSH 模块系统同时把包扫成浏览器插件、提供 `/plugins/dsh-pet/client.js`（**此句依据 patch 注释 `cordis.patch.yml:18-19`，DSH 侧实现待任务 C 验证**）。
- 宿主生命周期 = `apply(ctx)` 一次**同步装配**：建对象 → 起定时器/监听（全部经 `ctx.effect` 收集）→ 挂路由 → **最后**才 `startHelper()`（顺序不可换，注释明确）。
- 卸载清理由 `registerLifecycle` 那**一个** `ctx.effect` 统一收口（其它模块各自的 `ctx.effect` 只管自己的定时器/监听）：`markDisposed → stopWorkStatusFlush → stopDownloadSlotTimer → lock.releaseAll → playback.cancelAll → state.cancelAll → stopHelper`，顺序不可换（写叶子必须在 `cancelAll` 之前）。
- 浏览器生命周期 = 模块工厂 `apply(ctx)`：注册 locale、`petApi7340`（客户端只读）、通知、`/pet` 选择框、命令图标、设置导航图标、`shell.overlay` 插槽、`settings.section` 插槽、右侧栏对话页；**任一可选能力缺失只降级，不抛**。
- 另有两套"无 DSH"生命周期：`standalone`（伪 ctx + 本机 HTTP + 能力令牌）与 `app`（Electron 单进程，`DSH_PET_IN_PROCESS=1` 时不 spawn 子进程）。

**证据**

| 位置 | 内容 |
| --- | --- |
| `dsh-pet/dsh-pet/package.json:111-128` | `dsh.bundle.patch = ./cordis.patch.yml`；`dsh.client.inject = ['@deepseek-ai/dsh-client-connection']`；`dsh.client.platform = "web"`；`dsh.compatibility.dshReleases` 三项（0.2.1-rc.2/rc.3、0.2.2-alpha.2 全 compatible） |
| `dsh-pet/dsh-pet/cordis.patch.yml:23-25` | `- insert: - id: dsh-pet / name: 'dsh-pet'`（id 必须与包名一致、不得写行尾注释，注释见 :11-19） |
| `dsh-pet/dsh-pet/src/host/index.ts:29` | `export const name = 'pet'`（**与 patch 的 `dsh-pet` 不一致**，见 15.3） |
| `dsh-pet/dsh-pet/src/host/index.ts:31` | `export const inject = ['webServer','agentDefaultModel','credentials','llm','commands','connection']` |
| `dsh-pet/dsh-pet/src/host/index.ts:35-110` | `apply(ctx:any)`：setup → 各工厂 → `deps` 表 → `createHttpRoute` → `registerHttpRoute` |
| `dsh-pet/dsh-pet/src/host/index.ts:163-175` | `registerLifecycle` 后**最后** `startHelper()`（注释 :1-3 说明顺序不可改） |
| `dsh-pet/dsh-pet/src/host/plugin/setup.ts:100-107` | 日志文件的 `ctx.effect(注册/释放, 'dsh-pet: log file')`；复用 standalone logger 时不重复建、也不负责关 |
| `dsh-pet/dsh-pet/src/host/plugin/lifecycle.ts:31-43` | 卸载顺序：`markDisposed → stopWorkStatusFlush → stopDownloadSlotTimer → lock.releaseAll() → playback.cancelAll() → state.cancelAll() → stopHelper('dsh-host-stop')` |
| `dsh-pet/dsh-pet/src/host/plugin/http-route.ts:72-113` | 路由注册包在 `ctx.effect(() => ctx.webServer.register({kind:'prefix',path:ROUTE_SEGMENT,handler}), '...asset route')`，卸载自动摘 |
| `dsh-pet/dsh-pet/src/host/plugin/loops.ts:53-58,95-100,194-201` | 三个自调度 `setTimeout` 循环，全部在 `ctx.effect` 内登记清理 |
| `dsh-pet/dsh-pet/src/client/app.ts:65-67` | Client `name='pet'`、`inject=['slots','locale','connection','remote','remote.commands','commandUi']` |
| `dsh-pet/dsh-pet/src/client/app.ts:71,78-83,170-182` | `ctx.locale.register`、`ctx.provide('petApi7340', {getState,menuEvents,pose,progress})`、`shell.overlay`、`settings.section` |
| `dsh-pet/dsh-pet/src/client/app.ts:187-208` | 对话页注册整体 try/catch："任何注册异常都不许拖垮插件激活" |
| `dsh-pet/dsh-pet/src/standalone/context.ts:71-127,134-194` | 伪 ctx：`webServer{port getter, register}`、`effect` 收集、`provide/get` 注册表；单项失败只记录 |
| `dsh-pet/dsh-pet/src/host/plugin/desktop/spawn.ts:73` | `inProcessHost = process.env.DSH_PET_IN_PROCESS === '1'`（应用模式不 spawn） |

**对 Voice Assistant 的含义**

- VA 插件也应坚持"**一次同步装配 + `ctx.effect` 全量登记 + 单一卸载链**"，并把"停 Runtime 连接 / 停定时器 / 清挂起等待"排在释放资源之前；dsh-pet 的 `lock.releaseAll() → state.cancelAll()` 顺序（先写状态、再结束等待者）值得照抄。
- patch 的 `id` 必须等于包名（否则商城预检判 `SUBMISSION_ENTRY_MISSING`，`cordis.patch.yml:11-19`）；VA 的包名/entry id 要与 `package.json.name` 一致。
- `dsh.compatibility.dshReleases` 只声明了 3 个 DSH 版本且**不进安装闸门**（注释 `package.json:33`），VA 不能把它当版本保证，必须自己读 `engines`/`peerDependencies` 做运行时探测。
- VA 若同时提供 Host + Client 半侧，应像 dsh-pet 一样让 Client 侧 `apply` 对缺失服务**逐个降级**，否则一个插槽注册失败会让整页 Web UI 进不去。

---

## 3. Host Cordis API（ctx 上真实可用的服务与方法）

**结论**

- 宿主侧 `ctx` 被显式标注为 `any`（`HostContext = any`），所以"API 是否存在"只能靠**调用点**证明。审计到的真实成员共 9 个服务 + 5 个上下文能力，均已在本仓库内被实际调用（并有对应测试桩）。
- Host 侧对 `agentDefaultModel` / `credentials` / `llm` / `commands` / `connection` / `webServer` 六项走 `inject` 硬依赖；其余（`deepseekAccount`、`standaloneAi`、`shutdownApp`）一律 `ctx.get(name, false)` 软取。
- **未发现** `ctx.agents`、Session 创建、`followup`/`steer`/`cancel`、assistant-stream 的任何调用。dsh-pet 不碰 Agent 执行面。

**证据**

| 服务 / 能力 | 真实用法（调用点） | 语义与约束 |
| --- | --- | --- |
| `ctx.webServer.register(spec)` | `.../plugin/http-route.ts:75-78`：`{kind:'prefix', path:'/dsh-pet-7340', handler(req,res)}`，返回 disposer | 前缀路由；handler 是原生 `IncomingMessage/ServerResponse`，需自己写响应 |
| `ctx.webServer.port` | `.../plugin/desktop/spawn.ts:80`；`.../standalone/context.ts:72-75` | 端口可能短暂为 0（未完成监听），需轮询等待 |
| `ctx.effect(fn, label)` | `host/index.ts` 各 `register*`；`setup.ts:100`；`session-watch.ts:154,265`；`loops.ts:53,95,194` | 注册随卸载清理的副作用；**label 必填**（规范见 `.agents/skills/dsh-plugin-standards/SKILL.md:243`） |
| `ctx.on(event, handler)` → dispose | `.../plugin/session-watch.ts:155`（`'session/event'`，签名 `(session, event)`）、`:266-292`、`:297-303`（`'agent/error'`） | 宿主事件总线；`session/event` 载荷**无公开类型**（代码用 `any` 接收，`:268-269` 注释） |
| `ctx.provide(name, value)` | `.../plugin/setup.ts:176-187`（宿主 `petApi7340`）；`client/app.ts:78-83`（页面 `petApi7340`） | 同名服务在两个容器各一份；**同名重复 provide 会直接抛**（`client/app.ts:76-77` 注释） |
| `ctx.get(name, required?)` | `.../plugin/setup.ts:116-120`（包一层 `optionalService`）；`.../balance-poll.ts:89`（`ctx.get('deepseekAccount', false)`）；`client/app.ts:91,95,107,138` | `required=false` 缺失返回 `undefined`；**裸读未 inject 的属性会抛**（`setup.ts:111-114` 注释） |
| `ctx.logger` | `setup.ts:85-93`（作为文件 logger 的 base）；`http-route.ts:105` | 桌面版无控制台，`ctx.logger` 只写 stdout，故另建文件日志 |
| `ctx.commands.register({name,description,input:{hint},handler})` | `.../plugin/command-pet.ts:26-71`；`command-chat.ts:30`；`command-balance.ts:26` | 斜杠命令；`handler({rawInput})` 返回 `{kind:'success'|'error', text}` |
| `ctx.llm.stream(options)` | `.../host/whisper.ts:83,142`；`chat.ts:57-58` | `{provider, model, sessionId, messages, system, temperature, reasoningEffort?, signal}` → `AsyncIterable` chunk；`sessionId` 传的是常量 `'dsh-pet'`（`llm-call.ts:14`，仅为适配器载体） |
| `ctx.llm.listProviders()/listConfigurableProviders()/listModels()` | `.../routes/state.ts:22-55`（`GET /models`） | 可选，缺失/抛错只让清单为空 |
| `ctx.agentDefaultModel.currentSelection()` | `.../plugin/balance-poll.ts:78`；`whisper.ts:74`；`llm-reasoning.ts`；`model-selection.ts:34-46` | 返回 `{provider, model}`；未配置或抛错 → `undefined` |
| `ctx.credentials.resolve(ref)` | `.../plugin/balance-poll.ts:82` | 返回 `{value}?`，凭证缺失由此判定 |
| `ctx.connection.authenticatedUrl(origin)` | `.../plugin/desktop/spawn.ts:109` | 给"打开网站"菜单项换发带启动令牌的站点 URL，**等价登录态**，不得进日志 |

**对 Voice Assistant 的含义**

- VA 的 `DshAgentBridge`（任务书 §九）**不能从 dsh-pet 抄任何实现**：这里既没有 `ctx.agents`，也没有 Session/steer/cancel。Agent 桥必须按任务 C 的 DSH 官方 API 单独核实。
- 可以直接复用的宿主侧模式：`ctx.effect` 全量登记、`ctx.get(name,false)` 软取可选服务、`ctx.commands.register` 暴露 `/voice` 之类命令、`ctx.webServer.register({kind:'prefix'})` 挂自己的路由（**VA 应选一个不与 `/dsh-pet-7340` 冲突的段**）。
- `session/event` 是 VA 唯一能"监听 Agent 状态"的宿主入口（turn/start、tool/call、tool/result、approval/asked、turn/end、user/message、todo/write、assistant/message 在 dsh-pet 里都被消费过：`session-watch.ts:163-252,276-291`）。但事件载荷无类型，VA 必须像 dsh-pet 一样做**形状防御**并写契约测试。
- `ctx.llm.stream` 是"绕过 Agent 直接问模型"的旁路。VA 明确要求"DSH 是唯一 Agent 执行核心"，**不应**用这条旁路生成最终回复（只可用于标题/摘要类附属能力）。

---

## 4. Client Cordis API

**结论**

- Client 侧 `apply(ctx)` 拿到的服务：`slots`、`locale`、`connection`、`remote`（含 `remote.commands`）、`commandUi`（声明在 `inject`），另有软取 `uiWorkspace`、`sessions`、`primitives`、`react-dom`。
- 对外只提供一个**只读** Cordis 服务 `petApi7340`：`getState()` / `menuEvents(owner)` / `pose(petId)` / `progress(petId)`。**控制面一律走 HTTP**，注释明确"避免出现两条控制通道"。
- 插槽注册：`shell.overlay`（`id:'pet'`, `order:1000`）与 `settings.section`（`id:'pet-config'`, `order:30`）；命令 `/pet` 用 `commandUi.decorate({kind:'popupSelect'})` 补选择框；命令图标通过包装 `commandUi.candidates` 实现（DSH 无官方入口）。

**证据**

| 能力 | 调用点 | 约束 |
| --- | --- | --- |
| `ctx.locale.register(NS, dicts)` / `ctx.locale.bind(NS)` | `client/app.ts:71-72` | 9 种语言字典（`client/settings/locales/*.ts`） |
| `ctx.slots.inject(name, generator)` + `ctx.slots.register(meta, Component)` | `client/app.ts:170-172`（`shell.overlay`）、`:177-182`（`settings.section`） | `meta` 含 `name/id/order/label/inject` |
| `ctx.provide('petApi7340', …)` | `client/app.ts:78-83` | 只读；消费方用 `ctx.get('petApi7340')` 探测，缺成员=老版本 |
| `ctx.get('commandUi').decorate(spec)` | `client/app.ts:105-131` | `kind:'popupSelect'`，`options()` 异步，`onSelect` 里 `remote.commands.execute` |
| `ctx.get('commandUi')` + 包装 `candidates` | `client/command-faces.ts`（由 `app.ts:136-155` 安装） | DSH 无官方图标入口，属**DOM/对象层补丁** |
| `ctx.remote.commands.execute(sessionId, '/pet <id>', [])` | `client/app.ts:127` | 浏览器侧执行斜杠命令 |
| `ctx.get('uiWorkspace').openSession(id)` | `client/app.ts:91` | 通知点击跳会话；惰性取，缺失降级 |
| `ctx.get('sessions').list.getSnapshot().byId[id].title` | `client/app.ts:95` | 通知标题取会话名 |
| `primitives` / `react-dom/client` | `client/app.ts:31-60` | 缺失只影响图标，捕获降级 |

**对 Voice Assistant 的含义**

- 若 VA 的 UI 也是 DSH 页面插件，可照抄：`shell.overlay` 放麦克风指示/悬浮控件、`settings.section` 放语音设置页、`commandUi.decorate` 做设备/音色选择框。
- **不要**指望通过 Cordis 服务控制桌宠：dsh-pet 客户端服务只读；VA 的 PetBridge 必须走 HTTP（或反过来，VA 也只能提供只读服务给别人）。
- `ctx.get('commandUi')`、`ctx.get('sessions')` 这类"官方无入口、靠服务对象内部形状"的写法是**高风险兼容点**：VA 应把它们放进 try/catch 或特性探测，而不是写在启动关键路径。

---

## 5. HTTP API

**结论**

- 只有**一条前缀路由** `/dsh-pet-7340`（`7340` 是历史名字，**不是端口**），挂在 DSH Web 服务上，故**没有独立端口**：`http://127.0.0.1:{ctx.webServer.port}/dsh-pet-7340/...`；`dsh web` 默认 3080。
- 浏览器侧实际地址还要加挂载前缀：`routePathOf(document.baseURI) = 前缀 + /dsh-pet-7340`（反代把 UI 挂在子路径时会多一段）。
- 契约共 **39 条路径 / 49 个操作**（GET 18、POST 24、DELETE 5、PUT 1、PATCH 1），全部由同一个 `handlePetRoute` 实现；桌面 Helper 复用同一函数，故两端行为逐字一致。
- 鉴权：**插件层没有**。仅监听 127.0.0.1；openapi 明写"没有任何鉴权：任何能访问本机该端口的进程都能调用"。仅"独立模式"（非 DSH）才有进程级能力令牌。
- 状态码模型：业务失败 200 + `{ok:false,reason,message}`；协议失败 404/405/400/413/500；素材端点直接 404 纯文本。
- 请求体上限：通用 1 MiB；`POST /work-status` 更严，8 KiB。`GET`/`DELETE` 不读体。

**证据**

| 事实 | 证据 |
| --- | --- |
| 路由段常量 | `dsh-pet/dsh-pet/src/shared/constants.ts:26` `ROUTE_SEGMENT = '/dsh-pet-7340'` |
| 浏览器地址 = 挂载前缀 + 路由段 | `.../shared/constants.ts:37-56,62`（`mountPrefixOf` / `routePathOf` / `ROUTE_PATH`） |
| 前缀注册 + 同源处理 | `.../host/plugin/http-route.ts:43-44`（`new URL` + `rest = pathname.slice(prefix+1)` 后 `decodeURIComponent`）、`:75-78`、`:86-88`（仅 PUT/POST/PATCH 读体） |
| 无鉴权 | `dsh-pet/openapi.yaml:19`；`http-route.ts` 全文件无 token/cookie 校验 |
| 失败口径 | `.../host/routes/result.ts:71-80`（业务失败恒 200）、`:82-105`（400/405/413/500） |
| 请求体上限 | `.../host/http.ts:180` `MAX_BODY_BYTES = 1MiB`；`.../routes/state.ts:116` work-status 8 KiB |
| 业务 reason 全集（34 个） | `.../host/routes/result.ts:15-46` |
| 长轮询上限 | `.../host/state.ts:44` `MAX_STATE_WAIT_MS = 10_000`；解析规则 `:61-77`（`since`/`timeout` 成对，`timeout ∈ 0..10000`） |
| 读体/写体 | `http.ts:150-169`（`sendJson`/`sendText`）、`:172-177`（`RouteResult` 四态）、`:191-226`（`readBody`，超限 `body-too-large`） |
| 素材路由（Range 支持） | `http.ts:59-79`（单段 Range）、`:91-147`（`sendFile`：fstat 取长、206/416、客户端断开即停读） |

**路由总表（路径 : 方法 → 作用；行号为 openapi 条目起点）**

| 路径 | 方法 | 作用 / 关键约束 |
| --- | --- | --- |
| `/state` (101) | GET | 唯一数据出口；`?since=&timeout=` 长轮询（成对）；`cache-control: no-cache, no-store` |
| `/work-status` (223) | POST / DELETE | 外部写工作状态（固定槽 `api`，6 档，`task` ≤40 码点）；DELETE 清空（204） |
| `/balance` (294) | POST | 立即刷新余额（写 `sections.balance`，只回 `{ok}`） |
| `/whisper` (320) | POST | 生成一句碎碎念；响应额外带 `text`(+`image`) |
| `/broadcast` (375) | POST | 第三方投喂文本（不生成）；`image`/`url` 二选一；无长度/频率限制 |
| `/bubble/clear` (510) | POST | 写 `{clear:true}` 收起气泡（幂等） |
| `/anim` (555) | POST | 点播动画：池内 `name` 或 http(s) `url`，可选 `facing`；回 `playbackId` |
| `/position` (709) | POST | 归一化坐标 `x/y`（宠物中心），`mode ∈ instant/spring/line`；回夹取后值 |
| `/throw` (845) | POST | 抛掷 `angle`(度)/`power`(>0) |
| `/lock` (933) | POST | 取锁/续期二合一；回 `lockId/petId/expiresAt` |
| `/lock/release` (1054) | POST | `lockId` 或 `force:true`（恰一个）；幂等 |
| `/sleep` (1127) | POST | 入睡（宿主挑三段动画名）；被占用时回 `locked` |
| `/wake` (1162) | POST | 叫醒（幂等，回 `changed`） |
| `/pose` (1187) | GET | 读**桌面端**实况（位置+朝向）；非 desktop 显示 → `pet-not-displayed` |
| `/pose/report` (1260) | POST | 桌面渲染端上报实况（内部通道，变化时推+节流） |
| `/playback/{id}` (1325) | GET | 播放回执；`?wait=&timeout=` 可挂起 |
| `/playback/{id}/report` (1397) | POST | 渲染端上报播放状态（幂等，终态保护） |
| `/attachment` (1481) | GET | 按附件 id 取图（内容哈希） |
| `/chat` (1528) | GET / POST / DELETE | 读记忆窗口（`rounds` 0–200）/ 说一句（可带图）/ 按 `ts` 删轮或清空 |
| `/chat/memory` (1716) | GET / DELETE | 已删宠物的残留记忆：列出 / 清空 |
| `/config` (1789) | GET / PUT / POST | 读成品聚合 / 保存用户层 / 同步默认（写路径串行排队） |
| `/pet-display` (1933) | POST | 单宠 `display` 改写（并写 `sections.config` 信号） |
| `/pet-config` (2002) | POST | 整条目实例写回 |
| `/config/meta` (2091) | GET | 配置/日志/存储路径清单、profile 名 |
| `/models` (2139) | GET | 可选模型清单（来自 `ctx.llm`） |
| `/reload` (2175) | POST | 重启桌面 Helper |
| `/quit` (2202) | GET / POST | 退出整个宿主应用；**DSH 内 `canQuit:false`**（仅独立模式可用） |
| `/thumb/{petId}/{file}` (2257) | GET | 动画素材（`.webm`/`.mov`，支持 Range） |
| `/voice/speak` (2312) | POST | 合成 mp3 并**直接返回文件本体**（`audio/mpeg`） |
| `/voice/voices` (2378) | GET | 音色白名单（4 个中文音色） |
| `/logo` (2413) | GET | 包内 `assets/logo.png` |
| `/sound/{file}` (2434) | GET | 点击音效（`assets/sound/`，扁平） |
| `/font/{file}` (2457) | GET | 字体文件 |
| `/pic/{file}` (2480) | GET | 表情包 / 用户图（含 `pic/memes/<root>/<name>.png`） |
| `/menu/item` (2537) | POST / DELETE | 第三方右键菜单注册（按 owner 整体覆盖）/ 清除 |
| `/menu/events` (2651) | GET | 读取即消费，可 `?wait=` 长轮询 |
| `/menu/click` (2708) | POST | 渲染端上报点击 |
| `/todos` (2750) | GET / POST | 待办清单 |
| `/todos/{id}` (2820) | PATCH / DELETE | 部分更新 / 删除 |

**对 Voice Assistant 的含义**

- VA 的 PetBridge 需要**自己实现一个小 HTTP 客户端**：基址 = `http://127.0.0.1:<dsh web port>/dsh-pet-7340`，且要处理"反代挂载前缀"（网页端插件尤其重要）。
- **必须按 `reason` 分支，不能按状态码**：`pet-required` / `unknown-pet` / `lock-required` / `lock-lost` / `locked` / `sleeping` / `pet-not-displayed` / `voice-busy` 都是 200。
- 安全：插件层无鉴权 → VA 与桌宠之间的调用谁都能冒充；VA 自己**不得**把 `/dsh-pet-7340` 反向代理到公网，也不要把令牌放进 URL（该 API 本来也没有令牌）。
- `POST /broadcast` 无长度限制、不限频 → 若 VA 逐字流式播报，必须自行节流/合并，否则会把气泡刷爆。
- `/state` 长轮询上限 10s 且 `since`/`timeout` 成对必填 → VA 的轮询器必须"首拉不带参 → 记 `counter` → 之后带 `since&timeout` → 收到即再拉"，且两个参数要么都给要么都不给。
- `/voice/speak` **不接受 `?pet=`，也不检查占用/睡眠**（`routes/voice.ts:21-32` 只调 `deps.voice.speak`），即它是"全局 TTS 工具端点"，不归属任何宠物。

---

## 6. OpenAPI 契约

**结论**

- `openapi.yaml` 在**仓库根**（不在包根），`openapi: 3.1.0`，`info.version: 0.3.8` 与包版本一致；39 路径 / 49 操作与源码路由一一对应（`scripts/check-openapi.mjs` 在 `prepack` 链上做静态比对，防文档漂移）。
- 契约有明确"两套数据通道"约定：动作端点只回执 + `GET /state` 单一出口；`counter` 是唯一变更信号（`Date.now()` 严格递增，重启不倒退）。
- 契约写清了失败模型、长轮询、宠物 id 可含点号（路径**不得**按 `.` 切分）、素材端点不套失败实体。
- 但契约仍有三处与源码不一致（默认音色、`/sleep` 的 `?lock=`、客户端 `getState` 叶子集合），说明"文档+静态比对"不能替代逐条源码核对。

**证据**

| 事实 | 证据 |
| --- | --- |
| 版本与标题 | `dsh-pet/openapi.yaml:1-5`（`openapi: 3.1.0`、`version: 0.3.8`） |
| 部署形态 / 无固定端口 / 无鉴权 | `openapi.yaml:8-22`（`{port}` = `ctx.webServer.port`，默认 3080；只监听 127.0.0.1；无鉴权） |
| 数据流与 `counter` 语义 | `openapi.yaml:37-58` |
| 状态码约定 | `openapi.yaml:60-68` |
| `counter` 严格递增实现 | `.../host/state.ts:119-124`（`Math.max(Date.now(), last+1)`） |
| 宠物 id 可含点号、不得 split | `openapi.yaml:164-166`；解析实现 `.../shared/state.ts:148-160`（按**最后一个**点切） |
| 契约静态校验 | `dsh-pet/dsh-pet/scripts/check-openapi.mjs:1-8`（YAML 可解析、`$ref` 全解、路径必须真实存在于 `src/host/routes`）；挂载于 `package.json:87-88`（`prepack` → `check:openapi`） |
| **契约不随包发布** | `package.json:61-74` 的 `files` 不含 `openapi.yaml` |

**对 Voice Assistant 的含义**

- VA 可以照抄这套"契约治理"：`openapi.yaml` + 一个静态比对脚本进 `prepack`/CI（任务书 §十五要求契约测试）；但必须额外覆盖**默认值与枚举**（dsh-pet 的漂移正好出在这里）。
- VA 与 dsh-pet 之间应**以 openapi 为准生成客户端**（而不是手抄），并把 `reason` 联合类型生成成 TS 联合，避免把 200 当成功。
- 由于 pet 的 openapi 不随包发布，VA 的适配层必须**对字段做可选/防御**（例如按 `state.counter` 是否存在判断老宿主，见 `.../shared/state.ts:19-26` 的"老宿主不带 counter → 退回定时轮询"）。

---

## 7. 工作状态接口（`work-status.ts` + `work-status-bridge.ts`）

**结论**

- **模型**：6 档，顺序固定且与配置 `animations.events.workStatus` 数组索引**严格一一对应**：`thinking(0) / working(1) / result(2) / waiting(3) / success(4) / error(5)`。快照 `{state, task}`，`null` = 空闲；`task` 是 todo 详情，**按码点截断 40**。
- **事件映射**：`turn/start→thinking`；`tool/call→working`（`ask_user_question` 特判为 `waiting`）；`tool/result→result`；`approval/asked→waiting`；`turn/end`：`completed→success`（goal 续跑轮有特殊终局判定）、`error|max-tokens|timeout→error`、`blocked→waiting`、其余（`aborted` 等）→ 清会话回空闲；`todo/write` 只更新 `task` 不切档。
- **多会话聚合**：`WorkStatusStore` 按 sessionId 存 `{state, seq, task}`，展示时取**优先级最高者**（`waiting 60 > error 50 > working 40 > thinking 30 > result 25 > success 20`，同档取 `seq` 更大者），`state` 与 `task` 取自**同一个 best 会话**（不会串会话）。
- **发布节流**：`work-status-bridge` 只在"内容真的变了"时写叶子；并对 `working→result` 单向做 5s 抖动压制（工具秒回会来回切十几次），其余方向与终态立即写。
- **生命周期**：`success`/`error` 终态保留 60s 后被定时器清理回空闲；`turn/start` 清上一轮 `task`/todo 缓存/在途工具表；`turn/end` 的 null 分支清整个会话条目；插件卸载清所有定时器。
- **外部写入槽**：固定 sessionId `'api'`，`POST /work-status` 直接 `setState + setTask + publish`，`DELETE` 清空；**无租约、无写者仲裁、最后写入者生效**，与 DSH 会话一起参与同一优先级比较（注释 `openapi.yaml:232-237`）。

**证据**

| 事实 | 证据 |
| --- | --- |
| 6 档常量 | `dsh-pet/dsh-pet/src/host/work-status.ts:15`；共享侧 `dsh-pet/dsh-pet/src/shared/work-status.ts:10-11` |
| 档位→数组索引 | `.../shared/work-status.ts:14-21`（注释"勿在中间插入新档"） |
| 事件→档位 | `.../host/work-status.ts:70-99`；`turnEndState` `:23-28`；`ask_user_question` `:31,82` |
| goal 续跑终局 | `.../host/work-status.ts:34,45-66`（`update_goal` → closing；中间轮 `result` 不庆祝） |
| todo→task（40 码点截断） | `.../host/work-status.ts:106,114-128` |
| 快照类型 `{state,task,ts}` | `.../host/work-status.ts:131-135` |
| 优先级与挑选 | `.../host/work-status.ts:149-171` |
| Store（按会话、防刷屏、clear、refresh 才更新 ts） | `.../host/work-status.ts:181-248`（`setState` `:209-215`、`setTask` `:218-224`、`clear` `:227-231`、`refresh` `:239-247`） |
| 事件接线（含 todo/turn 开头清理/终态定时器） | `.../host/plugin/session-watch.ts:154-252`（`todo/write` `:163-177`、`turn/start` `:189-198`、`turn/end` null `:217-226`、终态 `:251-252`） |
| 终态保留 60s | `.../host/plugin/session-notify.ts:45` `TERMINAL_KEEP_MS = 60*1000`；`scheduleTerminalCleanup` `:74-87` |
| 发布 + 5s 抖动压制 | `.../host/plugin/work-status-bridge.ts:21`（`WORK_STATE_GAP_MS=5000`）、`:31-56`（key 比对、`busyFlip`）、`:55`（写 `sections.workStatus = {state, task}`） |
| 停补写定时器 | `.../host/plugin/work-status-bridge.ts:59-64`，卸载处 `lifecycle.ts:34` |
| HTTP 写入校验 | `.../host/routes/state.ts:110-152`（8 KiB、6 档枚举、40 码点、`DELETE` 204） |
| 外部槽常量与序号 | `.../host/plugin/setup.ts:201-206`（`EXTERNAL_WORK_SESSION='api'`、`nextExternalWorkSeq`） |
| 客户端消费 | `.../client/pet/multi.ts:211-218`（`readWorkStatus` → tick）；`.../client/pet/card/cue-effects.ts:106-157`（按 `WORK_STATUS_INDEX` 取池、随机抽、终态一遍、非终态循环/轮换）；`.../client/pet/card/bubble-slots.ts:55-58`（气泡槽） |

**对 Voice Assistant 的含义**

- **Avatar State 不能 1:1 映射任务书的 8 态**：pet 只有 6 档，且没有 `LISTENING`/`SPEAKING`/`IDLE(显式)`。VA 需要一张映射表 + 用 `/anim`、`/broadcast` 补足"听/说"表现；**任何"新增档位"都要求改配置数组顺序**（会破坏所有宠物包），不可取。
- `POST /work-status` 是**全局单槽、last-writer-wins**，且与真实 DSH 会话共用优先级：VA 若在语音期间写 `working`，会被真实会话的 `waiting`/`error` 覆盖；反之 VA 写 `success` 也可能盖掉正在 `working` 的会话（`success 20 < working 40`，实际不会盖，但 `waiting` 会）。**建议 VA 只在"无活动 DSH 会话"时写这个槽**，并在语音结束 `DELETE`。
- `task` 上限 40 码点（约 11 个汉字/行 × 数行），VA 不能把整句 ASR 结果塞进去；要用就压缩成"正在听/正在说"这类短标签。
- `sections.workStatus` 的 `counter` 变化会**重播档位动画**，节流只有 5s 单向；VA 若高频写入会造成桌宠动画抖动，必须自己做状态去重。
- 终态 60s 自动清理意味着"任务完成"的庆祝只保留 1 分钟——VA 想延长必须自己有补偿机制（例如保留锁 + 循环点播），但这会与用户交互抢占冲突。

---

## 8. 动画接口

**结论**

- `/anim` 有**两种互斥形态**：`name`（必须是该宠物所属条目的动画池内的名字，池 = `idle/turn/drag/clicks/moves.actions/categories[].actions/events.*` 的并集）或 `url`（http/https 完整地址，不查池、不走菜单语义、直接换源播一次）。两个都给/都不给 → `bad-request`。
- 可选 `facing: left|right`：不传**不改朝向**（不是回落 left），传了必须合法。
- 受理成功回 `{ok:true, playbackId}` 并写 `pets.<id>.anim = {name|url, playbackId, facing?}`；真实播放结果只能通过 `GET /playback/{id}`（可 `?wait=ended&timeout=`）拿到，因为"播没播完"只有渲染端知道。
- 客户端消费：`multi.ts` 把 `anim` 叶子转成 `animCue`（带自增 `seq`）→ `cue-effects.ts` 按 `url`/`name` 分流（`url` 停运动+`setCueUrl`+`bumpSeq`；`name` 走 `playByName` 与右键菜单同一处理函数，含镜像修正与移动类真实位移）。
- 与"状态类叶子"的区别：`anim`/`position`/`throw`/`say` 是**指令**（宿主→渲染端，不回流）；`lock`/`sleep` 是**状态**（渲染端读它决定冻结/睡姿，并自己按时间收尾）。

**证据**

| 事实 | 证据 |
| --- | --- |
| 决策层（纯逻辑） | `dsh-pet/dsh-pet/src/host/anim.ts:121-171`；二选一 `:130-133`；facing `:135-143`；pet 必填 `:145-152`；url 校验 `:156-162`；池内校验 `:166-169` |
| 可点播名字集合（与菜单同源） | `.../host/anim.ts:45-88`（`idle→turn→drag→clicks→moves.actions→categories→events` 顺序展平去重） |
| url 只放行 http/https | `.../host/anim.ts:98-110`（`file:` 会让桌面渲染端读本地任意文件） |
| 路由接线（surface→lock→写叶子→回 playbackId） | `.../host/routes/motion.ts:28-66`（`surfaceBlocked` `:48`、`lockBlocked` `:51`、`playback.create` `:55`、`state.writePet(...,'anim',…)` `:56-60`） |
| 位置/抛掷决策 | `.../host/motion-cue.ts:71-104`（x/y→mode→duration→pet，夹取 0..1）、`:110-116`（line 才带 duration）、`:129-146`（angle/power） |
| 位置/抛掷路由 | `.../host/routes/motion.ts:73-117`（回夹取后的 `x/y`） |
| 姿态（桌面独有） | `.../host/routes/motion.ts:124-164`（`GET /pose` 需 display 含 desktop；`POST /pose/report` 快照） |
| 播放回执 store 与路由 | `.../host/routes/playback.ts:23-43`（report：`unknown`/`invalid` 都是 200）、`:44-91`（`?wait=` 挂起，`kind:'none'` 表示调用方已断开） |
| 叶子类型（客户端） | `.../shared/state.ts:244-260`（`readAnim`：`name`/`url` 恰好一个、`playbackId`/`facing` 可选） |
| 客户端分发 | `.../client/pet/multi.ts:241-254`（`anim` → `animCueRef` + `setAnimCueTick`）、`:306-313`（按 `counter` 变化分发） |
| 客户端执行 | `.../client/pet/card/cue-effects.ts:173-198`（url 与 name 两条路）；`.../client/pet/animation/animation.ts:71-90`（`switchTo/setCueUrl/setFrozen/…`）、`:128-140`（防重命中也要回执） |
| 素材加载超时 | `.../client/pet/animation/animation.ts:28` `ASSET_FETCH_TIMEOUT_MS = 10_000` |
| 动画扩展名（webm / mov 可切） | `.../shared/constants.ts:64-68` |

**对 Voice Assistant 的含义**

- VA 想让桌宠"听/说"，只有三条路：**(a)** 用配置池内已有的名字（`/anim` name）；**(b)** 自己托管 webm 并给 `url`（要求对方 CORS、且不走菜单语义、播完回正常链）；**(c)** 改宠物包配置新增动画（侵入用户配置，不可取）。
- 自带素材用 `url` 时两端都是 `fetch`+blob（`openapi.yaml:596-598`），**跨域必须由素材方给 `Access-Control-Allow-Origin`**；VA 若在本机起素材服务，应与 DSH 同源或显式加 CORS。
- 动画"播完"不可靠：同一动画连续两次点播可能被播放端防重逻辑吞掉（`openapi.yaml:614-616`）；VA 依赖"播完再说话"时必须用 `playbackId + GET /playback/{id}?wait=ended&timeout=`，并处理 `unknown-playback`。
- `facing` 不传=保持当前朝向；VA 若做"面向用户"的姿态控制，应显式传 `facing` 并在之后不假设它不变（宠物自己播 `turn` 池会翻回去）。
- VA 若要"移动宠物到屏幕角落"，用 `/position`（`mode: instant|spring|line`，坐标为宠物中心）；桌面端坐标是**多屏工作区外接矩形**的归一化值，与网页视口语义不同（`openapi.yaml:718-732`），不能混用。

---

## 9. Lock 机制（`lock.ts` / `lock-freeze.ts`）

**结论**

- **粒度**：**每只宠物一把、全有全无**；`petId → LockRecord`，进程内内存，宿主重启即空。
- **TTL**：缺省 **120000ms（2min）**，允许 **1000ms ~ 1800000ms（1s~30min）**；越界/非有限数直接 `bad-request`，**不夹取**；续期不带 `ttl` 时沿用本轮 `ttl`。
- **过期语义**：**懒判、无定时器**——`current()` 每次读时若 `now >= expiresAt` 就删记录、写墓碑、把叶子改 `{locked:false}`。没人调用时渲染端按叶子里的 `expiresAt` 自行解冻。
- **门禁**：`/anim`、`/broadcast`、`/position`、`/throw`、`/bubble/clear` 五个端点共用 `gate()`：有锁且编号匹配→放行；有锁但没带编号→`lock-required`；有锁但编号不符→`lock-lost/unknown`；无锁且没带编号→放行（**既有调用方零改动**）；无锁但带了编号→`lock-lost` + 墓碑里的 `cause`。
- **不复活**：`acquire` 时"给了 `lockId` 但当前无锁"一律 `lock-lost`，不能用旧编号把锁重新建起来。
- **抢占**：只有**用户**能抢占——渲染端在拖拽/点击/隐藏/关闭时调 `/lock/release {force:true}`，`cause=preempted`；第三方之间先到先得（`locked` + `expiresAt`）。
- **副作用**：取锁会**先叫醒**睡着的宠物（`sleep.wake`）；取锁会打断正在播的点播（回执 `cancelled` + `reason: frozen`）；占用期间 `POST /sleep` 回 `locked`。
- **客户端冻结**：叶子 `{locked:true, expiresAt}` 是唯一真相；`lock-freeze` 用它算 deadline、设一次解冻定时器、并在用户接管时本地立即 `release()`；冻结只挡**自动来源**（随机链、自播动画、自动余额、工作状态），**不挡显式指令**（say/anim/position/throw）。

**证据**

| 事实 | 证据 |
| --- | --- |
| TTL 常量 | `dsh-pet/dsh-pet/src/host/lock.ts:21-23` |
| cause 与文案 | `.../host/lock.ts:27,30-35` |
| 叶子形状 `{locked,expiresAt}` | `.../host/lock.ts:38`；客户端 `.../shared/state.ts:262-282` |
| 记录/墓碑/编号格式 | `.../host/lock.ts:41-54,264-267`（`lk-<时间36>-<自增36>`） |
| TTL 校验（不夹取） | `.../host/lock.ts:76-89` |
| 懒判过期（读带副作用） | `.../host/lock.ts:122-135`（注释明确"读方法带一次副作用是有意的"） |
| 门禁真值表 | `.../host/lock.ts:155-175` |
| 取锁/续期 | `.../host/lock.ts:183-213`（续期 `:195-200`、新建 `:206-212`） |
| 释放（幂等 + lockId/force 二选一） | `.../host/lock.ts:223-241` |
| 卸载全撤 | `.../host/lock.ts:244-249` → `lifecycle.ts:39` |
| 路由接线（取锁唤醒、失败带 cause/expiresAt） | `.../host/routes/interaction.ts:32-71`（`requirePet(..., {surface: !isRelease})` `:45`、`sleep.wake` `:65`） |
| 门禁调用点 | `.../host/routes/motion.ts:51,98,109`；`.../host/routes/interaction.ts:140,179` |
| 自动来源让路 | `.../client/pet/card/cue-effects.ts:100`（余额）、`:114`（工作状态）、`:112-113`（"不挡宿主写入，按宠物在渲染端忽略"） |
| 冻结驱动 | `.../client/pet/card/lock-freeze.ts:53-56`（过期即视为无锁）、`:86-99`（一次定时器）、`:101-106`（用户接管本地解冻） |

**对 Voice Assistant 的含义**

- **这是 VA 与桌宠联动的核心原语**：VA 在 `LISTENING`/`SPEAKING` 期间取锁，就能让桌宠**不随机乱跑、不弹自动气泡、不响应自动工作状态**，同时仍然接受 VA 自己的显式指令（`/anim`、`/broadcast` 带 `?lock=`）。
- 必须实现**续期心跳**（建议 TTL 60s、心跳 20s），否则 2 分钟后锁过期、桌宠当场解冻并继续随机动画；心跳本身也是"锁还在吗"的探测器（`lock-lost` + `cause`）。
- 必须在**卸载/异常路径** `POST /lock/release`，否则用户要等 TTL 或被用户交互抢占；`releaseAll` 只发生在插件卸载，VA 不能依赖。
- VA 与其它第三方（女仆插件等）会**互相 `locked`**：VA 拿到 `locked` + `expiresAt` 后应退避重试，而不是抢；用户拖拽会以 `preempted` 抢走，VA 必须能优雅收尾（停止播报/不再写动画）。
- 锁**不会**阻止 `/state` 读取，也不会阻止 `/voice/speak`（TTS 端点不检查锁）；"完全静止"是渲染端行为，宿主停不掉正在播的视频。

---

## 10. TTS Provider 注册接口

**结论**

- 注册面：宿主 Cordis 服务 **`ctx.get('petApi7340').voice`**，成员只有 `register(def)` 与 `list()`；**没有 unregister**（注销只能靠 `register` 返回的 disposer）。
- `VoiceProvider` 形状：`{ id: string; name: string; synthesize({text, rate}): Promise<Uint8Array> }`。`id` 必须非空且**不能等于内置 `'edge'`**（否则缓存键撞车，抛 `TypeError`）；`synthesize` 必须是函数；失败必须 **throw**（宿主归一成 `generate-error`），返回空字节同样按失败处理。
- **单槽语义**：同一时刻只有一个第三方实现生效，**后注册覆盖先注册**；注销只在"当前仍是自己那份"时清空（迟到的注销不会顶掉后来者）。`voice.list()` 返回 `{builtin:['edge'], external:[当前 id]}`。
- **请求时现查**：每次 `POST /voice/speak` 都重新 `activeVoiceProvider()`，所以运行中注册/卸载都能立刻生效（不是启动快照）。
- **覆盖语义**：注册后 `voice` 参数不再影响合成（音色由 provider 自己决定），但**校验口径不变**（非法 voice 仍 `bad-request`）；缓存键把 voice 置空但加入 `source`，换实现不会命中旧音频。
- **不回落**：注册了就一定走第三方，第三方坏了就是 `generate-error`，绝不会静默退回 `edge`。
- 生命周期：注册表是**模块级单例**（`registry.ts`），跨插件实例共享；宿主侧 `petApi7340` 在 `createHostSetup` 里 `ctx.provide` 一次，随插件卸载消失。

**证据**

| 事实 | 证据 |
| --- | --- |
| 服务暴露 | `dsh-pet/dsh-pet/src/host/plugin/setup.ts:176-187`（`voice: {register: registerVoiceProvider, list: listVoiceProviders}`；注释"不给 unregister"） |
| 内置 id 与接口 | `.../host/voice/registry.ts:12`（`BUILTIN_VOICE_ID='edge'`）、`:15-27`（`VoiceProvider`） |
| 注册校验与覆盖 | `.../host/voice/registry.ts:39-49`（`id` 非空/非 edge/`synthesize` 是函数；`current = def`；disposer 只在 `current===def` 时清） |
| 查询 | `.../host/voice/registry.ts:55-65`（`activeVoiceProvider` / `listVoiceProviders`） |
| 测试复位（不对外） | `.../host/voice/registry.ts:67-73`（`resetVoiceProviders`，`@internal`） |
| 请求时现查 provider | `.../host/voice/speak.ts:118-122`（注释"第三方可能运行中才注册"） |
| 第三方合成 + 15s 超时 + 空字节失败 | `.../host/voice/speak.ts:156-172`（`withTimeout`）、`:174-189`（`synthesizeWithProvider`；`:187` 空字节即 `VoiceSynthError`） |
| 文档契约（与源码一致） | `dsh-pet/CORDIS.md:244-306`（参数/抛错/行为/示例）、`dsh-pet/openapi.yaml:2320-2325`（"经 Cordis 服务 `petApi7340.voice.register` 注册"） |

**对 Voice Assistant 的含义**

- 这是 VA 与 dsh-pet **唯一"官方"的 TTS 接入点**，但它把 TTS 语义绑在"桌宠要念一句"上：注册后**所有** `POST /voice/speak` 调用（包括设置页试听、其它插件的调用）都会走 VA 的 Runtime，**影响面是全插件级的**，不是 VA 私有的。
- **单槽 → 与其它 TTS 插件互斥**（后注册覆盖）。VA 若注册，必须：①在 `ctx.effect` 里注册并靠 disposer 卸载；②在 UI 明确"已接管桌宠语音合成"；③处理 `list()` 里发现 `external` 不是自己（被别人覆盖）的降级。
- 因为"不回落"，VA Runtime 挂掉 = 桌宠彻底没声音。若 VA 不能保证 Runtime 常驻，**更安全的做法是不注册 provider**，而是让 VA 自己在 Runtime 侧合成+播放，桌宠只负责动画/气泡。
- 若 VA 选择注册，**播放权威仍在桌宠两端**（浏览器页 / 桌面窗口各自 `new Audio`），VA Runtime 只产字节不播——这恰好满足"不要在多个模块同时向扬声器播放"的约束，但会与 VA 自己的"SPEAKING 状态由 Runtime 驱动"产生时序差（播完事件无回调，见 11 节）。
- `synthesize` 入参**没有** `voice`、没有配置上下文、没有取消信号（只有宿主侧的 `withTimeout` 会 reject，**原 Promise 不会被取消**，`speak.ts:156` 注释明说）→ VA 的实现必须自己处理"被超时放弃后仍在进行的合成"。

---

## 11. TTS 音频格式要求（`voice/speak.ts` / `routes/voice.ts` / `shared/voice.ts`）

**结论**

- **格式**：**mp3**。成功时 `/voice/speak` 直接返回文件本体，`content-type: audio/mpeg`；缓存文件为 `<userRoot>/voice-cache/<sha1>.mp3`。
- **字节类型**：第三方 `synthesize` 必须返回 `Uint8Array`（Node `writeFile` 直接写）；空数组视为失败。
- **长度**：`text` trim 后非空且 **≤500 个 UTF-16 字符**（`MAX_TEXT_CHARS`），超出 `bad-request`。
- **语速**：`rate` 形如 `+0%`/`-10%`，正则 `^[+-]\d{1,3}%$`，数值范围 **-50 ~ +100**；越界 `bad-request`。
- **音色**：只接受白名单 4 个中文音色（`zh-CN-XiaoxiaoNeural / XiaoyiNeural / YunxiNeural / YunjianNeural`），缺省 `zh-CN-XiaoyiNeural`（**openapi 写成 XiaoxiaoNeural，是文档错误**）。
- **超时**：内置 edge 15s（`SYNTHESIS_TIMEOUT_MS`）；第三方也 15s（`PROVIDER_TIMEOUT_MS`）；客户端请求超时 20s（比宿主宽 5s，让宿主先给出结构化失败）。
- **并发/队列**：**串行**（`chain`），同时最多排 3 个（含正在跑的），超出 `voice-busy`；缓存命中直接返回文件，不占队列。
- **缓存**：键 = `sha1(source \n voice \n rate \n text)`（`source` 为 `edge` 或第三方 id）；上限 **20 MiB / 200 个文件**，按 mtime 淘汰最旧；只在合成成功后才淘汰。
- **播放**：宿主**不播**。两端 `shared/voice.ts` 用 `fetch` 取 mp3 → `URL.createObjectURL` → `new Audio().play()`；播放前要过三道门：`say.voiceTo === 本端`、网页端 `document.hidden === false`、配置 `voiceEnabled === true`；手动点播（对话面板喇叭）不受总开关限制，但会先掐掉上一句。
- **播完无回调**：`audio.onended` 只释放 blob/改状态图标，**不回报宿主**；宿主与第三方都无法知道"这句真的播完了"（只有 `/playback` 覆盖动画，不覆盖音频）。

**证据**

| 事实 | 证据 |
| --- | --- |
| 文本/队列上限 | `dsh-pet/dsh-pet/src/host/voice/speak.ts:16`（500）、`:17-18`（`MAX_QUEUE=3`） |
| 语速正则与范围 | `.../host/voice/speak.ts:21-25`（`RATE_PATTERN`/`-50`/`+100`） |
| 第三方超时 | `.../host/voice/speak.ts:27`（`PROVIDER_TIMEOUT_MS=15_000`） |
| 参数校验 | `.../host/voice/speak.ts:54-72`（text/voice/rate，未知 voice 报允许列表） |
| 串行队列 | `.../host/voice/speak.ts:85-102`（`queueUsed`/`chain`/`enqueue`） |
| 缓存命中/未命中/忙 | `.../host/voice/speak.ts:104-151`（`:105-112` 命中要求 `size>0`；`:129-131` 队列满；`:133-150` 合成） |
| 返回文件（audio/mpeg） | `.../host/routes/voice.ts:21-32`（`:31` `{kind:'file', contentType:'audio/mpeg'}`） |
| 音色白名单与缺省 | `.../host/voice/voices.ts:18-26` |
| 内置 edge 实现 | `.../host/voice/edge.ts:26`（15s）、`:57-69`（`.mp3.part` → rename；失败清 part 并抛 `VoiceSynthError`） |
| 缓存键与淘汰 | `.../host/voice/cache.ts:13-15`（20MiB/200）、`:34-36`（sha1 四元组）、`:55-90`（按 mtime 淘汰） |
| 客户端播放 | `.../shared/voice.ts:37`（20s）、`:126-137`（三道门）、`:151-175`（fetch→blob→Audio）、`:159`（content-type 必须含 `audio`） |
| 手动点播（掐旧句、世代号） | `.../shared/voice.ts:177-240` |
| 桌面端基址/面标识 | `dsh-pet/dsh-pet/runtime/electron-helper/renderer.js:66-68`（`setVoiceBase(BASE)` + `setSurface('desktop')` + `setVoiceConfig`） |
| **默认音色文档漂移** | `dsh-pet/openapi.yaml:2346`（"缺省 `zh-CN-XiaoxiaoNeural`"）vs `.../voices.ts:26`（`DEFAULT_VOICE='zh-CN-XiaoyiNeural'`） |

**对 Voice Assistant 的含义**

- 若 VA 通过 pet 出声：**必须把回复切成 ≤500 UTF-16 字符的片段**（建议按句切 60–120 字），并自己排队（pet 只允许 3 个在途）；MP3 是唯一可接受格式，VA Runtime 若产出 PCM/WAV/Opus，必须转码。
- **"播完"信号缺失**是硬约束：VA 的 `tts.finished` / `tts.interrupted` 事件**不能**从 pet 获得，只能由 VA 自己的播放器（若 VA 自己播）或超时估算（若 pet 播）驱动。若 VA 需要精确打断，**不应**把播放交给 pet。
- 客户端三道门意味着"没声音"可能有很多原因（`voiceTo` 未点名、页面 hidden、`voiceEnabled=false`、队列满、上游失败），VA 的诊断面板必须能区分；注意 `voiceEnabled` 默认 **false**（`dsh-pet/dsh-pet/assets/config.jsonc:86`），开箱即静音。
- 缓存 20MiB/200 文件落在 `$DSH_HOME/dsh-pet/voice-cache/`；VA 若绕过 pet 自己缓存，要避免同一句话被两处重复合成、重复占盘。
- 依赖 `@andresaya/edge-tts`（在线、非官方 Edge 端点、`package.json:104`）→ 离线场景不可用；VA 的本地 TTS 必须自己实现 provider，并在 `synthesize` 内做**可放弃**的取消（宿主超时不会取消原 Promise）。

---

## 12. 插件通信方式

**结论**

- dsh-pet **没有** WebSocket、没有 SSE、没有 UDP/多播、没有"广播"API。全部通道只有四类：
  1. **HTTP 轮询（唯一状态源）**：`GET /state`，支持 `?since=&timeout=` 长轮询（≤10s）；消费端"收到即再拉"，空闲时挂起。
  2. **HTTP 动作端点**：POST 触发行为，写 S，只回 `{ok}`（`/whisper`、`/chat` 额外带回生成文本）。
  3. **进程内 Cordis 服务**：`petApi7340`（宿主侧 register/list；页面侧只读快照/pose/progress/menuEvents），零网络。
  4. **桌面 Helper 管道**：宿主 `spawn` Electron 子进程，子进程渲染端把请求经自定义 scheme `dsh-pet-bridge://` 交主进程，主进程把一行 JSON 写 stdout（前缀 `dsh-pet-bridge:`）给宿主；宿主**应答**不走 stdin（Electron 读不到 piped stdin），而是 POST 到主进程起的本地回调 HTTP 服务。
- 事件面：DSH 的 `session/event` / `agent/error` 只被宿主**消费**（转成状态/通知/菜单），**不转发**给第三方；第三方要拿点击事件只能 `GET /menu/events`（读取即消费，可长轮询）。
- 通知是**单槽**：`sections.notify` 后写覆盖先写，不排队；只有网页端消费（桌面模式不弹 toast）。

**证据**

| 通道 | 证据 |
| --- | --- |
| 无 WebSocket/SSE | 全 `src/**` 检索 `WebSocket|EventSource|text/event-stream` 仅命中 `edge.ts:6` 注释（依赖内部用 WS）与测试桩；插件自身无服务端推送 |
| `/state` 长轮询 | `.../host/routes/state.ts:67-105`（`state.wait` + abort）；`.../host/state.ts:169-183`（等待者/超时/取消）、`:206-213`（写后唤醒，`since===last` 跳过） |
| 客户端自调度轮询 | `.../client/pet/state-poll.ts:32-52`（首拉探测 `counter` → 之后带 since → 失败/老宿主退避） |
| 动作端点只回执 | `.../host/routes/result.ts:66-69`（`okResult` 直接内联结果）；`openapi.yaml:37-58` |
| 进程内服务（宿主） | `.../host/plugin/setup.ts:176-187` |
| 进程内服务（页面） | `.../client/app.ts:78-83`；`.../client/state-service.ts:23-50`（最近一拍 + 订阅） |
| 桌面管道协议 | `.../host/helper/bridge.ts:10`（`BRIDGE_PREFIX`）、`:15-30`（`BridgeRequest/BridgeResponse`，`cb` = 本地回调地址；注释说明 electron#4218） |
| 管道装配 | `.../host/plugin/desktop/spawn.ts:126-139`（`bridgeHandler` = 同一个 `handlePetRoute` + `toBridgeResponse`） |
| 自定义 scheme | `dsh-pet/dsh-pet/runtime/electron-helper/main.js:144-161`（`registerSchemesAsPrivileged`）、`:243-252`（`protocol.handle('dsh-pet-bridge', …)` + `bridge.startCallback()`） |
| 渲染端基址 | `.../runtime/electron-helper/constants.js:134-135`（`BRIDGE ? 'dsh-pet-bridge://dsh-pet/dsh-pet-7340' : ORIGIN + '/dsh-pet-7340'`） |
| 菜单事件（读取即消费） | `.../host/routes/menu.ts:43-53`（`poll(owner, waitMs)`，`MENU_WAIT_MAX_MS` 封顶） |
| 通知单槽 | `openapi.yaml:3449-3455`；`.../host/plugin/session-watch.ts:261-311`（`pushNotifyFrame`，仅网页消费的注释 `:264`） |

**对 Voice Assistant 的含义**

- VA 的 PetBridge 只要实现"**一个长轮询读 + 若干 POST 写**"即可，不需要任何回调服务器；这大幅降低跨平台复杂度。
- 桌面的 `dsh-pet-bridge://` 与宿主管道是**私有协议**（`BridgeRequest` 无版本号、无鉴权、只在 pet 自己的进程间用），VA **不能**复用；VA 必须假定"HTTP 是唯一稳定面"。
- 若 VA 需要"用户点了桌宠/桌宠菜单项"这类事件：唯一可用的是 `/menu/*`（需自己注册 owner，且只支持"更多"子菜单），**没有**"点击宠物本体"的事件外泄（点击只触发内部动画/音效，`/menu/click` 是渲染端上报专用）。
- VA 自己的 Runtime↔Plugin 协议（任务书 §八）需要 WebSocket + 二进制帧，这部分**无法**从 dsh-pet 借鉴任何实现。

---

## 13. 桌面模式与 Web 模式差异

**结论**

- **判定依据是配置 `display`**（`web|desktop|both|none`，必填四值之一），不是运行时开关；同一只宠物可以在两端各渲染一份。
- Web 模式：DSH 页面内的 React overlay（`shell.overlay`），`/state` 由页面 `fetch` 拉；位置是**视口语义**；语音由页面 `Audio` 播；系统通知**只有网页端**弹 toast。
- 桌面模式：由宿主 `spawn` 的 Electron 子进程（每只 desktop 宠物一个局部小窗），渲染端是**经典 script + shared-core IIFE**（不是 React 客户端）；位置是**多显示器工作区并集的外接矩形**；`/pose` 只有桌面端有实况；语音基址走 `dsh-pet-bridge://`。
- 桌面模式又分两小类：
  - **DSH 主体 + Helper 子进程**（`DSH_PET_BRIDGE=1`）：HTTP 完全不经网络，走管道；无令牌。
  - **独立应用**（`dsh-pet-standalone` / Electron app，`DSH_PET_IN_PROCESS=1`）：单进程本机 HTTP + **进程能力令牌**（`x-dsh-pet-token`），并额外提供 `shutdownApp`（`/quit` 可用）。
- 宿主形态差异通过 `resolveOpenTarget()` 区分三种菜单首项（desktop / standalone / web）；`/quit` 在 DSH 内恒 `canQuit:false`；`/reload` 只重启 Helper；非图形环境（无 `DISPLAY`/`WAYLAND_DISPLAY`）直接跳过桌面 Helper。

**证据**

| 差异点 | 证据 |
| --- | --- |
| `display` 四值 | `.../host/surface.ts:14-17,33-44`；默认值 `.../assets/config.jsonc:250`（`"display": "both"`） |
| Web 只渲染 web/both | `.../client/pet/multi.ts:169-170`；桌面只渲染 desktop/both `.../runtime/electron-helper/renderer.js:74` |
| 两端坐标语义不同 | `openapi.yaml:718-732`（浏览器=视口；桌面=全部显示器工作区外接矩形，含多屏空洞夹取） |
| `/pose` 桌面专属 | `.../host/routes/motion.ts:146-158`（display 不含 desktop → `pet-not-displayed`；未上报 → `pose-unavailable`） |
| 网页端用 Cordis 读 pose | `.../client/pet/card/animation.ts:118-125`（`registerPose`） |
| 通知仅网页 | `.../host/plugin/session-watch.ts:261-264`（"通知是网页端能力，桌面模式不消费"） |
| 桌面渲染端形态 | `.../runtime/electron-helper/index.html:332-342`；`.../scripts/build-desktop-core.mjs:1-8` |
| 桌面语音基址 | `.../runtime/electron-helper/renderer.js:66`；`.../runtime/electron-helper/constants.js:135` |
| 管道模式（DSH） | `.../host/plugin/desktop/spawn.ts:126-137`（`DSH_PET_BRIDGE='1'`） |
| 独立应用模式 | `.../host/plugin/desktop/spawn.ts:73`（`DSH_PET_IN_PROCESS`）；`.../app/router.ts:116`（`listen(0,'127.0.0.1')`） |
| 独立模式令牌 | `.../standalone/request-security.ts:43`（32 字节随机）、`:58-89`（Host 头必须本机端口、Origin/Sec-Fetch-Site 校验、`publicRead` 只放行 GET 的部分路径、其余需 `x-dsh-pet-token` 43 字符且定时安全比较） |
| 桌面出站注入令牌 | `.../app/desktop-auth.ts:43-69`（仅"顶层 file 渲染端 + 本机 origin + 路由段"才加 `X-DSH-Pet-Token`，重定向不带） |
| `/quit` 仅独立模式 | `.../host/routes/desktop.ts:29-49`（`optionalService('shutdownApp')`，`canQuit` 软判） |
| 菜单首项三形态 | `.../host/plugin/desktop/spawn.ts:45-48`（`resolveOpenTarget`） |
| 无图形环境跳过 | `.../host/plugin/desktop/spawn.ts:165-176` |
| 桌面窗口/托盘/多屏 | `.../host/plugin/desktop/spawn.ts:104-112`（origin/`configUrl`）；`.../runtime/electron-helper/main/*.js`（windows/tray/displays/dpi） |

**对 Voice Assistant 的含义**

- **VA 的"桌宠联动"在 Web 模式与桌面模式下的可见效果不同**：`/position`、`/pose`、窗口行为只在桌面端有意义；VA 的状态文案（气泡）两端都能显示。
- 若 VA 需要"桌宠出现在桌面上（不在浏览器标签里）"：必须确保用户装了带 `display: desktop|both` 的宠物，且 DSH 能拉起 Electron Helper（首次可能要下载 Electron）；在 Linux 无显示环境会静默跳过（只有 warn 日志）。
- **VA 不要依赖 `X-DSH-Pet-Token`**：那是独立模式内部凭证，DSH 主体模式下 pet 路由无令牌；VA 若自己起 HTTP 服务，必须实现自己的令牌（任务书 §八/§十二要求）。
- 桌面 Helper 是 pet 自己的子进程，VA 无法复用它来"跑自己的 UI"；VA 若要有桌面悬浮 UI，需要自己的 Electron/原生方案（或完全走 DSH Web UI）。
- 语音"由哪端念"（`voiceTo`）是 pet 解决"两端都渲染同一只宠物会重复出声"的机制；VA 若两端都可能渲染，必须用类似机制或直接禁用其中一端。

---

## 14. 可复用接口（PetBridge 映射）

**结论**：任务书 §十 列的 8 个能力，dsh-pet 的真实支持度如下（全部已核到源码）：

| PetBridge 方法 | 可用性 | 真实接口 | 备注 |
| --- | --- | --- | --- |
| `getState()` | ✅ | `GET /state`（长轮询 `?since=&timeout=`）；或同页 Cordis `petApi7340.getState()`（只读快照） | 快照含全部叶子；`counter` 判变化 |
| `setWorkStatus()` | ⚠️ 受限 | `POST /work-status` / `DELETE /work-status` | 单槽 `api`、6 档、`task≤40` 码点、last-writer-wins、与真实会话共享优先级 |
| `broadcast()` | ✅ | `POST /broadcast?pet=&surface=`（`text` + 可选 `image|url`、`duration`、`anim`） | 需 `pet` 必填、`surface` 必填；受锁/睡眠门禁；无长度/频率限制 |
| `playAnimation()` | ✅（受池约束） | `POST /anim?pet=&surface=`，`name` 或 `url`，可选 `facing` | 名字必须在配置池；`url` 需 http(s)+CORS；回 `playbackId` |
| `acquireLock()` | ✅ | `POST /lock?pet=&surface=`，可带 `ttl` | 单槽、TTL 1s–30min、懒过期、需心跳续期 |
| `releaseLock()` | ✅ | `POST /lock/release?pet=`，`lockId` 或 `force:true` | 幂等；force 只给渲染端用 |
| `wake()` | ✅ | `POST /wake?pet=` | 幂等，回 `changed`；会弹"起来"台词 |
| `sleep()` | ✅ | `POST /sleep?pet=` | 若无可睡动画 → `no-sleep-animations`；被占用 → `locked` |
| （额外）`move()` | ✅ | `POST /position?pet=&surface=` | `mode: instant/spring/line`；坐标为宠物中心 |
| （额外）`throw()` | ✅ | `POST /throw?pet=&surface=` | `angle` 度、`power>0` |
| （额外）`clearBubble()` | ✅ | `POST /bubble/clear?pet=&surface=` | 只清说话气泡 |
| （额外）`getPose()` | ⚠️ 桌面专属 | `GET /pose?pet=` | 仅 `display` 含 desktop |
| （额外）`playbackWait()` | ✅ | `GET /playback/{id}?wait=ended&timeout=` | 播放真实回执（不覆盖音频） |
| 订阅事件 | ❌ | 无 | 只能轮询 `/state`；菜单点击用 `GET /menu/events`（读取即消费） |
| 读取 `lockId` | ❌ | 无 | `/state` 的 `lock` 叶子**故意不含** `lockId`（`.../host/lock.ts:38`、`shared/state.ts:272`） |
| 播放音频 | ❌ | 无宿主音频 API | `/voice/speak` 只产 mp3；播放由渲染端 `Audio` 完成 |
| 设置任意 Avatar 状态 | ❌ | 无 | 只有 6 档 `workStatus` + 动画/气泡/位置/锁/睡眠 |

**证据**

- 状态：`.../host/routes/state.ts:67-105`、`.../client/app.ts:78-83`、`.../shared/state.ts:45-87`
- 工作状态：`.../host/routes/state.ts:110-152`、`.../host/work-status.ts:149-156`
- 投喂：`.../host/routes/interaction.ts:108-162`、`.../host/broadcast.ts`（`decideBroadcast`）
- 动画：`.../host/routes/motion.ts:28-66`、`.../host/anim.ts:121-171`
- 锁/睡眠/唤醒：`.../host/routes/interaction.ts:32-71`、`.../host/routes/sleep.ts:17-57`
- 位置/抛掷：`.../host/routes/motion.ts:73-117`
- 回执：`.../host/routes/playback.ts:23-91`
- 无 `lockId` 的设计理由：`.../host/lock.ts:38`（leaf 只有 `locked/expiresAt`）、`.../shared/state.ts:272`（"不含 lockId：那是持锁者的凭证"）

**对 Voice Assistant 的含义**

- VA 的 `PetBridge` 抽象可以按上表 1:1 落地，**不需要**任何私有协议；建议把"不可用能力"显式建模（`supported: false`），而不是静默 no-op（任务书 §十："如果某项能力没有公开 API，则标记为不支持，不允许伪造"）。
- `setWorkStatus` 是**最容易被误用**的一个：VA 不应把 Voice State 写进这里去"模拟"LISTENING/SPEAKING，否则会与真实 Agent 状态互相踩。推荐：`lock` 表达"VA 正在控制"，`/anim` 表达"听/说"，`/broadcast` 表达"提示语"，`workStatus` 只在"VA 代表一次真实 DSH 任务进度"时用。
- `getState()` 建议做成**单例长轮询**（一进程一个轮询器），并把叶子分发做成事件（`state.workStatus.changed` / `state.pet.<id>.anim`），否则 VA 多模块各自拉会放大请求。
- `broadcast` + `clearBubble` 足以实现"VA 的状态提示气泡"；注意 `duration` 默认 10s、`0` = 不显示、`anim:false` = 只弹气泡不联动动画（`.../shared/state.ts:180-190`、`openapi.yaml:143-146`）。

---

## 15. 潜在兼容性风险

按"会不会让 VA 直接坏掉"排序。

### 15.1 版本与依赖门（高）

- **结论**：dsh-pet 对 DSH 的兼容声明是"点版本清单 + 宽范围 peer"，不是一个可计算的区间；`engines.node >= 22.12.0`。
- **证据**：`dsh-pet/dsh-pet/package.json:100-102`（node ≥22.12.0）、`:129-142`（`@deepseek-ai/cordis ^4.0.4`、`dsh-client-connection/ui-primitives/ui-slots/commands/credentials/home-paths/host-webserver/llm ^0.2.0-rc.1`、`react ^18.2`）、`:111-121`（`dshReleases` 只列 3 个版本；注释 `:33` 明说"不进安装闸门"）。
- **含义**：VA 若与 dsh-pet 同 profile 安装，**任何一方升级都可能把另一方挤掉**（peer 冲突或 DSH 版本不在清单）。VA 必须做**运行时探测 + 软降级**（`ctx.get('petApi7340')` 拿不到、`/state` 404、`reason: unknown-pet`），不能把桌宠联动设为硬依赖。

### 15.2 桌面 / Electron 专属（高）

- **结论**：桌面联动需要 Electron Helper；DSH Desktop 2.0.3+ 会拦"插件自拉进程的裸 HTTP 请求"，pet 因此改用管道；无图形环境直接跳过。
- **证据**：`.../host/plugin/desktop/spawn.ts:104-112`（注释明说"DSH Desktop 2.0.3+ 会拦插件自拉进程的裸 HTTP 请求，浏览器访问闸门只放行带令牌的请求"）、`:165-176`（无 DISPLAY/WAYLAND 跳过）、`:177-207`（下载 Electron 到 DSH_HOME）、`package.json:106-107`（`@electron/get`、`extract-zip`）。
- **含义**：VA 若想"桌面悬浮 + 语音"，不能假设 pet 的 Helper 一定在跑；桌宠可能只存在于浏览器。VA 也不应依赖 `dsh-pet-bridge://`（私有 scheme，仅 Helper 内部注册）。

### 15.3 文档/实现漂移（中）

| 漂移 | 文档 | 实现 | 影响 |
| --- | --- | --- | --- |
| 默认音色 | `openapi.yaml:2346` 写 `zh-CN-XiaoxiaoNeural` | `.../host/voice/voices.ts:26` 是 `zh-CN-XiaoyiNeural` | 按 openapi 生成客户端会算错缓存键/展示默认值（合成结果不同） |
| `/sleep` 的 `?lock=` | `openapi.yaml:1146` 声明 `LockQuery`，`:1152` 列 `lock-required/lock-lost`，`:1140` 称"带 lock= 不受睡觉限制" | `.../host/routes/sleep.ts:41` 只判 `lock.locked()` → `locked`，**从不调用 `lock.gate`** | 第三方按文档"带锁入睡"会失败；文档与实现语义相反 |
| 插件 `name` | `cordis.patch.yml:24` entry `id: dsh-pet` | `.../host/index.ts:29` `name='pet'`（注释还写"与 cordis.patch.yml 一致"） | Loader 侧影响**待验证**（可能只影响插件显示名/去重键），但注释与事实矛盾，是维护陷阱 |
| 客户端 `getState` 叶子集合 | `dsh-pet/CORDIS.md:76` 只列 5 个（无 `sleep`） | `.../shared/state.ts:120,130` 有 6 个（含 `sleep`） | 消费者若按文档穷举会漏掉睡眠状态 |
| 音色数量/默认 | `openapi.yaml:2346` | `voices.ts:18-23` 共 4 个，`default:true` 是 XiaoyiNeural | 同上 |

### 15.4 鉴权与暴露面（中）

- **结论**：DSH 主体模式下 pet 的 HTTP **零鉴权**；只有独立模式有进程令牌。
- **证据**：`openapi.yaml:19`（"没有任何鉴权"）；`.../host/plugin/http-route.ts:72-113`（无校验）；`.../standalone/request-security.ts:58-89`（独立模式才有 `x-dsh-pet-token`）。
- **含义**：VA 与 pet 的调用链上任何本机进程都能伪造；VA 的"危险操作确认"不能依赖 pet 的任何身份信息（它没有）。VA 自己对外暴露的接口必须自带令牌 + localhost + Origin 校验（可参考 `request-security.ts` 的做法，但**不要**复用其 43 字符 token 形状假设）。

### 15.5 单文件加载约束导致的重复类型（中）

- **结论**：Host 不得 import `src/shared`，导致 `PetLeafName`、`PetFacing`、`PositionMode`、`VoiceTarget`、`WorkStatusState` 等**各写两份**，且注释要求"改动时两边一起改"。
- **证据**：`.../host/state.ts:5`、`.../host/anim.ts:6-8,19-21`、`.../host/motion-cue.ts:16-20`、`.../host/surface.ts:46-47`、`.../shared/state.ts:192-193,305-306`。
- **含义**：VA 若 fork/内联这些类型，必须建立**契约测试**（例如用同一份 JSON 样例同时喂两端 parser），否则两边会静默分叉。

### 15.6 构建目标陷阱（中）

- **结论**：es2020 目标会把 class field 降级成 `@oxc-project/runtime` helper，而该包**不在依赖里** → 宿主加载插件树时 `ERR_MODULE_NOT_FOUND`，整个 profile 起不来。
- **证据**：`.../host/work-status.ts:182-184`（注释）、`.../host/lock.ts:100-102`、`.../host/state.ts:93-95`；`.../tsdown.config.mjs:60-67`（standalone/app 提到 es2022 以避开）；`.../scripts/prepack-check.js` 第 8 项（注释提及）。
- **含义**：VA 若也打 ESM 单文件给 DSH Loader，**必须**用 `declare` + 构造器赋值（或把 target 提到 es2022 并确认 DSH 的 Node 版本）；CI 必须有一个"加载产物"的冒烟测试，而不是只跑 `tsc --noEmit`。

### 15.7 端口未就绪竞态（中）

- **结论**：`ctx.webServer.port` 可能在 apply 时仍为 0，pet 用 500ms 轮询等待，最多无限重试（每 20 次打一条 warn）。
- **证据**：`.../host/plugin/desktop/spawn.ts:80-102`。
- **含义**：VA 若在启动时就要拼 pet 的基址，不能把 port=0 当最终值；必须"每次请求现算基址"或"等到非 0 再连"。

### 15.8 长轮询与 DSH 空闲超时（低/待验证）

- **结论**：pet 自己承认"DSH WebServer 是否对长期持有的响应设了空闲超时尚未核实"，因此把挂起上限压在 10s。
- **证据**：`.../host/state.ts:41-44`（注释原文）。
- **含义**：VA 的长轮询 `timeout` 也应 ≤10s；若 VA 自建 Runtime WS，不受此限，但插件→pet 的轮询受限。

### 15.9 死分支 / 可疑逻辑（低，但会造成"以为被拦其实没拦"）

| 现象 | 证据 | 后果 |
| --- | --- | --- |
| `sleepGated` 里的 `rest === 'voice'` 永远不匹配（真实 rest 是 `voice/speak`、`voice/voices`） | `.../host/routes/index.ts:61` + `.../host/routes/voice.ts:16,21` | 睡觉期间 `/voice/speak` **不会**被拦（且该 gate 只在有 `?pet=` 时生效，TTS 端点本就没有 pet） |
| `sleepGated` 未包含 `/sleep`、`/wake`、`/lock` | `.../host/routes/index.ts:51-63` | 睡眠期间仍可取锁（取锁会唤醒，符合语义）、仍可醒来 |
| `WorkStatusSnapshot.ts` 从未写进叶子 | `.../host/work-status.ts:134` 有 `ts`，`.../host/plugin/work-status-bridge.ts:55` 只写 `{state,task}` | 消费端拿不到 `ts`（只有 `counter`），与 `openapi.yaml:3424-3440` 一致，但读源码易误判 |

### 15.10 第三方 TTS 上游（中）

- **结论**：内置 TTS 依赖 `@andresaya/edge-tts`（在线 Edge 端点，非官方、可能变更/限流），且是**运行期可选依赖**（按需 `require`）。
- **证据**：`.../package.json:104`；`.../host/voice/edge.ts:1-9,57-69`；`.../host/voice/speak.ts:114-151`（失败只回 `generate-error`，细节只进日志）。
- **含义**：VA 不能把"pet 能出声"当成离线保证；VA 的引擎适配器必须自己实现本地 TTS，并把 pet 的 edge 视为"可选的在线兜底"。

### 15.11 许可证（低）

- **结论**：dsh-pet 是 **MIT**（`dsh-pet/LICENSE:1`、`dsh-pet/dsh-pet/package.json:99`），可安全参考/复制片段（仍需保留版权声明）。
- **证据**：同上；对照任务书"未经许可证评估不得复制 GPL"的要求，dsh-pet 无此风险。
- **含义**：VA 可复用其状态机/JSONC 解析/契约写法；但 `assets/` 下的图片/动画/表情包是**内容素材**，其授权需单独评估（仓库 LICENSE 是否覆盖 assets 需法务确认，标为"待验证"）。

---

## 16. 未验证 / 待验证清单

1. **`name='pet'` 与 entry `id='dsh-pet'` 不一致的实际后果**（`.../host/index.ts:29` vs `cordis.patch.yml:24`）——需要 DSH Loader 源码（任务 C）确认 `name` 是否参与 entry 匹配/去重。
2. **DSH WebServer 对长连接的 idle timeout**（`.../host/state.ts:41-44` 自述未核实）。
3. **DSH 是否对插件路由另有浏览器访问闸门**：`.../host/plugin/desktop/spawn.ts:105-111` 提到"浏览器访问闸门只放行带令牌的请求"，但 pet 路由本身无令牌，说明闸门在 DSH 层；其判定规则未在本地核实。
4. **`@andresaya/edge-tts` 的上游可用性/限流/ToS**（在线依赖，未联网验证）。
5. **Electron 首次下载**（`@electron/get` + `extract-zip`）在受限网络/代理下的行为（未实际跑）。
6. **`/sleep` 的 `?lock=` 语义**：文档说"带锁不受睡觉限制"，源码只判 `locked`；需确认是否有意为之（可能是文档超前）。
7. **`assets/` 素材的授权范围**（代码 MIT，素材是否同许可未在仓库内声明）。
8. **桌面多屏坐标夹取**（`clampReachableBox`/`relayout`）在真实多屏下的表现——有单测（`.../src/client/pet/motion/geometry.test.ts` 等），但未做真机验证。
9. **DSH 版本矩阵**：`dsh.compatibility.dshReleases` 只覆盖 3 个版本，当前用户实际 DSH 版本未知。
10. **`check-openapi.mjs` 是否在所有 CI 上执行**：仅在 `prepack` 链（`package.json:87`），本地开发/PR 是否跑需看 `.github/workflows`（本次未逐条核对 workflow 触发条件）。

---

## 17. 对 Voice Assistant 的落地约束（结论性建议）

1. **PetBridge 用 HTTP 长轮询 + 动作端点**，单一轮询器；基址每次现算（`http://127.0.0.1:{webServer.port}/dsh-pet-7340` + 可能的挂载前缀）；按 `reason` 分支而非状态码。
2. **Avatar 状态映射表**（VA 8 态 → pet 能力）：`IDLE→释放锁 + 无 workStatus`；`LISTENING→锁 + /anim(听) + /broadcast(短提示)`；`THINKING→workStatus thinking（仅当无活动会话）`；`WORKING→workStatus working`；`SPEAKING→锁 + /anim(说)`；`CONFIRMATION→workStatus waiting`；`SUCCESS/ERROR→workStatus success/error（60s 后自动清）`。**不得**用 `workStatus` 模拟 `LISTENING/SPEAKING`。
3. **TTS 播放权威二选一**：要么 VA Runtime 播（推荐，能精确打断），pet 只做动画/气泡且 `voiceEnabled=false`；要么注册 pet 的 `voice.register` 让 pet 两端播（无法拿到播完事件、影响全插件、与其它 TTS 插件互斥）。**禁止**两条同时开。
4. **锁纪律**：取锁 → 每 20s 续期（TTL 60s）→ 结束/异常/卸载必须释放；收到 `locked` 退避，收到 `lock-lost(preempted)` 立即收尾并上报"被用户接管"。
5. **文本纪律**：`/broadcast` 无长度/限频 → VA 侧截断 + 合并 + 最小间隔；`/work-status.task` ≤40 码点；`/voice/speak.text` ≤500 UTF-16 字符且按句切分。
6. **契约纪律**：把 pet 的 `reason` 联合（`result.ts:15-46`）与 `PetLeafName`/`SectionLeafName` 抄进 VA 的协议包，并写"契约快照测试"；对 `counter` 缺失（老宿主）走退避轮询。
7. **隔离纪律**：桌宠不可用（未安装/版本不兼容/无 desktop 显示/无图形环境）时，VA 必须完整降级（语音功能不依赖桌宠），且 UI 明确显示"桌宠未连接"。
8. **不要复用**：pet 的 `src/**` 内部实现、`dsh-pet-bridge` 私有管道、Electron Helper、`ctx.llm` 直连模型的对话路径、`name='pet'` 这类与 patch 不一致的声明。

---

*本文档所有结论均可由所列「路径:行号」在 commit `38306ec` 上复核；标注「待验证」的条目需要在任务 C（DSH 插件机制）或真机环境中补证。*
