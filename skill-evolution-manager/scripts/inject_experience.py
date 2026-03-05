"""
inject_experience.py - 调用 skill 前自动注入相关经验

功能：
1. 读取 skill 的 evolution.json
2. 筛选出 verified 状态的经验
3. 根据上下文标签过滤相关经验
4. 返回格式化的经验提示，供 Agent 注入到 skill 调用中
"""

import os
import sys
import json
from typing import List, Dict, Optional


def load_evolution_data(skill_dir: str) -> Dict:
    """加载 evolution.json 数据"""
    evolution_path = os.path.join(skill_dir, "evolution.json")

    if not os.path.exists(evolution_path):
        return {"entries": []}

    try:
        with open(evolution_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 兼容旧版数据结构
            if "entries" not in data:
                data = migrate_legacy_format(data)
            return data
    except Exception as e:
        print(f"Error loading evolution.json: {e}", file=sys.stderr)
        return {"entries": []}


def migrate_legacy_format(old_data: Dict) -> Dict:
    """将旧版扁平结构迁移到新版结构"""
    entries = []
    entry_id = 1

    for item in old_data.get("preferences", []):
        entries.append({
            "id": f"exp_{entry_id:03d}",
            "type": "preference",
            "content": item,
            "validation": {"status": "verified", "confirmed_count": 1}
        })
        entry_id += 1

    for item in old_data.get("fixes", []):
        entries.append({
            "id": f"exp_{entry_id:03d}",
            "type": "fix",
            "content": item,
            "validation": {"status": "verified", "confirmed_count": 1}
        })
        entry_id += 1

    for item in old_data.get("contexts", []):
        entries.append({
            "id": f"exp_{entry_id:03d}",
            "type": "context",
            "content": item,
            "validation": {"status": "verified", "confirmed_count": 1}
        })
        entry_id += 1

    if old_data.get("custom_prompts"):
        entries.append({
            "id": f"exp_{entry_id:03d}",
            "type": "custom_prompt",
            "content": old_data["custom_prompts"],
            "validation": {"status": "verified", "confirmed_count": 1}
        })

    return {
        "last_updated": old_data.get("last_updated"),
        "entries": entries
    }


def filter_by_status(entries: List[Dict], allowed_statuses: List[str] = None) -> List[Dict]:
    """按状态过滤经验"""
    if allowed_statuses is None:
        allowed_statuses = ["verified", "pending"]

    return [
        e for e in entries
        if e.get("validation", {}).get("status", "pending") in allowed_statuses
    ]


def filter_by_tags(entries: List[Dict], context_tags: List[str]) -> List[Dict]:
    """按标签过滤相关经验"""
    if not context_tags:
        return entries

    context_tags_lower = [t.lower() for t in context_tags]

    def is_relevant(entry: Dict) -> bool:
        entry_tags = [t.lower() for t in entry.get("tags", [])]
        # 无标签的经验默认相关
        if not entry_tags:
            return True
        # 有标签则检查交集
        return bool(set(entry_tags) & set(context_tags_lower))

    return [e for e in entries if is_relevant(e)]


def format_for_injection(entries: List[Dict], format_type: str = "markdown") -> str:
    """格式化经验供注入"""
    if not entries:
        return ""

    if format_type == "json":
        return json.dumps([e["content"] for e in entries], ensure_ascii=False, indent=2)

    # Markdown 格式
    lines = ["## 📌 Active Constraints (Auto-Injected)", ""]

    # 按类型分组
    by_type = {}
    for e in entries:
        t = e.get("type", "other")
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(e)

    type_labels = {
        "preference": "### User Preferences",
        "fix": "### Known Fixes",
        "context": "### Context Constraints",
        "custom_prompt": "### Custom Instructions"
    }

    for t, items in by_type.items():
        label = type_labels.get(t, f"### {t.title()}")
        lines.append(label)
        for item in items:
            content = item["content"]
            status = item.get("validation", {}).get("status", "pending")
            confirmed = item.get("validation", {}).get("confirmed_count", 0)

            # 显示置信度指示
            if status == "verified" and confirmed >= 3:
                indicator = "✅"
            elif status == "verified":
                indicator = "☑️"
            elif status == "stale":
                indicator = "⚠️"
            else:
                indicator = "○"

            lines.append(f"- {indicator} {content}")
        lines.append("")

    return "\n".join(lines)


def get_active_constraints(
    skill_dir: str,
    context_tags: List[str] = None,
    include_pending: bool = False,
    format_type: str = "markdown"
) -> str:
    """
    主入口：获取应该注入的经验约束

    Args:
        skill_dir: skill 目录路径
        context_tags: 上下文标签，用于过滤相关经验
        include_pending: 是否包含待验证的经验
        format_type: 输出格式 (markdown/json)

    Returns:
        格式化的经验字符串
    """
    data = load_evolution_data(skill_dir)
    entries = data.get("entries", [])

    # 状态过滤
    allowed = ["verified"]
    if include_pending:
        allowed.append("pending")
    entries = filter_by_status(entries, allowed)

    # 标签过滤
    if context_tags:
        entries = filter_by_tags(entries, context_tags)

    return format_for_injection(entries, format_type)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inject_experience.py <skill_dir> [--tags tag1,tag2] [--include-pending] [--format json|markdown]")
        sys.exit(1)

    skill_dir = sys.argv[1]
    context_tags = None
    include_pending = False
    format_type = "markdown"

    # 解析参数
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
            context_tags = sys.argv[i + 1].split(",")
            i += 2
        elif sys.argv[i] == "--include-pending":
            include_pending = True
            i += 1
        elif sys.argv[i] == "--format" and i + 1 < len(sys.argv):
            format_type = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    result = get_active_constraints(skill_dir, context_tags, include_pending, format_type)

    if result:
        print(result)
    else:
        print("No active constraints found.", file=sys.stderr)
