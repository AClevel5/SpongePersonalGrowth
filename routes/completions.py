from datetime import date, datetime, timedelta
from flask import Blueprint, request, jsonify
from extensions import db
from models import Activity, Completion
from routes.auth import login_required, current_user

completions_bp = Blueprint("completions", __name__)


def _parse_date(s, default=None):
    if not s:
        return default
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _monday_of(d):
    return d - timedelta(days=d.weekday())


@completions_bp.route("/completions", methods=["POST"])
@login_required
def log_completion():
    user = current_user()
    data = request.get_json() or {}
    activity_id = data.get("activity_id")
    if not activity_id:
        return jsonify({"error": "activity_id required"}), 400

    activity = Activity.query.filter_by(id=activity_id, user_id=user.id).first()
    if not activity:
        return jsonify({"error": "Activity not found"}), 404

    d = _parse_date(data.get("date"), default=date.today())
    if d is None:
        return jsonify({"error": "Invalid date (YYYY-MM-DD)"}), 400

    c = Completion(user_id=user.id, activity_id=activity.id, date=d)
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@completions_bp.route("/completions/<int:completion_id>", methods=["DELETE"])
@login_required
def delete_completion(completion_id):
    user = current_user()
    c = Completion.query.filter_by(id=completion_id, user_id=user.id).first()
    if not c:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "Deleted"})


@completions_bp.route("/completions", methods=["GET"])
@login_required
def list_completions():
    """List raw completions in a date range (inclusive)."""
    user = current_user()
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    if start is None or end is None:
        return jsonify({"error": "start and end query params required (YYYY-MM-DD)"}), 400

    rows = (
        Completion.query
        .filter(Completion.user_id == user.id)
        .filter(Completion.date >= start, Completion.date <= end)
        .order_by(Completion.date, Completion.id)
        .all()
    )
    return jsonify([c.to_dict() for c in rows])


@completions_bp.route("/week", methods=["GET"])
@login_required
def week_summary():
    """
    Mon-Sun week summary.
    Query: ?start=YYYY-MM-DD (Monday). Defaults to current week's Monday.
    Returns: {start, end, days:[{date, points, completions:[{id, activity_id, activity_name, points}]}], total}
    """
    user = current_user()
    start = _parse_date(request.args.get("start"), default=_monday_of(date.today()))
    if start is None:
        return jsonify({"error": "Invalid start date"}), 400
    start = _monday_of(start)  # normalize to Monday
    end = start + timedelta(days=6)

    activities = {a.id: a for a in Activity.query.filter_by(user_id=user.id).all()}

    rows = (
        Completion.query
        .filter(Completion.user_id == user.id)
        .filter(Completion.date >= start, Completion.date <= end)
        .order_by(Completion.date, Completion.id)
        .all()
    )

    by_date = {start + timedelta(days=i): [] for i in range(7)}
    for c in rows:
        a = activities.get(c.activity_id)
        if not a:
            continue
        by_date.setdefault(c.date, []).append({
            "id": c.id,
            "activity_id": a.id,
            "activity_name": a.name,
            "points": a.points,
        })

    days = []
    total = 0
    for i in range(7):
        d = start + timedelta(days=i)
        comps = by_date.get(d, [])
        day_points = sum(c["points"] for c in comps)
        total += day_points
        days.append({
            "date": d.isoformat(),
            "points": day_points,
            "completions": comps,
        })

    return jsonify({
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "total": total,
    })
