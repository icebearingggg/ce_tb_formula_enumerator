# 高 Ce/Tb 含量化学式枚举器

本项目完整枚举约化的 `Ce_a Tb_b M_c O_m F_n` 整数组成，并用指定的形式价态模型检查电荷可行性。它只产生供 CrystalFormer 前处理使用的组成目录，不生成结构，也不预测稳定性、可合成性、实际氧化态或结构新颖性。

## 科学模型

- Ce、Tb 各允许形式价态 `+3/+4`；`k` 是每个约化式中所需的四价 Ce/Tb 总数，不指定四价位于 Ce、Tb 或任何晶位。
- O 固定为 `-2`，F 固定为 `-1`。
- 每条 M 电荷假设只使用一种统一价态；M 自身混合价态不在第一版范围内。
- 默认 M 池、价态、排除规则和预算均在 [`config/default_config.json`](config/default_config.json) 中。排除规则只是项目范围选择，不能解释为未排除元素或所得化合物安全、稳定或可合成。
- 枚举使用整数电荷等式；约化后重新计算 `k` 和 `z_RE_required`。pymatgen 用于解析并交叉验证最终组成，不使用其默认氧化态猜测。
- `x_RE` 是阳离子中的 Ce/Tb 分数；`c_RE` 是总原子分数；`r_Ce` 和 `y_F` 分别描述 Ce/Tb 与 O/F 比例。没有晶胞体积，因此不计算 `rho_RE`。

## 环境与安装

支持 Python `>=3.10,<3.14`。`.venv` 是机器相关产物，不应复制到另一台机器。

Windows PowerShell（无需激活环境）：

```powershell
cd C:\path\to\ce_tb_formula_enumerator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pip check
```

如果 `python` 不是期望解释器，先用该解释器的完整路径执行 `-m venv`。创建后可用以下命令核对隔离：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.prefix); print(sys.base_prefix)"
.\.venv\Scripts\python.exe -m pip --version
```

Linux（重新创建环境，不复制 Windows `.venv`）：

```bash
cd /path/to/ce_tb_formula_enumerator
python3.11 -m venv .venv
./.venv/bin/python -m pip install -e '.[test]'
./.venv/bin/python -m pip check
```

项目仅直接声明运行依赖 `pymatgen`，测试依赖为 `pytest`。没有 SMACT 或联网数据库依赖。默认运行的实际版本写入 `run_summary.json`；本次 Windows 验证版本另见 `VALIDATION_REPORT.md`。不要把 `pip freeze` 的全部传递依赖当作项目的手工依赖清单。

## 运行

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m ce_tb_enumerator --config .\config\default_config.json
```

Linux：

```bash
./.venv/bin/python -m ce_tb_enumerator --config ./config/default_config.json
```

配置中的相对输出路径相对于配置文件目录解析。命令行覆盖路径相对于当前工作目录解析：

```powershell
.\.venv\Scripts\python.exe -m ce_tb_enumerator `
  --config ".\config\default_config.json" `
  --output-dir ".\results\另一次 运行"
```

默认拒绝覆盖四个命名输出文件，并在写入前统一检查。确需替换时显式添加 `--overwrite`。模块导入不会启动枚举，枚举没有随机抽样或静默截断。

只运行无 M 搜索时，复制默认配置并仅把 `elements.additional_element_pool` 改为空对象：

```json
"additional_element_pool": {}
```

空 M 池只枚举 Ce–O–F、Tb–O–F 和 Ce–Tb–O–F；输出中的 `c` 为 0、`M` 为空，电荷假设中的 `M_oxidation_state` 为 `null`。默认配置本身仍保留原有 27 个 M 元素。非空 M 池中每个元素仍必须提供至少一个合法正整数价态。

## 输出

- `compositions.csv`：每个约化组成一行，CSV 使用 UTF-8、稳定字段和 LF 行尾。
- `charge_hypotheses.jsonl`：每个组成一行，保留全部去重后的电荷假设；`z_RE_required` 同时保存数值和精确分数字符串。
- `formulas.txt`：按稳定规则排序、每行一个普通整数化学式。
- `run_summary.json`：生效配置、版本、计数、分类、过滤/去重口径和运行元数据。

`composition_key` 按元素符号排序后的约化整数计数生成，是去重依据；`composition_id` 是该键 UTF-8 字节的 SHA-256。化学式的显示顺序不参与去重。

组成排序依次使用 Ce-only、Tb-only、Ce/Tb-mixed 分支，氧化物、氟化物、氟氧化物类别，M 的原子序数以及约化后的 `a,b,c,m,n` 和 `composition_key`。化学式显示顺序固定为 `Ce,Tb,M,O,F`，省略 0 和 1；因此显示顺序可能不同于 pymatgen 的习惯式，但解析组成完全相同。

### 覆盖、回滚与恢复材料

程序先在输出目录内的 `.ce-tb-output-stage-*` 临时目录生成完整四件套；全部准备成功后，才在同一文件系统内发布。覆盖已有结果时，旧文件及其原始存在状态保存在固定目录 `.ce-tb-output-recovery`。可捕获的文件写入或替换错误会触发四个命名输出的整体回滚：原有文件恢复，原先不存在的文件重新变为不存在；其他文件不参与事务，也不会被修改或删除。成功发布或成功回滚后会清理临时材料。

这是带恢复的逐文件替换，不是四个文件在同一瞬间切换的多文件原子事务，也不能保证在断电、操作系统崩溃或进程被强制终止时自动完成回滚。不要让多个进程同时写入同一个输出目录。

如果自动回滚或清理失败，程序会保留 `.ce-tb-output-recovery/manifest.json`、尚存的 `*.backup`，并尽可能写入 `RECOVERY_REQUIRED.txt`；错误消息会给出该目录。检测到这个目录时，程序会拒绝再次写入。先停止所有写入进程并保留恢复目录，再按清单中的 `status` 处理：

- `recovery_failed`：发布失败且自动回滚未完成。读取每个文件的 `originally_existed` 和 `backup`，用尚存备份恢复原先存在的输出，并删除原先不存在却被部分发布的命名输出；核对原始四件套恢复一致后再移走恢复材料。
- `rolled_back_cleanup_failed`：发布失败，但原始输出已经完整恢复，失败只发生在随后清理恢复材料时。保留并核对正式目录中的原始输出，不要再次从备份恢复；核对后只移走残留恢复材料及清单记录的暂存目录。
- `published_cleanup_failed`：四个新输出已经完整发布，失败只发生在清理旧恢复材料时。保留并核对正式目录中的完整新结果，不要从可能已不完整的旧备份恢复；核对后只移走残留恢复材料及清单记录的暂存目录。
- `prepublish_cleanup_failed`：新结果尚未发布，正式命名输出未改变，失败发生在发布前恢复材料的清理。保留并核对当前正式输出，不要从部分备份恢复；核对后只移走残留恢复材料。

清理本身也是逐项文件系统操作，不具有多文件原子性，因此清理失败时某些旧备份可能已经不存在。若清单、说明或恢复材料不完整，先复制保存整个恢复目录再诊断，不要把一种状态的恢复步骤套用到另一种状态。

## 测试

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Linux：

```bash
./.venv/bin/python -m pytest
```

测试覆盖题定的 10 项数学验收、小范围独立直接穷举对拍、预算边界、空 M 池与无 M 子集一致性、多价 M 归并、非法配置、UTF-8 BOM、中文和空格路径、重复运行、默认禁止覆盖、暂存/发布/回滚故障注入、部分原始状态恢复、恢复材料保护，以及全部输出化学式的 pymatgen 回读。

## Linux 迁移验收

通过 U 盘复制源码、`config/`、`scripts/`、`tests/`、`pyproject.toml`、README、报告和需要保留的 `results/`。不要复制或使用 Windows 的 `.venv`、解释器、缓存和已安装二进制包。在 Linux 按上面的命令重建 `.venv`、运行测试，并把默认枚举写到一个新目录：

```bash
./.venv/bin/python -m ce_tb_enumerator \
  --config ./config/default_config.json \
  --output-dir ./results/linux_default
./.venv/bin/python ./scripts/compare_core_outputs.py \
  ./results/default_run ./results/linux_default
```

比较工具只比较 `composition_key` 集合及规范化后的电荷假设，忽略时间戳、路径、平台和解释器元数据。当前交付仅在 Windows 实测；Linux 必须在工作站迁移后完成验收。

## 许可证

本项目采用 [MIT License](LICENSE)。

## 配置约束

JSON 以 UTF-8 或 UTF-8 BOM 读取。未知字段、未知元素、M 与排除规则冲突、M 使用 Ce/Tb/O/F、缺失/重复/非正整数价态，以及非法预算都会明确报错。schema 1 固定 Ce/Tb 为 `[3,4]`、O/F 为 `-2/-1`；若以后扩展这些模型，应提升 schema，而不是静默改变含义。
