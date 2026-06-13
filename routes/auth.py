from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, limiter
from models import User, WebAuthnCredential
from config import Config
import json
import base64
from functools import wraps

auth_bp = Blueprint("auth", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per hour")
def register():
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already taken"}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"id": user.id, "username": user.username}), 201


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute; 50 per hour")
def login():
    data = request.get_json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid username or password"}), 401

    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"id": user.id, "username": user.username})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@auth_bp.route("/me", methods=["GET"])
def me():
    user = current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    has_passkey = WebAuthnCredential.query.filter_by(user_id=user.id).first() is not None
    return jsonify({
        "id": user.id,
        "username": user.username,
        "has_passkey": has_passkey,
    })


# ── WebAuthn / Passkey ────────────────────────────────────────────────────────

def _webauthn_available():
    try:
        import webauthn  # noqa: F401
        return True
    except ImportError:
        return False


@auth_bp.route("/webauthn/register-options", methods=["POST"])
def webauthn_register_options():
    if not _webauthn_available():
        return jsonify({"error": "py-webauthn not installed"}), 501

    user = current_user()
    if not user:
        return jsonify({"error": "Must be logged in to register a passkey"}), 401

    import webauthn
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        UserVerificationRequirement,
        ResidentKeyRequirement,
        PublicKeyCredentialDescriptor,
    )

    existing = WebAuthnCredential.query.filter_by(user_id=user.id).all()
    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(c.credential_id + "=="))
        for c in existing
    ]

    options = webauthn.generate_registration_options(
        rp_id=Config.RP_ID,
        rp_name=Config.RP_NAME,
        user_id=str(user.id).encode(),
        user_name=user.username,
        user_display_name=user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED,
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
        exclude_credentials=exclude_credentials,
    )

    session["webauthn_register_challenge"] = base64.b64encode(options.challenge).decode()
    return jsonify(json.loads(webauthn.options_to_json(options)))


@auth_bp.route("/webauthn/register-verify", methods=["POST"])
def webauthn_register_verify():
    if not _webauthn_available():
        return jsonify({"error": "py-webauthn not installed"}), 501

    user = current_user()
    if not user:
        return jsonify({"error": "Must be logged in"}), 401

    challenge_b64 = session.pop("webauthn_register_challenge", None)
    if not challenge_b64:
        return jsonify({"error": "No registration challenge in session"}), 400

    import webauthn

    data = request.get_json()
    try:
        verification = webauthn.verify_registration_response(
            credential=data,
            expected_challenge=base64.b64decode(challenge_b64),
            expected_rp_id=Config.RP_ID,
            expected_origin=Config.ORIGIN,
            require_user_verification=False,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    cred_id_b64 = base64.urlsafe_b64encode(verification.credential_id).rstrip(b"=").decode()
    pub_key_b64 = base64.urlsafe_b64encode(verification.credential_public_key).rstrip(b"=").decode()

    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=cred_id_b64,
        public_key=pub_key_b64,
        sign_count=verification.sign_count,
    )
    db.session.add(cred)
    db.session.commit()
    return jsonify({"message": "Passkey registered"})


@auth_bp.route("/webauthn/login-options", methods=["POST"])
def webauthn_login_options():
    if not _webauthn_available():
        return jsonify({"error": "py-webauthn not installed"}), 501

    import webauthn
    from webauthn.helpers.structs import (
        UserVerificationRequirement,
        PublicKeyCredentialDescriptor,
    )

    data = request.get_json() or {}
    username = data.get("username", "").strip()

    allow_credentials = []
    if username:
        user = User.query.filter_by(username=username).first()
        if user:
            creds = WebAuthnCredential.query.filter_by(user_id=user.id).all()
            allow_credentials = [
                PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(c.credential_id + "=="))
                for c in creds
            ]

    options = webauthn.generate_authentication_options(
        rp_id=Config.RP_ID,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    session["webauthn_login_challenge"] = base64.b64encode(options.challenge).decode()
    return jsonify(json.loads(webauthn.options_to_json(options)))


@auth_bp.route("/webauthn/login-verify", methods=["POST"])
@limiter.limit("10 per minute")
def webauthn_login_verify():
    if not _webauthn_available():
        return jsonify({"error": "py-webauthn not installed"}), 501

    challenge_b64 = session.pop("webauthn_login_challenge", None)
    if not challenge_b64:
        return jsonify({"error": "No login challenge in session"}), 400

    import webauthn

    data = request.get_json()
    cred_id_raw = data.get("id", "")

    stored = WebAuthnCredential.query.filter_by(credential_id=cred_id_raw).first()
    if not stored:
        return jsonify({"error": "Credential not found"}), 404

    pub_key_bytes = base64.urlsafe_b64decode(stored.public_key + "==")

    try:
        verification = webauthn.verify_authentication_response(
            credential=data,
            expected_challenge=base64.b64decode(challenge_b64),
            expected_rp_id=Config.RP_ID,
            expected_origin=Config.ORIGIN,
            credential_public_key=pub_key_bytes,
            credential_current_sign_count=stored.sign_count,
            require_user_verification=False,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    stored.sign_count = verification.new_sign_count
    db.session.commit()

    user = User.query.get(stored.user_id)
    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"id": user.id, "username": user.username})
