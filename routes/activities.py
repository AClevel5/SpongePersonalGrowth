from flask import Blueprint, request, jsonify
from extensions import db
from models import Activity
from routes.auth import login_required, current_user

activities_bp = Blueprint("activities", __name__)


@activities_bp.route("/activities", methods=["GET"])
@login_required
def list_activities():
    user = current_user()
    include_archived = request.args.get("include_archived", "false").lower() == "true"
    q = Activity.query.filter_by(user_id=user.id)
    if not include_archived:
        q = q.filter_by(is_archived=False)
    activities = q.order_by(Activity.sort_order, Activity.id).all()
    return jsonify([a.to_dict() for a in activities])


@activities_bp.route("/activities", methods=["POST"])
@login_required
def create_activity():
    user = current_user()
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400

    try:
        points = int(data.get("points", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Points must be an integer"}), 400

    max_sort = db.session.query(db.func.max(Activity.sort_order)).filter_by(user_id=user.id).scalar() or 0
    activity = Activity(
        user_id=user.id,
        name=name,
        points=points,
        sort_order=max_sort + 1,
    )
    db.session.add(activity)
    db.session.commit()
    return jsonify(activity.to_dict()), 201


@activities_bp.route("/activities/<int:activity_id>", methods=["PUT"])
@login_required
def update_activity(activity_id):
    user = current_user()
    activity = Activity.query.filter_by(id=activity_id, user_id=user.id).first()
    if not activity:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        activity.name = name
    if "points" in data:
        try:
            activity.points = int(data["points"])
        except (TypeError, ValueError):
            return jsonify({"error": "Points must be an integer"}), 400
    if "is_archived" in data:
        activity.is_archived = bool(data["is_archived"])
    if "sort_order" in data:
        try:
            activity.sort_order = int(data["sort_order"])
        except (TypeError, ValueError):
            return jsonify({"error": "sort_order must be an integer"}), 400

    db.session.commit()
    return jsonify(activity.to_dict())


@activities_bp.route("/activities/<int:activity_id>", methods=["DELETE"])
@login_required
def delete_activity(activity_id):
    user = current_user()
    activity = Activity.query.filter_by(id=activity_id, user_id=user.id).first()
    if not activity:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(activity)
    db.session.commit()
    return jsonify({"message": "Deleted"})
