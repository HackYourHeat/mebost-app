"""
Soul Dashboard — MEBOST Hải Đăng V1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Route ẩn /admin/soul?key=<ADMIN_KEY>
Hiển thị "sức khỏe tâm hồn" của hệ thống:
  - Emotion distribution (bar chart)
  - Trust / Momentum / Arousal / Pressure theo user
  - Pronoun modes đang dùng
  - Bio state (HRV, breath)
  - Rate limit hits
  - Top active users

ADMIN_KEY: set qua biến môi trường ADMIN_KEY
"""
from __future__ import annotations
import os
from db import get_db, db_mode, utc_now_iso

# ADMIN_KEY bắt buộc từ env var — không có default để tránh security risk
_raw_admin_key = os.environ.get("ADMIN_KEY", "")
ADMIN_KEY = _raw_admin_key if _raw_admin_key else "CHANGE_ME_SET_ADMIN_KEY_ENV_VAR"


def _q(db, sql, params=()):
    try:
        return db.execute(sql, params).fetchall()
    except Exception:
        return []


def build_soul_data() -> dict:
    """Thu thập tất cả metrics cho dashboard."""
    db = get_db()
    try:
        # Emotion distribution — 7 ngày gần nhất
        emotions = _q(db, """
            SELECT emotion, COUNT(*) as cnt
            FROM emotion_logs
            WHERE timestamp >= datetime('now', '-7 days')
            GROUP BY emotion ORDER BY cnt DESC LIMIT 10
        """)

        # Top users — tin nhắn nhiều nhất
        top_users = _q(db, """
            SELECT user_id, COUNT(*) as msg_count,
                   MAX(timestamp) as last_seen
            FROM messages WHERE role='user'
            GROUP BY user_id ORDER BY msg_count DESC LIMIT 20
        """)

        # Internal state snapshot
        internal = _q(db, """
            SELECT user_id, arousal, calm, pressure, trust, depth, updated_at
            FROM user_internal_state
            ORDER BY updated_at DESC LIMIT 20
        """)

        # Bio state
        bio = _q(db, """
            SELECT user_id, heartbeat_rate, breath_phase,
                   conversation_depth, updated_at
            FROM user_bio_state
            ORDER BY updated_at DESC LIMIT 20
        """)

        # Pronoun distribution
        pronouns = _q(db, """
            SELECT pronoun_mode, COUNT(*) as cnt
            FROM user_pronoun_profile
            GROUP BY pronoun_mode ORDER BY cnt DESC
        """)

        # Rate limit hits — 1 giờ gần nhất
        rl_recent = _q(db, """
            SELECT COUNT(*) as cnt FROM rate_limits
            WHERE created_at >= datetime('now', '-1 hour')
        """)
        rl_count = rl_recent[0][0] if rl_recent else 0

        # Memory nodes tổng
        mem_total = _q(db, "SELECT COUNT(*) FROM memory_nodes WHERE deleted_flag=0")
        mem_count = mem_total[0][0] if mem_total else 0

        # Tổng messages hôm nay
        today_msgs = _q(db, """
            SELECT COUNT(*) FROM messages
            WHERE timestamp >= datetime('now', 'start of day')
        """)
        today_count = today_msgs[0][0] if today_msgs else 0

        return {
            "generated_at":  utc_now_iso(),
            "db_mode":       db_mode(),
            "today_messages": today_count,
            "memory_nodes":  mem_count,
            "rate_limit_hits_1h": rl_count,
            "emotions":      [dict(r) if hasattr(r, "keys") else {"emotion": r[0], "cnt": r[1]} for r in emotions],
            "top_users":     [dict(r) if hasattr(r, "keys") else {"user_id": r[0], "msg_count": r[1], "last_seen": r[2]} for r in top_users],
            "internal_state":[dict(r) if hasattr(r, "keys") else {"user_id":r[0],"arousal":r[1],"calm":r[2],"pressure":r[3],"trust":r[4],"depth":r[5],"updated_at":r[6]} for r in internal],
            "bio_state":     [dict(r) if hasattr(r, "keys") else {"user_id":r[0],"heartbeat_rate":r[1],"breath_phase":r[2],"conversation_depth":r[3],"updated_at":r[4]} for r in bio],
            "pronouns":      [dict(r) if hasattr(r, "keys") else {"pronoun_mode": r[0], "cnt": r[1]} for r in pronouns],
        }
    finally:
        db.close()


def render_dashboard_html(data: dict) -> str:
    """Render HTML dashboard với Chart.js."""
    emotion_labels = [e["emotion"] for e in data["emotions"]]
    emotion_counts = [e["cnt"]     for e in data["emotions"]]
    pronoun_labels = [p["pronoun_mode"] for p in data["pronouns"]]
    pronoun_counts = [p["cnt"]          for p in data["pronouns"]]

    # Internal state rows
    state_rows = ""
    for u in data["internal_state"]:
        uid   = u.get("user_id","?")[:12]
        trust = float(u.get("trust",0))
        calm  = float(u.get("calm",0))
        pres  = float(u.get("pressure",0))
        aro   = float(u.get("arousal",0))
        depth = float(u.get("depth",0))
        upd   = str(u.get("updated_at",""))[:16]

        def bar(val, color):
            pct = int(val * 100)
            return f'<div style="background:{color};width:{pct}%;height:10px;border-radius:4px"></div>'

        state_rows += f"""
        <tr>
          <td style="font-size:11px;color:#94a3b8">{uid}</td>
          <td>{bar(trust,"#22d3ee")}</td>
          <td>{bar(calm,"#4ade80")}</td>
          <td>{bar(pres,"#f87171")}</td>
          <td>{bar(aro,"#fb923c")}</td>
          <td>{bar(depth,"#a78bfa")}</td>
          <td style="font-size:10px;color:#64748b">{upd}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hải Đăng — Soul Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0a0f1e;color:#e2e8f0;font-family:'Segoe UI',sans-serif;padding:24px}}
  h1{{font-size:22px;color:#7dd3fc;margin-bottom:4px}}
  .sub{{font-size:12px;color:#64748b;margin-bottom:24px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-bottom:24px}}
  .card{{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:16px}}
  .card h2{{font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px}}
  .stat{{font-size:36px;font-weight:700;color:#38bdf8}}
  .stat-label{{font-size:12px;color:#475569;margin-top:4px}}
  .chart-wrap{{position:relative;height:200px}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  th{{color:#475569;text-align:left;padding:4px 8px;border-bottom:1px solid #1e293b}}
  td{{padding:4px 8px;border-bottom:1px solid #1e293b}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;background:#1e293b;color:#94a3b8}}
  .refresh{{float:right;font-size:11px;color:#475569;cursor:pointer;text-decoration:underline}}
</style>
</head>
<body>
<h1>🌊 Hải Đăng — Soul Dashboard</h1>
<div class="sub">Generated: {data["generated_at"]} &nbsp;|&nbsp; DB: {data["db_mode"]} &nbsp;|&nbsp;
  <a class="refresh" onclick="location.reload()">⟳ Refresh</a>
</div>

<div class="grid">
  <div class="card">
    <h2>Tin nhắn hôm nay</h2>
    <div class="stat">{data["today_messages"]}</div>
    <div class="stat-label">messages</div>
  </div>
  <div class="card">
    <h2>Memory nodes</h2>
    <div class="stat">{data["memory_nodes"]}</div>
    <div class="stat-label">ký ức đang hoạt động</div>
  </div>
  <div class="card">
    <h2>Rate limit hits</h2>
    <div class="stat" style="color:{'#f87171' if data['rate_limit_hits_1h']>5 else '#4ade80'}">{data["rate_limit_hits_1h"]}</div>
    <div class="stat-label">trong 1 giờ qua</div>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>Cảm xúc — 7 ngày (Chart)</h2>
    <div class="chart-wrap">
      <canvas id="emoChart"></canvas>
    </div>
  </div>
  <div class="card">
    <h2>Pronoun modes</h2>
    <div class="chart-wrap">
      <canvas id="pronChart"></canvas>
    </div>
  </div>
</div>

<div class="card" style="margin-bottom:16px">
  <h2>Internal State — 20 users gần nhất</h2>
  <table>
    <thead><tr>
      <th>User</th>
      <th style="color:#22d3ee">Trust</th>
      <th style="color:#4ade80">Calm</th>
      <th style="color:#f87171">Pressure</th>
      <th style="color:#fb923c">Arousal</th>
      <th style="color:#a78bfa">Depth</th>
      <th>Updated</th>
    </tr></thead>
    <tbody>{state_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>Top active users</h2>
  <table>
    <thead><tr><th>User ID</th><th>Messages</th><th>Last seen</th></tr></thead>
    <tbody>
      {"".join(f'<tr><td style="color:#94a3b8">{u.get("user_id","?")[:20]}</td><td>{u.get("msg_count",0)}</td><td style="font-size:11px;color:#64748b">{str(u.get("last_seen",""))[:16]}</td></tr>' for u in data["top_users"])}
    </tbody>
  </table>
</div>

<script>
const emo = new Chart(document.getElementById("emoChart"), {{
  type:"bar",
  data:{{
    labels:{emotion_labels},
    datasets:[{{
      data:{emotion_counts},
      backgroundColor:["#38bdf8","#7dd3fc","#93c5fd","#6ee7b7","#fde68a","#fca5a5","#c4b5fd","#f9a8d4","#86efac","#fb923c"],
      borderRadius:4
    }}]
  }},
  options:{{plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:"#94a3b8",font:{{size:10}}}},grid:{{display:false}}}},y:{{ticks:{{color:"#94a3b8"}},grid:{{color:"#1e293b"}}}}}}}}
}});
const pro = new Chart(document.getElementById("pronChart"), {{
  type:"doughnut",
  data:{{
    labels:{pronoun_labels},
    datasets:[{{
      data:{pronoun_counts},
      backgroundColor:["#38bdf8","#4ade80","#f87171","#fb923c","#a78bfa","#f472b6","#34d399","#fbbf24","#60a5fa","#e879f9"],
      borderWidth:0
    }}]
  }},
  options:{{plugins:{{legend:{{labels:{{color:"#94a3b8",font:{{size:10}}}}}}}}}}
}});
</script>
</body></html>"""
