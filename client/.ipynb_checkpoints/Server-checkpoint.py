from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from base64 import b64encode, b64decode
from urllib.parse import urlparse
from urllib.parse import quote
from Crypto.Cipher import AES
from dotenv import load_dotenv
from typing import List
from Backend.MySQL import MySQL_Doing
from Backend import Define
from pydantic import BaseModel, Field
from decimal import Decimal, InvalidOperation
import pandas as pd
import secrets, hashlib, urllib.parse, base64, json, time, hmac, os, redis, httpx

api = APIRouter(prefix='/api')

load_dotenv()
MySQL_Doing = MySQL_Doing()

app = FastAPI(
    title="H_Bus API",
    version="V0.1.0",
    description="H_Bus 服務的最小 API 範本，含健康檢查與根路由。",
)

# === 加入 CORS 設定 ===    
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://([a-zA-Z0-9-]+\.ngrok-free\.app|localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|140\.134\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# === Redis 初始化 ===
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# === URL 相關設定 ===
BASE_URL = os.getenv("FRONTEND_DEFAULT_URL")
FRONTEND_DEFAULT_URL = f"{BASE_URL}/profile"
FRONTEND_DEFAULT_HOST = urlparse(FRONTEND_DEFAULT_URL).hostname if FRONTEND_DEFAULT_URL.startswith(('http://', 'https://')) else None
r = redis.from_url(REDIS_URL, decode_responses=True)

# === LINE 相關設定 ===
CHANNEL_ID = os.getenv("LINE_CHANNEL_ID")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CALLBACK_PATH = "/auth/line/callback"
AUTHORIZE_URL = "https://access.line.me/oauth2/v2.1/authorize"
TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
PROFILE_URL = "https://api.line.me/v2/profile"
APP_SESSION_SECRET = os.getenv("APP_SESSION_SECRET", "my-secret")

# === 金流 相關設定 ===
MERCHANT_ID   = os.getenv("MERCHANT_ID", "")
TERMINAL_ID   = os.getenv("TERMINAL_ID", "")
STORE_CODE    = os.getenv("STORE_CODE", "")
KEY_HEX       = os.getenv("KEY", "")
IV_HEX        = os.getenv("IV", "")
LAYMON        = os.getenv("LAYMON", "iqrc.epay365.com.tw")  # 雷門 host，不要加 https://
PUBLIC_BASE   = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")  # 例: https://hualenbus.labelnine.app:8600

if not all([MERCHANT_ID, TERMINAL_ID, STORE_CODE, KEY_HEX, IV_HEX, PUBLIC_BASE]):
    raise RuntimeError("環境變數缺失：請確認 MERCHANT_ID / TERMINAL_ID / STORE_CODE / KEY / IV / PUBLIC_BASE_URL")

KEY = bytes.fromhex(KEY_HEX)
IV  = bytes.fromhex(IV_HEX)

# === Session 與 Token 工具 ===
class SessionManager:
    @staticmethod
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")
    @staticmethod
    def _sign(data: bytes) -> str:
        sig = hmac.new(APP_SESSION_SECRET.encode(), data, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).decode().rstrip("=")
    @staticmethod
    def make_session_token(user_id: str, ttl: int = 7*24*3600) -> str:
        payload = {"uid": user_id, "exp": int(time.time()) + ttl}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return f"{base64.urlsafe_b64encode(raw).decode().rstrip('=')}.{SessionManager._sign(raw)}"
    @staticmethod
    def verify_session_token(token: str | None) -> str | None:
        if not token or "." not in token:
            return None
        try:
            b64p, sig = token.split(".", 1)
            payload = base64.urlsafe_b64decode(b64p + "===")
            if SessionManager._sign(payload) != sig:
                return None
            obj = json.loads(payload.decode())
            if obj.get("exp", 0) < int(time.time()):
                return None
            return obj.get("uid")
        except Exception:
            return None

# === LINE OAuth 流程 ===
class LineAuth:
    @staticmethod
    def get_login_url(state, challenge):
        redirect_uri = f"{BASE_URL}{CALLBACK_PATH}"
        params = {
            "response_type": "code",
            "client_id": CHANNEL_ID,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "openid profile",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    @staticmethod
    async def exchange_token(code, verifier):
        redirect_uri = f"{BASE_URL}{CALLBACK_PATH}"
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": CHANNEL_ID,
            "client_secret": CHANNEL_SECRET,
            "code_verifier": verifier,
        }
        async with httpx.AsyncClient() as client:
            tr = await client.post(TOKEN_URL, data=form, headers={"Content-Type":"application/x-www-form-urlencoded"})
            if tr.status_code != 200:
                raise HTTPException(400, f"Token error: {tr.text}")
            token = tr.json()
            prof = await client.get(PROFILE_URL, headers={"Authorization": f"Bearer {token['access_token']}"})
            if prof.status_code != 200:
                raise HTTPException(400, f"Profile error: {prof.text}")
            profile = prof.json()
        return token, profile

# === Helper: return_to 安全檢查 ===
def _is_safe_return_to(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        # 允許本機/內網
        if host in ("localhost", "127.0.0.1") or host.startswith("192.168.") or host.startswith("10."):
            return True
        # 允許 ngrok
        if host.endswith(".ngrok-free.app"):
            return True
        # 允許環境變數清單
        allowed_env = os.getenv("ALLOWED_RETURN_ORIGINS", "")
        if allowed_env:
            allowed_list = [o.strip() for o in allowed_env.split(",") if o.strip()]
            origin = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}" if parsed.port else f"{parsed.scheme}://{parsed.hostname}"
            if origin in allowed_list:
                return True
        return False
    except Exception:
        return False

def _default_frontend_url(request: Request, path: str = "/profile") -> str:
    """登入後預設導向網址：優先使用 ngrok/指定網域，其餘回退環境變數"""
    try:
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            host = parsed.hostname or ""
            if host and (host.endswith(".ngrok-free.app") or (FRONTEND_DEFAULT_HOST and host == FRONTEND_DEFAULT_HOST)):
                candidate = f"{origin.rstrip('/')}{path}"
                if _is_safe_return_to(candidate):
                    return candidate
    except Exception:
        pass
    if FRONTEND_DEFAULT_URL.startswith(("http://", "https://")):
        return FRONTEND_DEFAULT_URL
    return f"http://{FRONTEND_DEFAULT_URL.lstrip('/') }"

def _build_login_url(request: Request, return_to: str | None = None) -> str:
    """組出 LINE Login 的登入 URL，並帶上 return_to。"""
    try:
        rt = return_to or _default_frontend_url(request)
        q = urllib.parse.urlencode({"return_to": rt})
        return f"{BASE_URL}/auth/line/login?{q}"
    except Exception:
        return f"{BASE_URL}/auth/line/login"

def _unauthorized_response(request: Request, detail: str):
    """依請求型態決定回傳 302 導轉或 401 JSON，避免僅在前端顯示而無指引。"""
    login_url = _build_login_url(request)
    accept = (request.headers.get("accept") or "").lower()
    sec_mode = (request.headers.get("sec-fetch-mode") or "").lower()
    sec_dest = (request.headers.get("sec-fetch-dest") or "").lower()
    wants_html = ("text/html" in accept) and ("application/json" not in accept)
    is_navigation = (sec_mode == "navigate") or (sec_dest in {"document", "iframe"})

    if wants_html or is_navigation:
        # 瀏覽器直接導向登入頁
        return RedirectResponse(login_url, status_code=302)
    # API/fetch：回 401 並附上登入入口，讓前端可決定導向
    raise HTTPException(status_code=401, detail={"detail": detail, "login_url": login_url})
    
# --- AES256-CBC 加解密 ---
def pad(s: str) -> str:
    pad_len = 16 - (len(s.encode("utf-8")) % 16)
    return s + chr(pad_len) * pad_len

def unpad(s: str) -> str:
    pad_len = ord(s[-1])
    return s[:-pad_len]

def encrypt_aes(data: str, key: bytes, iv: bytes) -> str:
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct_bytes = cipher.encrypt(pad(data).encode("utf-8"))
    return b64encode(ct_bytes).decode("utf-8")

def decrypt_aes(enc: str, key: bytes, iv: bytes) -> str:
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = cipher.decrypt(b64decode(enc))
    return unpad(pt.decode("utf-8"))

# ====== 請款請求模型 ======
class CreatePaymentIn(BaseModel):
    amount: str = Field(..., description="金額（以元為單位，純數字字串，例如 '10' 或 '199'）")
    order_number: str = Field(..., min_length=1, max_length=64, description="商家訂單編號")
    # 若要自訂導回路徑，可開額外欄位；目前用固定 /return
    # return_path: str | None = "/return"

class CreatePaymentOut(BaseModel):
    pay_url: str

# === 前端路線資訊 ===
@app.get("/healthz", tags=["meta"], summary="健康檢查")
def healthz():
    """用於監控或負載平衡器的健康檢查端點"""
    return {"status": "error 404"}

@api.get("/All_Route", tags=["Client"], summary="所有路線")
def All_Route():
    rows = MySQL_Doing.run("SELECT * FROM bus_routes_total")

    df_cols = MySQL_Doing.run("SHOW COLUMNS FROM bus_routes_total")
    columns = df_cols["Field"].tolist()

    df = pd.DataFrame(rows, columns=columns)

    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce") \
            .apply(lambda x: x.to_pydatetime() if pd.notnull(x) else None)

    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    return records

@api.post("/Route_Stations", response_model=List[Define.StationOut], tags=["Client"], summary="所有站點")
def get_route_stations(q: Define.RouteStationsQuery):
    sql = "SELECT * FROM bus_route_stations WHERE route_id = %s"
    params = [q.route_id]
    if q.direction:
        sql += " AND direction = %s"
        params.append(q.direction)

    try:
        rows = MySQL_Doing.run(sql, params)
    except TypeError:
        if q.direction:
            rows = MySQL_Doing.run(f"SELECT * FROM bus_route_stations WHERE route_id = {int(q.route_id)} AND direction = '{q.direction}'")
        else:
            rows = MySQL_Doing.run(f"SELECT * FROM bus_route_stations WHERE route_id = {int(q.route_id)}")

    df_cols = MySQL_Doing.run("SHOW COLUMNS FROM bus_route_stations")
    columns = df_cols["Field"].tolist()
    df = pd.DataFrame(rows, columns=columns)

    if df.empty:
        return []
    col_map = {
        "station_name": "stop_name",
        "stop_name": "stop_name",
        "est_time": "eta_from_start",
        "eta_from_start": "eta_from_start",
        "order_no": "stop_order",
        "seq": "stop_order",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    if "latitude" in df.columns:
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    if "longitude" in df.columns:
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    if "eta_from_start" in df.columns:
        df["eta_from_start"] = pd.to_numeric(df["eta_from_start"], errors="coerce").astype("Int64")
    if "stop_order" in df.columns:
        df["stop_order"] = pd.to_numeric(df["stop_order"], errors="coerce").astype("Int64")
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce") \
            .apply(lambda x: x.to_pydatetime() if pd.notnull(x) else None)
    desired_cols = [
        "route_id", "route_name", "direction", "stop_name",
        "latitude", "longitude", "eta_from_start", "stop_order", "created_at"
    ]
    keep_cols = [c for c in desired_cols if c in df.columns]
    df = df[keep_cols]
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    data: List[Define.StationOut] = [Define.StationOut(**r) for r in records]
    return data

@api.get("/yo_hualien", tags=["Client"], summary="行動遊花蓮")
def yo_hualien():
    rows = MySQL_Doing.run("SELECT station_name, address, latitude, longitude FROM action_tour_hualien")
    columns = ["station_name", "address", "latitude", "longitude"]
    df = pd.DataFrame(rows, columns=columns)
    return df.to_dict(orient="records") 

@api.get("/GIS_About", tags=["Client"], summary="取得最新車輛資訊")
def Get_GIS_About():
    Results = MySQL_Doing.run("""
    Select route from car_resource
    where route != 'None'
    """)

    print(Results["route"].tolist())
    Results = MySQL_Doing.run("""
    SELECT c.route, c.X, c.Y, c.direction, c.Current_Loaction
    FROM car_backup c
    JOIN (
        SELECT route, MAX(seq) AS max_seq
        FROM car_backup
        WHERE route IN ('1', '2', '3')
        GROUP BY route
    ) t ON c.route = t.route AND c.seq = t.max_seq;
    """)
    return Results

@api.post("/reservation", tags=["Client"], summary="送出預約")
def push_reservation(req: Define.ReservationReq):
    sql = f"""
    INSERT INTO reservation (
        user_id, booking_time, booking_number, 
        booking_start_station_name, booking_end_station_name
    ) VALUES (
        '{req.user_id}', 
        '{req.booking_time}', 
        '{req.booking_number}', 
        '{req.booking_start_station_name}', 
        '{req.booking_end_station_name}'
    )
    """
    MySQL_Doing.run(sql)
    return {"status": "success", "sql": sql}

@api.get("/reservations/my", tags=["Client"], summary="預約查詢")
def show_reservations(user_id: str):
    sql = f"""
    SELECT reservation_id, user_id, booking_time, booking_number, 
           booking_start_station_name, booking_end_station_name,
           review_status, payment_status
    FROM reservation where user_id = '{user_id}'
    """
    results = MySQL_Doing.run(sql)

    # 如果是 DataFrame，轉成 dict
    if hasattr(results, "to_dict"):
        records = results.where(pd.notnull(results), None).to_dict(orient="records")
    else:
        # 已經是 list/dict 的情況
        records = results

    # 確保 numpy.int64 → int
    for r in records:
        for k, v in r.items():
            if isinstance(v, (pd._libs.missing.NAType, type(None))):
                r[k] = None
            elif hasattr(v, "item"):  # numpy scalar
                r[k] = v.item()

    return {"status": "success", "data": records}

@api.get("/reservations/tomorrow", tags=["Client"], summary="預約查詢")
def tomorrow_reservations(user_id: str):
    sql = f"""
    SELECT reservation_id, user_id, booking_time, booking_number, 
           booking_start_station_name, booking_end_station_name,
           review_status, payment_status
    FROM reservation where 
    review_status = 'approved' AND
    DATE(booking_time) = DATE_ADD(CURDATE(), INTERVAL 1 DAY) AND
    user_id = '{user_id}'
    """
    print("查詢明日預約 user_id=", user_id)
    print("SQL=", sql)
    results = MySQL_Doing.run(sql)

    return {"status": "success", "sql": results}

@api.post("/reservations/Canceled", tags=["Client"], summary="取消預約")
def Cancled_reservation(req: Define.CancelReq):
    sql = f"""
    UPDATE reservation
    SET review_status = 'canceled',
        cancel_reason = '{req.cancel_reason}'
    WHERE reservation_id = {req.reservation_id};
    """
    Results = MySQL_Doing.run(sql)
    return {"status": "success", "sql": Results}

# === 使用者更新資訊 ===
@api.post("/users/update_mail", tags=["Users"], summary="更新使用者Email")
def update_mail(user_id: int, email: str):
    sql = f"""
    UPDATE users
    SET email = '{email}',
        updated_at = NOW()
    WHERE user_id = {user_id};
    """
    results = MySQL_Doing.run(sql)
    return {"status": "success", "sql": sql, "results": results}

@api.post("/users/update_phone", tags=["Users"], summary="更新使用者Email")
def update_phone(user_id: int, phone: str):
    sql = f"""
    UPDATE users
    SET phone = '{phone}',
        updated_at = NOW()
    WHERE user_id = {user_id};
    """
    results = MySQL_Doing.run(sql)
    return {"status": "success", "sql": sql, "results": results}

# === LINE 登入與使用者權限相關API資訊 ===
@app.get("/auth/line/login", tags=["Auth"], summary="Line 登入")
def login(request: Request):
    force = request.query_params.get("force")
    uid = SessionManager.verify_session_token(request.cookies.get("app_session"))
    q_return_to = request.query_params.get("return_to")

    if q_return_to and _is_safe_return_to(q_return_to):
        resolved_return_to = q_return_to
    else:
        resolved_return_to = _default_frontend_url(request)

    # 防呆：如果 Redis 有但 MySQL 查不到 → 視為無效 session
    if not force and uid and r.exists(f"user:{uid}"):
        db_check = MySQL_Doing.run(f"SELECT 1 FROM users WHERE line_id='{uid}' LIMIT 1;")
        if db_check:
            return RedirectResponse(resolved_return_to)
        else:
            print(f"[WARN] Redis 有 session，但 MySQL 查不到 user={uid}，強制重登")
            r.delete(f"user:{uid}")  # 清理 Redis
            # 不 return，繼續往下走 LINE OAuth

    # 強制走 LINE OAuth
    state = secrets.token_urlsafe(16)
    verifier = secrets.token_urlsafe(64)
    challenge = SessionManager.b64url(hashlib.sha256(verifier.encode()).digest())
    r.setex(f"login_state:{state}", 300, json.dumps({"verifier": verifier, "return_to": resolved_return_to}))
    url = LineAuth.get_login_url(state, challenge)
    return RedirectResponse(url)

@app.get("/logout", tags=["Auth"], summary="登出")
def logout(request: Request):
    redirect_url = _default_frontend_url(request)
    resp = RedirectResponse(redirect_url)
    resp.delete_cookie("app_session")
    return resp

@app.get("/auth/line/callback", tags=["Auth"], summary="Line 登入回呼")
async def callback(request: Request, code: str | None = None, state: str | None = None):
    data = r.get(f"login_state:{state}")
    if not code or not state or not data:
        raise HTTPException(400, "Invalid state or code")

    st = json.loads(data)
    r.delete(f"login_state:{state}")
    verifier = st["verifier"]
    return_to = st.get("return_to")

    # ===== 1. 向 LINE API 換 token & profile =====
    token, profile = await LineAuth.exchange_token(code, verifier)
    uid = profile["userId"]

    # ===== 2. 產生 session token =====
    app_token = SessionManager.make_session_token(uid)

    # ===== 3. 存到 Redis (短期快取) =====
    r.setex(f"user:{uid}", token["expires_in"], json.dumps({
        "profile": profile,
        "access_token": token["access_token"],
        "refresh_token": token["refresh_token"],
        "exp": int(time.time()) + token["expires_in"],
        "session_token": app_token
    }))
    r.setex(f"session:{app_token}", 7*24*3600, uid)

    # ===== 4. 寫入 MySQL (長期存放) =====
    LineID = profile["userId"]
    UserName = profile["displayName"]
    print(f"[DEBUG] LINE Profile: {profile}")
    print(f"[DEBUG] LineID={LineID}, UserName={UserName}, AppToken={app_token}")
    try:
        MySQL_Doing.run(f"""
        INSERT INTO users (line_id, username, password, session_token, last_login)
        VALUES ('{LineID}', '{UserName}', '', '{app_token}', NOW())
        ON DUPLICATE KEY UPDATE session_token='{app_token}', last_login=NOW();
        """)
    except Exception as e:
        print(f"MySQL insert error: {e}")

    # ===== 5. 設定 Cookie 並跳轉到前端 =====
    # 固定跳轉到前端 Profile 頁
    redirect_url = _default_frontend_url(request)
    if return_to and _is_safe_return_to(return_to):
        redirect_url = return_to

    resp = RedirectResponse(redirect_url)
    is_https = str(BASE_URL or '').lower().startswith('https://')
    samesite = "none" if is_https else "lax"
    secure = True if is_https else False
    resp.set_cookie("app_session", app_token, httponly=True, max_age=7*24*3600, samesite=samesite, secure=secure)
    return resp

@app.get("/me", tags=["Auth"], summary="取得使用者資訊")
async def me(request: Request):
    app_token = request.cookies.get("app_session")
    if not app_token:
        return _unauthorized_response(request, "not logged in")

    result = MySQL_Doing.run(f"""
        SELECT user_id, line_id, username, email, phone, last_login
        FROM users
        WHERE session_token = '{app_token}'
        LIMIT 1;
    """)

    if result.empty:
        # 防呆：自動清理 Redis 裡壞掉的 session
        uid = SessionManager.verify_session_token(app_token)
        if uid:
            r.delete(f"user:{uid}")
            r.delete(f"session:{app_token}")
            print(f"[CLEANUP] 清掉無效 session: user={uid}")
        return _unauthorized_response(request, "session not found")

    row = result.iloc[0].to_dict()
    return {
        "user_id": row["user_id"],
        "line_id": row["line_id"],
        "username": row["username"],
        "email": row["email"],
        "phone": row["phone"],
        "last_login": row["last_login"],
    }

# ====== 建立付款連結（正式） ======
@app.post("/payments", response_model=CreatePaymentOut, tags = ["Pay"], summary="建立付款連結")
def create_payment(body: CreatePaymentIn):
    # 驗證 amount 為正數（避免浮點誤差，使用 Decimal）
    try:
        amt = Decimal(body.amount)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="amount 格式錯誤")

    if amt <= 0 or amt != amt.quantize(Decimal("1")):
        # 雷門若要求整數元，這裡限制為整數金額；若允許小數請調整 quantize
        raise HTTPException(status_code=400, detail="amount 必須為正整數（元）")

    payload = {
        "merchant_id": MERCHANT_ID,
        "terminal_id": TERMINAL_ID,
        "store_code":  STORE_CODE,
        "set_price": str(amt),                     # 金額（元）
        "pos_order_number": body.order_number,     # 訂單編號
        "callback_url": f"{PUBLIC_BASE}/callback", # 供雷門伺服器回呼
        "return_url":   f"{PUBLIC_BASE}/return"    # 供使用者導回顯示頁
    }

    json_str = json.dumps(payload, separators=(',', ':'))
    transaction_data = encrypt_aes(json_str, KEY, IV)
    hash_digest = hashlib.sha256(transaction_data.encode("utf-8")).hexdigest()

    url = f"https://{LAYMON}/calc/pay_encrypt/{STORE_CODE}"
    full_url = f"{url}?TransactionData={quote(transaction_data)}&HashDigest={hash_digest}"

    return CreatePaymentOut(pay_url=full_url)

# ====== 雷門回傳 callback（伺服器對伺服器） ======
@app.post("/callback", tags = ["Pay"])
async def callback(request: Request):
    body = await request.json()
    enc_data = body.get("TransactionData")
    hash_digest = body.get("HashDigest")

    if not enc_data or not hash_digest:
        raise HTTPException(status_code=400, detail="缺少必要欄位")

    # 驗證 hash
    if hashlib.sha256(enc_data.encode("utf-8")).hexdigest() != hash_digest:
        raise HTTPException(status_code=400, detail="Hash 驗證失敗")

    # 解密資料
    try:
        decrypted = decrypt_aes(enc_data, KEY, IV)
        data = json.loads(decrypted)
        # TODO: 在此更新你的訂單狀態（付款成功/失敗等），依雷門實際回傳欄位解讀
        return {"status": "ok", "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解密失敗: {e}")

# ====== 使用者導回頁（前端顯示用） ======
@app.get("/return", tags = ["Pay"])
def return_page():
    # 你可以改成回傳 HTML 或重導到你的前端頁面
    return {"message": "付款流程結束，這裡顯示給使用者看"}

# === 前端靜態檔案服務 ===
app.include_router(api)
app.mount('/', StaticFiles(directory='dist', html=True), name='client')

# === FastAPI 把 API 跟前端打包 ===
@app.exception_handler(StarletteHTTPException)
async def spa_fallback(request: Request, exc: StarletteHTTPException):
    try:
        if exc.status_code == 404 and request.method in ("GET", "HEAD"):
            path = request.url.path or "/"
            accept = (request.headers.get("accept") or "").lower()
            # only for browser navigations to non-API paths
            if (
                not path.startswith("/api")
                and not path.startswith("/auth")
                and ("text/html" in accept or accept == "*/*")
            ):
                index_path = os.path.join("dist", "index.html")
                if os.path.exists(index_path):
                    return FileResponse(index_path)
    except Exception:
        pass
    raise exc
