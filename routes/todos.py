from datetime import date, datetime
from flask import Blueprint, request, jsonify
from extensions import db
from models import Todo
from routes.auth import login_required, current_user

todos_bp = Blueprint("todos", __name__)


def _parse_date(s, default=None):
    if not s:
        return default
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _rollover_to(user_id, target_date):
    """Move any incomplete todos with date < target_date up to target_date."""
    Todo.query.filter(
        Todo.user_id == user_id,
        Todo.completed == False,  # noqa: E712 — SQLAlchemy needs the explicit ==
        Todo.date < target_date,
    ).update({Todo.date: target_date}, synchronize_session=False)
    db.session.commit()


@todos_bp.route("/todos", methods=["GET"])
@login_required
def list_todos():
    """List todos for a given date. Rolls over any older incomplete todos to that date first."""
    user = current_user()
    d = _parse_date(request.args.get("date"), default=date.today())
    if d is None:
        return jsonify({"error": "Invalid date (YYYY-MM-DD)"}), 400

    _rollover_to(user.id, d)

    rows = (
        Todo.query
        .filter(Todo.user_id == user.id, Todo.date == d)
        .order_by(Todo.completed, Todo.created_at)
        .all()
    )
    return jsonify([t.to_dict() for t in rows])


@todos_bp.route("/todos", methods=["POST"])
@login_required
def create_todo():
    user = current_user()
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Text required"}), 400
    if len(text) > 500:
        return jsonify({"error": "Text too long (max 500 chars)"}), 400

    d = _parse_date(data.get("date"), default=date.today())
    if d is None:
        return jsonify({"error": "Invalid date (YYYY-MM-DD)"}), 400

    todo = Todo(user_id=user.id, text=text, date=d)
    db.session.add(todo)
    db.session.commit()
    return jsonify(todo.to_dict()), 201


@todos_bp.route("/todos/<int:todo_id>", methods=["PUT"])
@login_required
def update_todo(todo_id):
    user = current_user()
    todo = Todo.query.filter_by(id=todo_id, user_id=user.id).first()
    if not todo:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    if "text" in data:
        text = (data["text"] or "").strip()
        if not text:
            return jsonify({"error": "Text required"}), 400
        todo.text = text
    if "completed" in data:
        new_completed = bool(data["completed"])
        if new_completed and not todo.completed:
            todo.completed_at = datetime.utcnow()
        elif not new_completed and todo.completed:
            todo.completed_at = None
        todo.completed = new_completed

    db.session.commit()
    return jsonify(todo.to_dict())


@todos_bp.route("/todos/<int:todo_id>", methods=["DELETE"])
@login_required
def delete_todo(todo_id):
    user = current_user()
    todo = Todo.query.filter_by(id=todo_id, user_id=user.id).first()
    if not todo:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(todo)
    db.session.commit()
    return jsonify({"message": "Deleted"})
