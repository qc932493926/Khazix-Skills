---
name: Skill Evolution Manager
description: 专门用于在对话结束时，根据用户反馈和对话内容总结优化并迭代现有 Skills 的核心工具。它通过吸取对话中的”精华”（如成功的解决方案、失败的教训、特定的代码规范）来持续演进 Skills 库。
license: MIT
---

# Skill Evolution Manager

这是整个 AI 技能系统的”进化中枢”。它不仅负责优化单个 Skill，还负责跨 Skill 的经验复盘和沉淀。

## 核心职责

1.  **复盘诊断 (Session Review)**：在对话结束时，分析所有被调用的 Skill 的表现。
2.  **经验提取 (Experience Extraction)**：将非结构化的用户反馈转化为结构化的 JSON 数据（`evolution.json`）。
3.  **智能缝合 (Smart Stitching)**：将沉淀的经验自动写入 `SKILL.md`，确保持久化且不被版本更新覆盖。
4.  **经验注入 (Experience Injection)**：调用 Skill 前自动注入相关的已验证经验。
5.  **版本验证 (Version Validation)**：Skill 更新后检测并标记可能失效的经验。
6.  **冲突检测 (Conflict Detection)**：识别语义重复或矛盾的经验并协助解决。

## 使用场景

**Trigger**:
- `/evolve` - 复盘当前对话
- “复盘一下刚才的对话”
- “我觉得刚才那个工具不太好用，记录一下”
- “把这个经验保存到 Skill 里”
- “检查一下哪些经验过期了”
- “清理重复的经验”

## 数据模型 (Evolution Data Schema)

### 新版结构化数据模型

每条经验都是一个完整的条目，包含溯源和验证信息：

```json
{
  “last_updated”: “2026-03-05T10:30:45”,
  “entries”: [
    {
      “id”: “exp_001”,
      “type”: “fix”,
      “content”: “Windows 下 ffmpeg 路径需要用双引号包裹”,
      “source”: {
        “conversation_id”: “conv_abc123”,
        “timestamp”: “2026-03-05T10:30:45”,
        “skill_version”: “0.2.1”,
        “skill_hash”: “a1b2c3d4”
      },
      “validation”: {
        “status”: “verified”,
        “confirmed_count”: 3,
        “last_confirmed”: “2026-03-10T08:00:00”
      },
      “tags”: [“windows”, “path”, “ffmpeg”]
    }
  ]
}
```

### 经验类型 (type)

| 类型 | 说明 |
|------|------|
| `preference` | 用户偏好（如”默认静音”） |
| `fix` | 已知修复/变通方案 |
| `context` | 上下文约束（如”仅限 Windows”） |
| `custom_prompt` | 自定义指令注入 |

### 经验状态 (validation.status)

```
┌─────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐
│ pending │ ─▶ │ verified │ ─▶ │  stale  │ ─▶ │ archived │
└─────────┘    └──────────┘    └─────────┘    └──────────┘
   新增经验      多次验证确认    skill升级后       归档
                               可能失效
```

### 兼容旧版数据

系统自动兼容旧版扁平结构，首次读取时会自动迁移：

```json
// 旧版（仍支持）
{
  “preferences”: [“...”],
  “fixes”: [“...”],
  “custom_prompts”: “...”
}
```

## 工作流 (The Evolution Workflow)

### 阶段一：经验复盘 (Review & Extract)

当用户触发复盘时，Agent 必须执行：

1.  **扫描上下文**：找出用户不满意的点（报错、风格不对、参数错误）或满意的点。
2.  **定位 Skill**：确定是哪个 Skill 需要进化（例如 `yt-dlp` 或 `baoyu-comic`）。
3.  **生成结构化 JSON**：

```json
{
  “entries”: [
    {
      “type”: “fix”,
      “content”: “Windows 下 ffmpeg 路径需转义”,
      “tags”: [“windows”, “ffmpeg”]
    }
  ]
}
```

### 阶段二：经验持久化 (Persist)

Agent 调用 `scripts/merge_evolution.py`：

```bash
python scripts/merge_evolution.py <skill_path> '<json_string>'
```

### 阶段三：文档缝合 (Stitch)

Agent 调用 `scripts/smart_stitch.py`：

```bash
python scripts/smart_stitch.py <skill_path>
```

### 阶段四：调用前注入 (Pre-Invoke Injection)

在调用目标 Skill 前，Agent 应先获取相关经验：

```bash
python scripts/inject_experience.py <skill_path> --tags windows,download
```

输出示例：
```markdown
## 📌 Active Constraints (Auto-Injected)

### Known Fixes
- ✅ Windows 下 ffmpeg 路径需要用双引号包裹

### User Preferences
- ☑️ 默认下载 1080p 分辨率
```

Agent 将这些约束注入到 Skill 调用的上下文中。

### 阶段五：版本更新后验证 (Post-Update Validation)

当 `skill-manager` 更新了某个 Skill 后：

```bash
python scripts/validate_experience.py <skill_path>
```

输出示例：
```
============================================================
Skill: yt-dlp
Current Hash: b5c6d7e8
============================================================
Total: 5 | Verified: 3 | Stale: 2 | Pending: 0

⚠️  Newly marked as stale: 2
   - exp_002
   - exp_004
```

### 阶段六：冲突检测与解决 (Conflict Resolution)

定期或在经验累积后运行：

```bash
# 生成冲突报告
python scripts/review_conflicts.py <skill_path>

# 交互式审核
python scripts/review_conflicts.py <skill_path> --interactive

# 程序化解决
python scripts/review_conflicts.py <skill_path> --resolve exp_001 exp_002 keep_first
```

## 核心脚本

### 基础脚本

| 脚本 | 功能 | 命令 |
|------|------|------|
| `merge_evolution.py` | 增量合并经验 | `python merge_evolution.py <skill_dir> '<json>'` |
| `smart_stitch.py` | 缝合到 SKILL.md | `python smart_stitch.py <skill_dir>` |
| `align_all.py` | 全量重新缝合 | `python align_all.py [skills_root]` |

### 增强脚本

| 脚本 | 功能 | 命令 |
|------|------|------|
| `inject_experience.py` | 获取待注入的经验 | `python inject_experience.py <skill_dir> [--tags ...]` |
| `validate_experience.py` | 验证经验有效性 | `python validate_experience.py <skill_dir>` |
| `review_conflicts.py` | 检测和解决冲突 | `python review_conflicts.py <skill_dir>` |

### inject_experience.py 详细用法

```bash
# 基础用法：获取所有已验证经验
python inject_experience.py <skill_dir>

# 按标签过滤
python inject_experience.py <skill_dir> --tags windows,download

# 包含待验证经验
python inject_experience.py <skill_dir> --include-pending

# JSON 格式输出
python inject_experience.py <skill_dir> --format json
```

### validate_experience.py 详细用法

```bash
# 验证所有经验（自动标记 stale）
python validate_experience.py <skill_dir>

# 不自动标记 stale
python validate_experience.py <skill_dir> --no-auto-stale

# 手动确认某条经验仍有效
python validate_experience.py <skill_dir> --confirm exp_001

# 归档失效经验
python validate_experience.py <skill_dir> --archive exp_002
```

### review_conflicts.py 详细用法

```bash
# 生成冲突报告
python review_conflicts.py <skill_dir>

# 交互式审核
python review_conflicts.py <skill_dir> --interactive

# 程序化解决冲突
python review_conflicts.py <skill_dir> --resolve <id1> <id2> <action> [merged_content]
# action: keep_first | keep_second | keep_both | merge | archive_both
```

## 完整工作流图

```
                        ┌────────────────────────────────────┐
                        │           对话进行中                │
                        └────────────────────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
        ▼                               ▼                               ▼
┌───────────────┐               ┌───────────────┐               ┌───────────────┐
│ 1. 调用前注入  │               │ 2. 执行 Skill  │               │ 3. 用户反馈   │
│ inject_exp.py │               │               │               │               │
└───────────────┘               └───────────────┘               └───────────────┘
        │                               │                               │
        │                               │                               │
        │                               ▼                               │
        │                       ┌───────────────┐                       │
        └──────────────────────▶│ 4. 复盘诊断   │◀──────────────────────┘
                                │ /evolve      │
                                └───────────────┘
                                        │
                                        ▼
                                ┌───────────────┐
                                │ 5. 经验提取   │
                                │ 生成 JSON     │
                                └───────────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        │                               │
                        ▼                               ▼
                ┌───────────────┐               ┌───────────────┐
                │ 6. 持久化     │               │ 7. 冲突检测   │
                │ merge_evo.py │               │ review_conf.py│
                └───────────────┘               └───────────────┘
                        │                               │
                        └───────────────┬───────────────┘
                                        │
                                        ▼
                                ┌───────────────┐
                                │ 8. 文档缝合   │
                                │ smart_stitch  │
                                └───────────────┘
                                        │
                                        ▼
                        ┌────────────────────────────────────┐
                        │       skill-manager 更新 Skill      │
                        └────────────────────────────────────┘
                                        │
                                        ▼
                                ┌───────────────┐
                                │ 9. 版本验证   │
                                │ validate_exp  │
                                └───────────────┘
                                        │
                                        ▼
                                ┌───────────────┐
                                │ 10. 重新缝合  │
                                │ align_all.py  │
                                └───────────────┘
```

## 最佳实践

- **不要直接修改 SKILL.md 的正文**：所有经验通过 `evolution.json` 通道进行。
- **多 Skill 协同**：一次对话涉及多个 Skill 时，依次为每个 Skill 执行流程。
- **定期清理**：运行 `review_conflicts.py` 清理重复和矛盾经验。
- **版本更新后验证**：每次 `skill-manager` 更新后运行 `validate_experience.py`。
- **注入经验时按需过滤**：使用 `--tags` 参数只注入相关经验，避免噪音。
