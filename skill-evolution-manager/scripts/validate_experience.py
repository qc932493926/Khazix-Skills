"""
validate_experience.py - skill 更新后检测过时经验

功能：
1. 对比当前 skill 版本与经验记录的版本
2. 标记可能失效的经验为 stale
3. 支持手动确认经验仍然有效
4. 支持增加经验的 confirmed_count
"""

import os
import sys
import json
import datetime
import subprocess
from typing import Dict, Optional, List


def get_skill_hash(skill_dir: str) -> Optional[str]:
    """获取 skill 当前的 github_hash（从 SKILL.md frontmatter）"""
    skill_md_path = os.path.join(skill_dir, "SKILL.md")

    if not os.path.exists(skill_md_path):
        return None

    try:
        with open(skill_md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 frontmatter
        if content.startswith("---"):
            end_idx = content.find("---", 3)
            if end_idx > 0:
                frontmatter = content[3:end_idx]
                for line in frontmatter.split("\n"):
                    if line.strip().startswith("github_hash:"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass

    return None


def get_skill_version(skill_dir: str) -> Optional[str]:
    """获取 skill 当前版本"""
    skill_md_path = os.path.join(skill_dir, "SKILL.md")

    if not os.path.exists(skill_md_path):
        return None

    try:
        with open(skill_md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if content.startswith("---"):
            end_idx = content.find("---", 3)
            if end_idx > 0:
                frontmatter = content[3:end_idx]
                for line in frontmatter.split("\n"):
                    if line.strip().startswith("version:"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass

    return None


def load_evolution_data(skill_dir: str) -> Dict:
    """加载 evolution.json"""
    evolution_path = os.path.join(skill_dir, "evolution.json")

    if not os.path.exists(evolution_path):
        return {"entries": []}

    try:
        with open(evolution_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading evolution.json: {e}", file=sys.stderr)
        return {"entries": []}


def save_evolution_data(skill_dir: str, data: Dict) -> bool:
    """保存 evolution.json"""
    evolution_path = os.path.join(skill_dir, "evolution.json")

    try:
        data["last_updated"] = datetime.datetime.now().isoformat()
        with open(evolution_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving evolution.json: {e}", file=sys.stderr)
        return False


def validate_experiences(skill_dir: str, auto_stale: bool = True) -> Dict:
    """
    验证所有经验的有效性

    Args:
        skill_dir: skill 目录
        auto_stale: 是否自动将版本不匹配的经验标记为 stale

    Returns:
        验证报告
    """
    current_hash = get_skill_hash(skill_dir)
    current_version = get_skill_version(skill_dir)
    data = load_evolution_data(skill_dir)
    entries = data.get("entries", [])

    report = {
        "skill_dir": skill_dir,
        "current_hash": current_hash,
        "current_version": current_version,
        "total": len(entries),
        "verified": 0,
        "stale": 0,
        "pending": 0,
        "newly_stale": [],
        "details": []
    }

    modified = False

    for entry in entries:
        entry_id = entry.get("id", "unknown")
        source = entry.get("source", {})
        validation = entry.get("validation", {"status": "pending", "confirmed_count": 0})

        # 确保 validation 字段存在
        if "validation" not in entry:
            entry["validation"] = validation
            modified = True

        old_status = validation.get("status", "pending")
        source_hash = source.get("skill_hash")

        # 检查版本是否匹配
        hash_mismatch = source_hash and current_hash and source_hash != current_hash

        detail = {
            "id": entry_id,
            "type": entry.get("type"),
            "content": entry.get("content", "")[:50] + "...",
            "status": old_status,
            "source_hash": source_hash,
            "hash_match": not hash_mismatch
        }

        # 自动标记为 stale
        if auto_stale and hash_mismatch and old_status == "verified":
            entry["validation"]["status"] = "stale"
            entry["validation"]["stale_reason"] = "skill_version_updated"
            entry["validation"]["stale_at"] = datetime.datetime.now().isoformat()
            report["newly_stale"].append(entry_id)
            detail["status"] = "stale"
            detail["newly_stale"] = True
            modified = True

        # 统计
        status = entry["validation"].get("status", "pending")
        if status == "verified":
            report["verified"] += 1
        elif status == "stale":
            report["stale"] += 1
        else:
            report["pending"] += 1

        report["details"].append(detail)

    # 保存修改
    if modified:
        save_evolution_data(skill_dir, data)

    return report


def confirm_experience(skill_dir: str, entry_id: str, is_valid: bool = True) -> bool:
    """
    确认某条经验是否仍然有效

    Args:
        skill_dir: skill 目录
        entry_id: 经验 ID
        is_valid: True=仍有效(重新验证), False=已失效(归档)
    """
    data = load_evolution_data(skill_dir)
    current_hash = get_skill_hash(skill_dir)

    for entry in data.get("entries", []):
        if entry.get("id") == entry_id:
            if is_valid:
                # 重新验证，更新为当前版本
                entry["validation"]["status"] = "verified"
                entry["validation"]["confirmed_count"] = entry["validation"].get("confirmed_count", 0) + 1
                entry["validation"]["last_confirmed"] = datetime.datetime.now().isoformat()
                if current_hash:
                    entry["source"]["skill_hash"] = current_hash
                # 清除 stale 标记
                entry["validation"].pop("stale_reason", None)
                entry["validation"].pop("stale_at", None)
            else:
                # 归档
                entry["validation"]["status"] = "archived"
                entry["validation"]["archived_at"] = datetime.datetime.now().isoformat()

            save_evolution_data(skill_dir, data)
            return True

    print(f"Experience {entry_id} not found", file=sys.stderr)
    return False


def batch_confirm(skill_dir: str, entry_ids: List[str], is_valid: bool = True) -> int:
    """批量确认经验"""
    count = 0
    for entry_id in entry_ids:
        if confirm_experience(skill_dir, entry_id, is_valid):
            count += 1
    return count


def print_report(report: Dict):
    """打印验证报告"""
    print(f"\n{'='*60}")
    print(f"Skill: {os.path.basename(report['skill_dir'])}")
    print(f"Current Hash: {report['current_hash'] or 'N/A'}")
    print(f"Current Version: {report['current_version'] or 'N/A'}")
    print(f"{'='*60}")
    print(f"Total: {report['total']} | Verified: {report['verified']} | Stale: {report['stale']} | Pending: {report['pending']}")

    if report["newly_stale"]:
        print(f"\n⚠️  Newly marked as stale: {len(report['newly_stale'])}")
        for entry_id in report["newly_stale"]:
            print(f"   - {entry_id}")

    print(f"\nDetails:")
    for d in report["details"]:
        status_icon = {
            "verified": "✅",
            "stale": "⚠️",
            "pending": "○",
            "archived": "📦"
        }.get(d["status"], "?")

        hash_icon = "🔗" if d["hash_match"] else "⛓️‍💥"
        print(f"  {status_icon} [{d['id']}] {d['type']}: {d['content']} {hash_icon}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python validate_experience.py <skill_dir>                    # 验证所有经验")
        print("  python validate_experience.py <skill_dir> --confirm <id>     # 确认经验仍有效")
        print("  python validate_experience.py <skill_dir> --archive <id>     # 归档失效经验")
        print("  python validate_experience.py <skill_dir> --no-auto-stale    # 不自动标记 stale")
        sys.exit(1)

    skill_dir = sys.argv[1]

    if "--confirm" in sys.argv:
        idx = sys.argv.index("--confirm")
        if idx + 1 < len(sys.argv):
            entry_id = sys.argv[idx + 1]
            if confirm_experience(skill_dir, entry_id, True):
                print(f"✅ Experience {entry_id} confirmed as valid")
            else:
                print(f"❌ Failed to confirm {entry_id}")
    elif "--archive" in sys.argv:
        idx = sys.argv.index("--archive")
        if idx + 1 < len(sys.argv):
            entry_id = sys.argv[idx + 1]
            if confirm_experience(skill_dir, entry_id, False):
                print(f"📦 Experience {entry_id} archived")
            else:
                print(f"❌ Failed to archive {entry_id}")
    else:
        auto_stale = "--no-auto-stale" not in sys.argv
        report = validate_experiences(skill_dir, auto_stale)
        print_report(report)
