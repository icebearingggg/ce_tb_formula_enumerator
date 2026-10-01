# 验证报告

验证日期：2026-09-30（Asia/Hong_Kong）

## 环境隔离

- 操作系统：Windows 10 `10.0.19045`，64 位。
- 基础解释器：CPython 3.11.9（系统安装的 Python 3.11）。
- 项目解释器：`<project>\.venv\Scripts\python.exe`。
- 创建前未激活虚拟环境，项目根也没有既有 `.venv`；新环境由 Python 标准库 `venv` 创建。
- 环境核对确认 `sys.prefix` 位于项目 `.venv`，`sys.base_prefix` 指向基础 Python；pip 也位于项目 `.venv`。
- 未升级全局 Python、全局 pip，未使用或修改 CrystalFormer、ORB、CP2K 等环境。

实际验证版本：程序 0.1.0、pip 24.0、pymatgen 2026.9.24、pytest 9.1.1。`python -m pip check` 报告 `No broken requirements found.`

## 自动测试

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：`16 passed in 10.32s`。

验证范围包括所有题定数值案例和拒绝案例、小计量范围的独立直接穷举集合对拍、约化去重、多价 M 假设归并、配置错误、UTF-8 BOM、中文和空格路径、CSV 换行、输出回读、重复运行，以及默认禁止覆盖且拒绝后文件哈希不变。

## 默认配置运行

默认输出位于本地 `results/default_run`（生成数据体量较大，不纳入版本控制）。运行结果：

- 唯一组成：34,648。
- 去重后的可行电荷假设：37,946。
- Ce-only：7,591；Tb-only：7,591；Ce/Tb-mixed：19,466。
- 氧化物：2,302；氟化物：2,636；氟氧化物：29,710。
- 约化/过滤前电荷构造路径：54,764。
- 因 `n_fu > 24` 过滤的路径：12,031（一个路径只计首个失败原因）。
- 归并掉的重复约化电荷假设观测：4,787。
- 摘要记录的枚举阶段耗时：4.158899 秒；文件写出时间不包含在该数值中。

对同一默认配置另行运行后，比较器报告：`MATCH: 34648 composition keys and normalized charge hypotheses`。输出行数核对为 34,648 条组成、34,648 条 JSONL 记录、34,648 个化学式；假设列表合计 37,946 条，与摘要一致。再次对默认目录运行且不带 `--overwrite` 时退出码为 2，四个已有输出未改变。

## 验收案例抽查

程序输出并测试确认：CeO2 为 `z_RE=4, k=1`；Ce2O3 为 `3,0`；TbOF 为 `3,0`；CeTbO3F 为 `7/2,1`；Ce2CaO4（Ca +2）为 `3,0`；Tb3KF12（与 KTb3F12 为同一组成，K +1）为 `11/3,2`。CeFeO3 只有一个组成，并同时保留 Fe +2/Ce 需求 +4 与 Fe +3/Ce 需求 +3 两条假设。Ce2O4 约化归并到 CeO2；CeO 和 CeOF3 被当前 +3/+4 模型拒绝。

化学式显示使用固定的领域顺序 `Ce, Tb, M, O, F`，因此 K/Tb 示例显示为 `Tb3KF12`；其 `composition_key` 与 pymatgen 回读组成和 `KTb3F12` 完全相同。显示字符串不参与唯一性判定。

## 未解决项与迁移状态

未发现影响当前范围的已知代码问题。本程序有意不判断稳定性、可合成性、真实氧化态、结构新颖性或数密度，也不覆盖 M 自身混合价态。

Windows 已完成环境、测试、默认运行、覆盖保护及可复现性验证。当前没有 Linux 执行环境，因此 Linux 尚未实测；迁移后必须按 README 重建 Linux `.venv`、重跑测试和默认枚举，并使用 `scripts/compare_core_outputs.py` 完成跨平台核心结果验收。

## 2026-10-01 输出事务与空 M 池修复验证

本次在原有项目 `.venv` 中完成 Windows 本地修复，没有重建环境或安装、升级依赖。实际环境仍为 CPython 3.11.9、pip 24.0、pymatgen 2026.9.24、pytest 9.1.1；解释器和 pip 均位于 `<project>\.venv`。`python -m pip check` 再次报告 `No broken requirements found.`

完整测试命令：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

结果：`26 passed in 4.90s`。新增回归覆盖同盘完整暂存、暂存写入失败不修改正式输出、发布中途失败完整回滚、无原始输出和部分原始输出的存在状态恢复、回滚失败时保留恢复材料并阻断后续写入、成功覆盖四件套、无关文件保持不变、默认拒绝覆盖、异常目录目标和 CLI 文件系统错误。故障均通过 monkeypatch 注入，不依赖填满磁盘或修改系统权限。空 M 池测试确认配置可加载、结果非空且全部 `c=0`/M 为空，并与同预算完整枚举的无 M 组成键及电荷假设集合完全一致；非字典池和空价态列表继续被拒绝。原有科学验收、直接穷举对拍、中文与空格路径、重复运行、约化和混合价态测试继续通过。

使用未修改的 `config/default_config.json`（仍含 27 个 M 元素）运行到新目录 `results/default_run_transaction_fix_20261001`，未覆盖 `results/default_run`。新运行统计为：

- 唯一组成：34,648；可行电荷假设：37,946。
- Ce-only：7,591；Tb-only：7,591；Ce/Tb-mixed：19,466。
- 氧化物：2,302；氟化物：2,636；氟氧化物：29,710。
- CSV 数据行、JSONL 行和化学式行均为 34,648；成功后没有 `.ce-tb-output-stage-*` 或 `.ce-tb-output-recovery` 残留。

本地存在修改前的完整默认输出，因此执行了集合级比较，而不只是计数比较：

```powershell
.\.venv\Scripts\python.exe .\scripts\compare_core_outputs.py `
  .\results\default_run `
  .\results\default_run_transaction_fix_20261001
```

结果：`MATCH: 34648 composition keys and normalized charge hypotheses`。

本次实际验证平台仅为 Windows。没有运行 Linux，因此不声称本次修改已在 Linux 实测；测试和实现避免硬编码本机路径，并使用 Python 标准库的跨平台文件 API，为后续 Linux 验收保留相同命令和故障注入测试。事务保证限于可捕获运行错误下的回滚；发布仍是逐文件替换，不是四文件瞬时原子切换，也不完全覆盖断电、操作系统崩溃或强制终止。

## 2026-10-01 发布后清理状态修补验证

本次继续使用项目既有 `.venv`，未安装或升级依赖。实际环境为 Windows、CPython 3.11.9、pip 24.0、pymatgen 2026.9.24、pytest 9.1.1；`python -m pip check` 报告 `No broken requirements found.`

恢复记录现区分四种状态：真正回滚未完成的 `recovery_failed`、原始输出已恢复而仅清理失败的 `rolled_back_cleanup_failed`、新输出已完整发布而仅清理失败的 `published_cleanup_failed`，以及正式输出未改变而发布前材料清理失败的 `prepublish_cleanup_failed`。`manifest.json`、`RECOVERY_REQUIRED.txt` 和抛出的错误信息使用一致语义；后三种状态不会再指示用户执行不必要或有风险的旧备份恢复。

新增两个故障注入测试，均使用临时目录和 monkeypatch：

- 四个不同配置的新输出全部发布后，模拟先删除一个旧备份、再令恢复目录清理抛出 `OSError`。验证正式四件套仍完整属于新运行，状态为 `published_cleanup_failed`，说明明确要求保留新结果且禁止恢复可能不完整的旧备份，剩余恢复材料保留，后续覆盖被阻止。
- 发布中途失败且自动回滚成功后，模拟相同的部分清理错误。验证原始四件套已完整恢复，状态为 `rolled_back_cleanup_failed`，说明明确要求保留已恢复结果且不要再次恢复，剩余材料保留，后续覆盖被阻止。

完整测试结果为 `28 passed in 4.77s`。原有发布失败回滚、回滚失败保护、空 M 池、科学验收、小空间直接穷举、约化、混合价态、中文与空格路径测试全部继续通过。

未修改默认配置，并将默认枚举写入新目录 `results/default_run_cleanup_state_fix_20261001`，未覆盖已有结果。统计仍为 34,648 个唯一组成和 37,946 条可行电荷假设；成功后没有暂存或恢复目录残留。与上一版 `results/default_run_transaction_fix_20261001` 进行集合级比较，结果为：`MATCH: 34648 composition keys and normalized charge hypotheses`。

本次仅在 Windows 实际运行验证，没有 Linux 实测，因此不声称 Linux 已通过。实现继续使用 Python 标准库跨平台文件 API，测试不依赖真实磁盘耗尽或权限修改。清理仍是逐项文件系统操作，不具有多文件原子性；报告写入采用尽力而为，失败时不会主动删除剩余恢复材料或掩盖原始错误。
