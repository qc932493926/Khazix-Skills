"""
review_conflicts.py - 交互式处理矛盾经验

功能：
1. 检测语义相似或矛盾的经验
2. 生成冲突报告
3. 支持合并、保留、删除等操作
"""

import os
import sys
import json
import datetime
import re
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher


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


def normalize_text(text: str) -> str:
    """文本标准化：小写、去标点、去多余空格"""
    text = text.lower()
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)  # 保留中文
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def compute_similarity(text1: str, text2: str) -> float:
    """计算两段文本的相似度"""
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    return SequenceMatcher(None, norm1, norm2).ratio()


def extract_keywords(text: str) -> set:
    """提取关键词"""
    # 简单实现：提取所有词
    norm = normalize_text(text)
    words = set(norm.split())
    # 过滤短词
    return {w for w in words if len(w) > 1}


def detect_contradiction_signals(text1: str, text2: str) -> List[str]:
    """检测矛盾信号"""
    signals = []

    # 否定词对
    negation_pairs = [
        ("不要", "要"), ("禁止", "允许"), ("关闭", "开启"),
        ("disable", "enable"), ("don't", "do"), ("never", "always"),
        ("静音", "有声"), ("mute", "unmute"), ("off", "on"),
        ("false", "true"), ("no", "yes")
    ]

    t1_lower = text1.lower()
    t2_lower = text2.lower()

    for neg, pos in negation_pairs:
        if (neg in t1_lower and pos in t2_lower) or (pos in t1_lower and neg in t2_lower):
            signals.append(f"Negation pair detected: {neg}/{pos}")

    # 数值矛盾（如 "1080p" vs "720p"）
    nums1 = set(re.findall(r'\d+', text1))
    nums2 = set(re.findall(r'\d+', text2))
    common_context_nums = nums1 & nums2
    diff_nums = (nums1 | nums2) - common_context_nums

    if diff_nums and compute_similarity(text1, text2) > 0.5:
        signals.append(f"Different values in similar context: {diff_nums}")

    return signals


def find_conflicts(entries: List[Dict], similarity_threshold: float = 0.7) -> List[Dict]:
    """
    检测所有潜在冲突

    Returns:
        冲突列表，每项包含两条经验和冲突类型
    """
    conflicts = []
    n = len(entries)

    for i in range(n):
        for j in range(i + 1, n):
            e1, e2 = entries[i], entries[j]
            content1 = e1.get("content", "")
            content2 = e2.get("content", "")

            # 跳过已归档的
            if e1.get("validation", {}).get("status") == "archived":
                continue
            if e2.get("validation", {}).get("status") == "archived":
                continue

            similarity = compute_similarity(content1, content2)
            contradiction_signals = detect_contradiction_signals(content1, content2)

            conflict = None

            # 高相似度 - 可能重复
            if similarity > 0.9:
                conflict = {
                    "type": "duplicate",
                    "confidence": similarity,
                    "entry1": e1,
                    "entry2": e2,
                    "reason": f"High similarity: {similarity:.2%}"
                }
            # 中等相似度 + 矛盾信号 - 可能矛盾
            elif similarity > 0.4 and contradiction_signals:
                conflict = {
                    "type": "contradiction",
                    "confidence": similarity,
                    "entry1": e1,
                    "entry2": e2,
                    "reason": "; ".join(contradiction_signals)
                }
            # 相同类型但有矛盾信号
            elif e1.get("type") == e2.get("type") and contradiction_signals:
                # 检查关键词重叠
                kw1 = extract_keywords(content1)
                kw2 = extract_keywords(content2)
                overlap = len(kw1 & kw2) / max(len(kw1 | kw2), 1)

                if overlap > 0.3:
                    conflict = {
                        "type": "potential_contradiction",
                        "confidence": overlap,
                        "entry1": e1,
                        "entry2": e2,
                        "reason": f"Same type with contradiction signals: {'; '.join(contradiction_signals)}"
                    }

            if conflict:
                conflicts.append(conflict)

    # 按置信度排序
    conflicts.sort(key=lambda x: x["confidence"], reverse=True)
    return conflicts


def generate_conflict_report(skill_dir: str) -> Dict:
    """生成冲突报告"""
    data = load_evolution_data(skill_dir)
    entries = data.get("entries", [])

    conflicts = find_conflicts(entries)

    report = {
        "skill_dir": skill_dir,
        "skill_name": os.path.basename(skill_dir),
        "total_entries": len(entries),
        "total_conflicts": len(conflicts),
        "duplicates": [c for c in conflicts if c["type"] == "duplicate"],
        "contradictions": [c for c in conflicts if c["type"] == "contradiction"],
        "potential": [c for c in conflicts if c["type"] == "potential_contradiction"],
        "conflicts": conflicts
    }

    return report


def resolve_conflict(
    skill_dir: str,
    entry_id1: str,
    entry_id2: str,
    action: str,
    merged_content: str = None
) -> bool:
    """
    解决冲突

    Args:
        skill_dir: skill 目录
        entry_id1: 第一条经验 ID
        entry_id2: 第二条经验 ID
        action: 操作类型
            - "keep_first": 保留第一条，归档第二条
            - "keep_second": 保留第二条，归档第一条
            - "keep_both": 保留两条（标记为已审核）
            - "merge": 合并为新条目，归档原两条
            - "archive_both": 归档两条
        merged_content: 合并后的内容（仅 action="merge" 时需要）
    """
    data = load_evolution_data(skill_dir)
    entries = data.get("entries", [])

    entry1 = None
    entry2 = None

    for e in entries:
        if e.get("id") == entry_id1:
            entry1 = e
        elif e.get("id") == entry_id2:
            entry2 = e

    if not entry1 or not entry2:
        print(f"Entry not found: {entry_id1} or {entry_id2}", file=sys.stderr)
        return False

    now = datetime.datetime.now().isoformat()

    if action == "keep_first":
        entry2["validation"]["status"] = "archived"
        entry2["validation"]["archived_at"] = now
        entry2["validation"]["archived_reason"] = f"duplicate_of:{entry_id1}"
        entry1["validation"]["confirmed_count"] = entry1.get("validation", {}).get("confirmed_count", 0) + 1

    elif action == "keep_second":
        entry1["validation"]["status"] = "archived"
        entry1["validation"]["archived_at"] = now
        entry1["validation"]["archived_reason"] = f"duplicate_of:{entry_id2}"
        entry2["validation"]["confirmed_count"] = entry2.get("validation", {}).get("confirmed_count", 0) + 1

    elif action == "keep_both":
        entry1["validation"]["reviewed_at"] = now
        entry2["validation"]["reviewed_at"] = now
        entry1["validation"]["conflict_reviewed_with"] = entry_id2
        entry2["validation"]["conflict_reviewed_with"] = entry_id1

    elif action == "merge":
        if not merged_content:
            print("merged_content required for merge action", file=sys.stderr)
            return False

        # 创建新条目
        new_id = f"exp_{len(entries) + 1:03d}"
        new_entry = {
            "id": new_id,
            "type": entry1.get("type", "merged"),
            "content": merged_content,
            "source": {
                "merged_from": [entry_id1, entry_id2],
                "timestamp": now
            },
            "validation": {
                "status": "verified",
                "confirmed_count": 1,
                "last_confirmed": now
            },
            "tags": list(set(entry1.get("tags", []) + entry2.get("tags", [])))
        }
        entries.append(new_entry)

        # 归档原条目
        entry1["validation"]["status"] = "archived"
        entry1["validation"]["archived_at"] = now
        entry1["validation"]["archived_reason"] = f"merged_into:{new_id}"
        entry2["validation"]["status"] = "archived"
        entry2["validation"]["archived_at"] = now
        entry2["validation"]["archived_reason"] = f"merged_into:{new_id}"

    elif action == "archive_both":
        entry1["validation"]["status"] = "archived"
        entry1["validation"]["archived_at"] = now
        entry1["validation"]["archived_reason"] = "conflict_resolved"
        entry2["validation"]["status"] = "archived"
        entry2["validation"]["archived_at"] = now
        entry2["validation"]["archived_reason"] = "conflict_resolved"

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        return False

    return save_evolution_data(skill_dir, data)


def print_conflict_report(report: Dict):
    """打印冲突报告"""
    print(f"\n{'='*70}")
    print(f"Conflict Report: {report['skill_name']}")
    print(f"{'='*70}")
    print(f"Total Entries: {report['total_entries']}")
    print(f"Total Conflicts: {report['total_conflicts']}")
    print(f"  - Duplicates: {len(report['duplicates'])}")
    print(f"  - Contradictions: {len(report['contradictions'])}")
    print(f"  - Potential: {len(report['potential'])}")

    if not report['conflicts']:
        print("\n✅ No conflicts detected!")
        return

    print(f"\n{'─'*70}")

    for i, conflict in enumerate(report['conflicts'], 1):
        type_icon = {
            "duplicate": "🔄",
            "contradiction": "⚔️",
            "potential_contradiction": "⚠️"
        }.get(conflict["type"], "?")

        e1 = conflict["entry1"]
        e2 = conflict["entry2"]

        print(f"\n{type_icon} Conflict #{i}: {conflict['type'].upper()}")
        print(f"   Confidence: {conflict['confidence']:.2%}")
        print(f"   Reason: {conflict['reason']}")
        print(f"\n   [A] {e1.get('id')}: {e1.get('content')}")
        print(f"   [B] {e2.get('id')}: {e2.get('content')}")
        print(f"\n   Actions: keep_first | keep_second | keep_both | merge | archive_both")
        print(f"{'─'*70}")


def interactive_review(skill_dir: str):
    """交互式审核冲突"""
    report = generate_conflict_report(skill_dir)

    if not report['conflicts']:
        print("✅ No conflicts to review!")
        return

    print_conflict_report(report)

    print("\n" + "="*70)
    print("Interactive Review Mode")
    print("="*70)

    for i, conflict in enumerate(report['conflicts'], 1):
        e1 = conflict["entry1"]
        e2 = conflict["entry2"]

        print(f"\n--- Conflict {i}/{len(report['conflicts'])} ---")
        print(f"[A] {e1.get('id')}: {e1.get('content')}")
        print(f"[B] {e2.get('id')}: {e2.get('content')}")

        while True:
            action = input("\nAction (a=keep A, b=keep B, k=keep both, m=merge, x=archive both, s=skip): ").strip().lower()

            if action == 's':
                break
            elif action == 'a':
                resolve_conflict(skill_dir, e1['id'], e2['id'], "keep_first")
                print("✅ Kept A, archived B")
                break
            elif action == 'b':
                resolve_conflict(skill_dir, e1['id'], e2['id'], "keep_second")
                print("✅ Kept B, archived A")
                break
            elif action == 'k':
                resolve_conflict(skill_dir, e1['id'], e2['id'], "keep_both")
                print("✅ Marked both as reviewed")
                break
            elif action == 'm':
                merged = input("Enter merged content: ").strip()
                if merged:
                    resolve_conflict(skill_dir, e1['id'], e2['id'], "merge", merged)
                    print("✅ Merged into new entry")
                    break
            elif action == 'x':
                resolve_conflict(skill_dir, e1['id'], e2['id'], "archive_both")
                print("✅ Archived both")
                break
            else:
                print("Invalid action. Try again.")

    print("\n✅ Review complete!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python review_conflicts.py <skill_dir>                    # 生成冲突报告")
        print("  python review_conflicts.py <skill_dir> --interactive      # 交互式审核")
        print("  python review_conflicts.py <skill_dir> --resolve <id1> <id2> <action> [merged_content]")
        print("      Actions: keep_first, keep_second, keep_both, merge, archive_both")
        sys.exit(1)

    skill_dir = sys.argv[1]

    if "--interactive" in sys.argv:
        interactive_review(skill_dir)
    elif "--resolve" in sys.argv:
        idx = sys.argv.index("--resolve")
        if idx + 3 < len(sys.argv):
            id1 = sys.argv[idx + 1]
            id2 = sys.argv[idx + 2]
            action = sys.argv[idx + 3]
            merged = sys.argv[idx + 4] if idx + 4 < len(sys.argv) else None

            if resolve_conflict(skill_dir, id1, id2, action, merged):
                print(f"✅ Conflict resolved: {action}")
            else:
                print("❌ Failed to resolve conflict")
        else:
            print("Missing arguments for --resolve")
    else:
        report = generate_conflict_report(skill_dir)
        print_conflict_report(report)
