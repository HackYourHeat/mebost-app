# --------------------------------------------------
# Life Graph Engine — MEBOST Hải Đăng V1.1
# --------------------------------------------------
# Biến AI từ chatbot thành life-aware companion.
# Thay vì nhớ từng câu, hệ thống hiểu:
# topics · goals · fears · relationships · projects
# và kết nối chúng thành đồ thị cuộc đời.
# --------------------------------------------------

from __future__ import annotations

import re
from db import get_db, utc_now_iso

# --------------------------------------------------
# Node taxonomy
# --------------------------------------------------

_NODE_TYPES = {
    "goal", "project", "relationship", "emotion_pattern",
    "life_event", "belief", "fear", "value", "identity",
}

# Keyword → (node_type, label_template)
_NODE_SIGNALS: list[tuple[list[str], str]] = [
    (["dự án", "project", "app", "website", "build", "xây", "làm"],      "project"),
    (["mục tiêu", "goal", "ước mơ", "dream", "muốn đạt", "target"],      "goal"),
    (["sợ", "fear", "afraid", "lo sợ", "ám ảnh", "nightmare"],           "fear"),
    (["tin rằng", "believe", "tôi nghĩ", "i think", "giá trị", "value"], "belief"),
    (["bạn bè", "friend", "gia đình", "family", "người yêu", "partner",
      "đồng nghiệp", "colleague"],                                        "relationship"),
    (["sự kiện", "event", "hôm đó", "that day", "khi tôi", "when i"],    "life_event"),
    (["tôi là", "i am", "mình là", "bản thân", "identity", "persona"],   "identity"),
    (["luôn luôn", "always feel", "thường cảm", "pattern", "mỗi khi",
      "every time"],                                                        "emotion_pattern"),
    (["quan trọng với", "matters to", "giá trị nhất", "most important",
      "tôi trân trọng"],                                                   "value"),
]

# Thread detection: keyword → thread_id
_THREAD_SIGNALS: dict[str, list[str]] = {
    "career":           ["công việc", "nghề", "career", "job", "sự nghiệp", "làm việc"],
    "creative_projects":["dự án", "project", "app", "build", "sáng tạo", "create"],
    "relationships":    ["bạn bè", "gia đình", "friend", "family", "người yêu", "relationship"],
    "self_identity":    ["bản thân", "mình là", "i am", "identity", "tôi nghĩ về mình"],
    "emotional_health": ["cảm xúc", "emotion", "cảm thấy", "feel", "tâm trạng", "mental"],
    "fears_and_beliefs":["sợ", "fear", "tin rằng", "believe", "ám ảnh"],
    "goals_and_dreams": ["mục tiêu", "goal", "ước mơ", "dream", "tương lai", "future"],
}

# Relation inference: (type_a, type_b) → relation
_EDGE_RULES: list[tuple[str, str, str, float]] = [
    ("fear",          "goal",           "conflicts_with", 0.7),
    ("emotion_pattern","goal",          "conflicts_with", 0.5),
    ("belief",        "goal",           "drives",         0.8),
    ("value",         "goal",           "supports",       0.8),
    ("project",       "goal",           "supports",       0.7),
    ("fear",          "emotion_pattern","causes",         0.6),
    ("life_event",    "emotion_pattern","causes",         0.7),
    ("life_event",    "belief",         "causes",         0.6),
    ("relationship",  "emotion_pattern","connected_to",   0.5),
    ("identity",      "belief",         "expresses",      0.7),
    ("identity",      "value",          "expresses",      0.7),
]


# --------------------------------------------------
# Layer 1 — Node detection
# --------------------------------------------------

def detect_life_nodes(message: str) -> list[dict]:
    """
    Extract candidate life nodes từ message.
    Dùng keyword heuristic — không gọi LLM.

    Returns:
        list of {node_type, label, importance, raw_signal}
    """
    low   = message.lower()
    found = []

    for keywords, node_type in _NODE_SIGNALS:
        for kw in keywords:
            if kw in low:
                # Extract label: lấy đoạn xung quanh keyword
                label = _extract_label(message, kw)
                if label:
                    found.append({
                        "node_type":   node_type,
                        "label":       label,
                        "importance":  _default_importance(node_type),
                        "raw_signal":  kw,
                    })
                break  # một keyword đủ để detect type này

    # Deduplicate by (node_type, label)
    seen: set[tuple] = set()
    unique = []
    for n in found:
        key = (n["node_type"], n["label"][:40].lower())
        if key not in seen:
            seen.add(key)
            unique.append(n)

    return unique


def _extract_label(text: str, keyword: str) -> str:
    """Lấy cụm từ xung quanh keyword làm label (tối đa 6 từ)."""
    low = text.lower()
    idx = low.find(keyword)
    if idx == -1:
        return ""
    # Lấy 6 từ bắt đầu từ keyword
    snippet = text[idx: idx + 60]
    words   = snippet.split()[:6]
    label   = " ".join(words).strip(".,!?…;:")
    return label[:80] if label else ""


def _default_importance(node_type: str) -> int:
    return {
        "fear":           8,
        "goal":           8,
        "belief":         7,
        "value":          7,
        "project":        7,
        "life_event":     7,
        "relationship":   6,
        "emotion_pattern":6,
        "identity":       6,
    }.get(node_type, 5)


# --------------------------------------------------
# Layer 2 — Graph persistence
# --------------------------------------------------

def update_life_graph(user_id: str, nodes: list[dict]) -> list[str]:
    """
    Insert hoặc update life nodes trong DB.

    Returns:
        list of node_ids đã upsert
    """
    if not nodes:
        return []

    db      = get_db()
    now     = utc_now_iso()
    node_ids = []

    try:
        for n in nodes:
            # node_id = user + type + label hash
            node_id = _make_node_id(user_id, n["node_type"], n["label"])

            existing = db.execute(
                "SELECT node_id, importance FROM life_nodes WHERE node_id = ?",
                (node_id,),
            ).fetchone()

            if existing:
                # Bump importance nếu nhắc lại
                new_importance = min(10, existing["importance"] + 1)
                db.execute(
                    "UPDATE life_nodes SET importance = ?, updated_at = ? WHERE node_id = ?",
                    (new_importance, now, node_id),
                )
            else:
                db.execute(
                    """INSERT INTO life_nodes
                       (node_id, user_id, node_type, label, importance, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (node_id, user_id, n["node_type"], n["label"],
                     n.get("importance", 5), now, now),
                )

            node_ids.append(node_id)

        db.commit()
    finally:
        db.close()

    return node_ids


def _make_node_id(user_id: str, node_type: str, label: str) -> str:
    """Tạo stable node_id từ user + type + label."""
    slug = re.sub(r"\W+", "_", label.lower().strip())[:30]
    return f"{user_id[:8]}_{node_type}_{slug}"


# --------------------------------------------------
# Layer 3 — Edge connection
# --------------------------------------------------

def connect_life_nodes(user_id: str, node_ids: list[str]) -> None:
    """
    Tạo edges giữa các node mới theo _EDGE_RULES.
    Chỉ tạo edge nếu cả source và target đều tồn tại.
    """
    if len(node_ids) < 2:
        return

    db  = get_db()
    now = utc_now_iso()

    try:
        # Load node types
        placeholders = ",".join("?" * len(node_ids))
        rows = db.execute(
            f"SELECT node_id, node_type FROM life_nodes WHERE node_id IN ({placeholders})",
            node_ids,
        ).fetchall()
        type_map = {r["node_id"]: r["node_type"] for r in rows}

        for i, src_id in enumerate(node_ids):
            for tgt_id in node_ids[i + 1:]:
                src_type = type_map.get(src_id)
                tgt_type = type_map.get(tgt_id)
                if not src_type or not tgt_type:
                    continue

                relation, weight = _infer_relation(src_type, tgt_type)

                # Upsert edge
                existing = db.execute(
                    """SELECT id FROM life_edges
                       WHERE user_id=? AND source_node=? AND target_node=?""",
                    (user_id, src_id, tgt_id),
                ).fetchone()

                if not existing:
                    db.execute(
                        """INSERT INTO life_edges
                           (user_id, source_node, target_node, relation, weight, created_at)
                           VALUES (?,?,?,?,?,?)""",
                        (user_id, src_id, tgt_id, relation, weight, now),
                    )

        db.commit()
    finally:
        db.close()


def _infer_relation(type_a: str, type_b: str) -> tuple[str, float]:
    """Tìm relation phù hợp nhất từ _EDGE_RULES."""
    for ta, tb, relation, weight in _EDGE_RULES:
        if (ta == type_a and tb == type_b) or (ta == type_b and tb == type_a):
            return relation, weight
    return "connected_to", 0.4


# --------------------------------------------------
# Layer 4 — Thread building
# --------------------------------------------------

def build_life_threads(user_id: str) -> None:
    """
    Group nodes thành life threads dựa trên label keyword matching.
    Upsert thread và cập nhật emotional_weight.
    """
    db  = get_db()
    now = utc_now_iso()

    try:
        nodes = db.execute(
            "SELECT node_id, node_type, label, importance FROM life_nodes WHERE user_id = ?",
            (user_id,),
        ).fetchall()

        thread_nodes: dict[str, list[str]] = {t: [] for t in _THREAD_SIGNALS}

        for node in nodes:
            label_low = node["label"].lower()
            for thread_id, keywords in _THREAD_SIGNALS.items():
                if any(kw in label_low for kw in keywords):
                    thread_nodes[thread_id].append(node["node_id"])

        for thread_id, nids in thread_nodes.items():
            if not nids:
                continue

            # emotional_weight = avg importance of member nodes / 10
            weights = db.execute(
                f"SELECT AVG(importance) as avg_imp FROM life_nodes "
                f"WHERE node_id IN ({','.join('?' * len(nids))})",
                nids,
            ).fetchone()
            emotional_weight = round((weights["avg_imp"] or 5) / 10, 3)

            existing = db.execute(
                "SELECT thread_id FROM life_threads WHERE thread_id = ? AND user_id = ?",
                (f"{user_id[:8]}_{thread_id}", user_id),
            ).fetchone()

            full_thread_id = f"{user_id[:8]}_{thread_id}"

            if existing:
                db.execute(
                    """UPDATE life_threads
                       SET emotional_weight=?, last_activity=?, node_count=?
                       WHERE thread_id=? AND user_id=?""",
                    (emotional_weight, now, len(nids), full_thread_id, user_id),
                )
            else:
                db.execute(
                    """INSERT INTO life_threads
                       (thread_id, user_id, name, emotional_weight, last_activity, node_count)
                       VALUES (?,?,?,?,?,?)""",
                    (full_thread_id, user_id, thread_id,
                     emotional_weight, now, len(nids)),
                )

        db.commit()
    finally:
        db.close()


# --------------------------------------------------
# Layer 5 — Summary for prompt injection
# --------------------------------------------------

def get_life_graph_summary(user_id: str) -> dict:
    """
    Tạo graph summary để inject vào prompt.

    Returns:
        {
          "active_threads":      list[str],
          "important_nodes":     list[dict],
          "recent_connections":  list[str],
        }
    """
    db = get_db()
    try:
        # Active threads (sorted by emotional_weight)
        threads = db.execute(
            """SELECT name, emotional_weight FROM life_threads
               WHERE user_id = ? ORDER BY emotional_weight DESC LIMIT 4""",
            (user_id,),
        ).fetchall()
        active_threads = [
            f"{r['name']} ({r['emotional_weight']:.0%})"
            for r in threads
        ]

        # Important nodes
        nodes = db.execute(
            """SELECT node_type, label, importance FROM life_nodes
               WHERE user_id = ? ORDER BY importance DESC LIMIT 6""",
            (user_id,),
        ).fetchall()
        important_nodes = [
            {"type": r["node_type"], "label": r["label"], "importance": r["importance"]}
            for r in nodes
        ]

        # Recent edges (as readable strings)
        edges = db.execute(
            """SELECT le.relation, ln1.label as src_label, ln2.label as tgt_label
               FROM life_edges le
               JOIN life_nodes ln1 ON le.source_node = ln1.node_id
               JOIN life_nodes ln2 ON le.target_node = ln2.node_id
               WHERE le.user_id = ?
               ORDER BY le.id DESC LIMIT 4""",
            (user_id,),
        ).fetchall()
        recent_connections = [
            f"{r['src_label']} --{r['relation']}--> {r['tgt_label']}"
            for r in edges
        ]

    finally:
        db.close()

    return {
        "active_threads":     active_threads,
        "important_nodes":    important_nodes,
        "recent_connections": recent_connections,
    }


# --------------------------------------------------
# Main pipeline entry
# --------------------------------------------------

def process_life_graph(user_id: str, message: str) -> dict:
    """
    Chạy toàn bộ life graph pipeline cho một message.
    Gọi từ /chat sau memory step.

    Returns:
        life_graph_summary dict
    """
    nodes    = detect_life_nodes(message)
    node_ids = update_life_graph(user_id, nodes)
    connect_life_nodes(user_id, node_ids)
    build_life_threads(user_id)
    return get_life_graph_summary(user_id)


# --------------------------------------------------
# Self-test
# --------------------------------------------------

def test_life_graph_engine() -> None:
    """
    Test detect + edge inference mà không cần DB.
    """
    messages = [
        "Mình đang xây dự án Mebost và rất lo về chi phí API.",
        "Mình sợ thất bại vì cả nhóm đang nhìn vào mình.",
        "Gia đình mình quan trọng với mình hơn sự nghiệp.",
    ]

    print("─── Life Graph Engine — Detection Test ───")
    for msg in messages:
        nodes = detect_life_nodes(msg)
        print(f"\nMsg: {msg[:55]}…")
        for n in nodes:
            print(f"  [{n['node_type']:16}] {n['label'][:40]}  (imp={n['importance']})")

    print("\n─── Edge Inference ───")
    pairs = [
        ("fear", "goal"),
        ("belief", "goal"),
        ("project", "emotion_pattern"),
        ("life_event", "belief"),
    ]
    for ta, tb in pairs:
        rel, w = _infer_relation(ta, tb)
        print(f"  ({ta}) --{rel}--> ({tb})  weight={w}")

    print("\n──────────────────────────────────────────")


if __name__ == "__main__":
    test_life_graph_engine()
