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
