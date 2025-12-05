# ====================================
# 🧩 專案內部模組
# ====================================
from Backend.CreateUserQR import generate_boarding_token, save_qr_png
from Backend.CheckQR import verify_boarding_token
from Backend.MySQL import MySQL_Doing
from Backend import Define
# ====================================
# 📦 第三方套件
# ====================================
from fastapi import FastAPI, Request, HTTPException, APIRouter, Body, Depends, status
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from dotenv import load_dotenv
from io import BytesIO
import pandas as pd
import holidays
import qrcode
import redis
import httpx
# ====================================
# ✅ 標準庫
# ====================================
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlparse, quote
from base64 import b64decode
from typing import List, Tuple
from zoneinfo import ZoneInfo
from datetime import datetime
from decimal import Decimal
from threading import RLock
import os, json, time, math, base64, requests
import urllib, hmac, hashlib, secrets, tempfile, smtplib
import uuid
# ====================================
# 定義 Fast API 項目 api / app 隔離
# ====================================
api = APIRouter(prefix='/api')
app = FastAPI(
    title="H_Bus API",
    version="V0.1.0",
    description="H_Bus 服務的最小 API 範本，含健康檢查與根路由。",
    docs_url=None,      # 關掉預設 /docs
    redoc_url=None      # 關掉預設 /redoc
)
# 
security = HTTPBasic()
DOCS_USER = os.getenv("DOCS_USER", "admin")
DOCS_PASS = os.getenv("DOCS_PASS", "Hbus@109")

def verify_docs_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, DOCS_USER)
    correct_pass = secrets.compare_digest(credentials.password, DOCS_PASS)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

@app.get("/docs", include_in_schema=False)
def custom_docs(credentials: bool = Depends(verify_docs_auth)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Secure API Docs")

@app.get("/redoc", include_in_schema=False)
def custom_redoc(credentials: bool = Depends(verify_docs_auth)):
    return get_redoc_html(openapi_url="/openapi.json", title="Secure API ReDoc")

# === 加入 CORS 設定 ===    
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://([a-zA-Z0-9-]+\.ngrok-free\.app|localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|140\.134\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
# ====================================
# 初始化
# ====================================
load_dotenv()
MySQL_Doing = MySQL_Doing()

# Simple in-process cache to reduce DB load when users toggle directions rapidly
# _ROUTE_STOPS_CACHE: dict[Tuple[int, str], Tuple[float, list]] = {}
# _ROUTE_STOPS_TTL_SEC = 120  # 2 minutes
# _ROUTE_STOPS_LOCK = RLock()

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
# === email 相關設定 ===
SENDER_EMAIL = os.getenv("Sender_email")
SENDER_PASS  = os.getenv("Password_email")
# === 金流 相關設定 ===
MERCHANT_ID   = os.getenv("MERCHANT_ID", "")
TERMINAL_ID   = os.getenv("TERMINAL_ID", "")
STORE_CODE    = os.getenv("STORE_CODE", "")
KEY_HEX       = os.getenv("KEY", "")
IV_HEX        = os.getenv("IV", "")
LAYMON        = os.getenv("LAYMON", "iqrc.epay365.com.tw")  # 雷門 host，不要加 https://
PUBLIC_BASE   = os.getenv("FRONTEND_DEFAULT_URL", "").rstrip("/") 

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

# === Main Route 流程 ===
class TaiwanHolidayChecker:
    def __init__(self):
        # 使用 holidays 套件初始化台灣假日表
        self.holidays = holidays.TW()

    def now_datetime(self):
        # 回傳目前時間（台北時區假設為系統當地時間）
        return datetime.now()

    def is_holiday(self, date=None):
        """
        判定給定日期是否為假日。
        如果 date 為 None，則使用今天。
        返回 True (假日) 或 False (非假日)。
        假日定義：在 holidays.TW 假日清單中 或 星期六／星期日。
        """
        if date is None:
            date = self.now_datetime().date()

        # 星期六(5)或星期日(6)
        if date.weekday() >= 5:
            return True

        # 是否為國定假日（假日套件中有記錄）
        if date in self.holidays:
            return True

        return False

    def display(self):
        """顯示今天是否為假日"""
        now = self.now_datetime()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        holiday_flag = self.is_holiday(now.date())
        # print(f"現在時間：{date_str} {time_str}")
        if holiday_flag:
            return("假日")
        else:
            return("工作日")

    def display_input(self, days_test):
        """讓使用者輸入日期來測試"""
        user_input = days_test.strip()
        if user_input:
            try:
                test_date = datetime.strptime(user_input, "%Y-%m-%d").date()
            except ValueError:
                print("⚠️ 日期格式錯誤，請輸入 YYYY-MM-DD")
                return
        else:
            test_date = self.now_datetime().date()

        holiday_flag = self.is_holiday(test_date)
        # print(f"測試日期：{test_date}")
        if holiday_flag:
            return("假日")
        else:
            return("工作日")

class Route_Processing():
    """邏輯：先有所有路線，顯示各站資訊，跟車輛動態無關，接著根據排程更新車輛資訊"""
    def __init__(self):
        checker = TaiwanHolidayChecker()
        self.Today = checker.display()
        self.now_time = datetime.now().time()
        # self.Today = checker.display_input("2025-01-02")
        # self.now_time = datetime.strptime("13:29", "%H:%M").time()
        print(f"=== DeBUG {self.Today}{self.now_time}")

        self.All_Route = None
        self.All_Schedual = None
        print("初始化完成")

    # ======================================================
    # 🔧 工具工具工具區（Utility Functions）
    # ======================================================
    def map_direction(self, d):
        # 統一方向
        if d in ["返程", "回程"]:
            return "回程"
        return "去程"

    def to_float(self, x):
        if isinstance(x, Decimal):
            return float(x)
        return float(x)

    def validate_and_fix_latlon(self, lat, lon):
        """
        自動修正常見經緯度錯誤：
        - Decimal → float
        - 交換 lat/lon（顛倒）
        - 非台灣區域 → 回傳 None
        """
        lat, lon = self.to_float(lat), self.to_float(lon)

        if lat is None or lon is None:
            return None, None, "invalid_number"

        # --- Step 1: 若緯度不在 -90~90 / 經度不在 -180~180 → 一定有問題
        if abs(lat) > 90 or abs(lon) > 180:
            # 嘗試交換
            lat, lon = lon, lat

        # --- Step 2: 再檢查一次合理範圍
        if abs(lat) > 90 or abs(lon) > 180:
            return None, None, "invalid_range"

        # --- Step 3: 台灣範圍檢查 ---
        in_tw = (21.5 <= lat <= 25.5) and (119.0 <= lon <= 123.0)

        return lat, lon, ("ok" if in_tw else "outside_tw")

    def normalize_direction(self, x):
        t = str(x or "").strip()
        if "返" in t or "回" in t or t == "1":
            return "回程"
        return "去程"

    def haversine_km(self, lat1, lon1, lat2, lon2):
        # --- 自動修正經緯度 ---
        lat1, lon1, _ = self.validate_and_fix_latlon(lat1, lon1)
        lat2, lon2, _ = self.validate_and_fix_latlon(lat2, lon2)

        if lat1 is None or lat2 is None:
            return None  # 不能計算距離

        # --- Haversine ---
        R = 6371.0  # 地球半徑（公里）
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        d = 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return d
    # ======================================================
    # 🕒 時間 / 排程工具（Schedule Utils）
    # ======================================================
    def next_bus_from_schedule(self, schedule, status="正常營運"):
        # 1️⃣ 車輛非正常營運：整條都視為未發車
        if status != "正常營運":
            return "未發車"
        
        # 2️⃣ 行程表為空
        if not schedule or schedule == "None":
            return "未發車"

        # 3️⃣ 分割行程表
        times = [t.strip() for t in schedule.split(",") if t.strip()]

        for t in times:
            sched_time = datetime.strptime(t, "%H:%M").time()
            if sched_time > self.now_time:
                return sched_time.strftime("%H:%M")

        # 4️⃣ 全部班次都已過 → 末班已發
        return "末班已發"
        
    def Search_All_Route(self):
        """各路線顯示（展開去程/回程）"""

        Total = MySQL_Doing.run("select * from bus_routes_total where status = 1")
        Total = Total[["route_id", "route_name", "direction"]]
        return Total
    
    # def Search_All_Schedual(self):
    #     """車輛狀態顯示"""
    #     All_schedual = MySQL_Doing.run("select * from route_schedule where operation_status = '正常營運'")
    #     All_schedual = All_schedual[["route_no", "direction","license_plate","operation_status", "vehicle_status"]]
    #     return All_schedual

    def Search_All_Schedual(self):
        """車輛狀態顯示 + 加入GIS座標"""
        All_schedual = MySQL_Doing.run("""
            select route_no, direction, license_plate, operation_status, vehicle_status
            from route_schedule
            where operation_status = '正常營運'
        """)

        # 先加欄位
        All_schedual["X"] = "NONE"
        All_schedual["Y"] = "NONE"

        for index, row in All_schedual.iterrows():
            plate = row["license_plate"]
            status = row["vehicle_status"]

            if status == "on_duty":
                Car_GIS = Route_Processing.Search_ForGIS(plate)

                # ---- 防呆：None 或空資料 ----
                if Car_GIS is None or len(Car_GIS) == 0:
                    continue

                # ---- 防呆：欄位不存在 ----
                if "X" not in Car_GIS.columns or "Y" not in Car_GIS.columns:
                    continue

                # ---- 寫回 DataFrame ----
                try:
                    All_schedual.at[index, "X"] = Car_GIS["X"].iloc[0]
                    All_schedual.at[index, "Y"] = Car_GIS["Y"].iloc[0]
                except:
                    # 任何例外也補上 NONE (保險)
                    All_schedual.at[index, "X"] = "NONE"
                    All_schedual.at[index, "Y"] = "NONE"

        return All_schedual

    def Search_Original_Stations(self, route_id, direction):
        Stop = MySQL_Doing.run(f"""
        select * from bus_route_stations 
        where route_id = {route_id} and direction = '{direction}'
        """)
        return Stop

    def Search_Stop_Stations(self, route_id, direction, status="正常營運"):
        Stop = MySQL_Doing.run(f"""
        select * from bus_route_stations 
        where route_id = {route_id} and direction = '{direction}'
        """)
        # ⭐ 若沒有站點 → 回傳空白模板（防止 KeyError）
        if Stop is None or Stop.empty:
            return pd.DataFrame({
                "route_id": [],
                "direction": [],
                "stop_name": [],
                "latitude": [],
                "longitude": [],
                "Next_Stop": []
            })

        # ⭐ 決定 schedule 欄位
        raw_col = "schedule" if self.Today == "工作日" else "schedule2"

        # ⭐ schedule 欄位不存在 → 全部視為未發車
        if raw_col not in Stop.columns:
            Stop["Next_Stop"] = "未發車"
        else:
            # 統一將 "None" → 空白
            Stop[raw_col] = Stop[raw_col].replace("None", "")
            Stop["Next_Stop"] = Stop[raw_col].apply(
                lambda s: self.next_bus_from_schedule(s, status)
            )

        # ⭐ 保證欄位存在才回傳
        return Stop[[
            "route_id",
            "direction",
            "stop_name",
            "latitude",
            "longitude",
            "Next_Stop"
        ]]

    def Search_Carinfor(self, Station, GIS, vehicle_status='rest'):
        # 沒站資料 → 回傳空
        if Station is None or Station.empty:
            return Station

        # 休息狀態：直接回傳 next stop
        if vehicle_status == "rest":
            df = Station.copy()
            df["distance_km"] = None
            df["車子所在位置"] = df["Next_Stop"]
            return df

        # 🚫 沒 GPS 資料 → 未定位
        if GIS is None or GIS.empty:
            df = Station.copy()
            df["distance_km"] = None
            df["車子所在位置"] = "未定位"
            return df

        # 🚫 GPS X/Y 是 None → 未定位
        X = GIS["X"].iloc[0]
        Y = GIS["Y"].iloc[0]

        if X is None or Y is None:
            df = Station.copy()
            df["distance_km"] = None
            df["車子所在位置"] = "未定位"
            return df

        # 🚫 GPS 轉 float 失敗 → 未定位
        try:
            car_lat = self.to_float(Y)
            car_lon = self.to_float(X)
        except:
            df = Station.copy()
            df["distance_km"] = None
            df["車子所在位置"] = "未定位"
            return df

        # ========= 正常車輛定位流程 =========
        df = Station.copy()

        df["distance_km"] = df.apply(
            lambda row: self.haversine_km(
                car_lat, car_lon,
                row["latitude"], row["longitude"]
            ),
            axis=1
        )

        # 全 None → GPS 異常
        if df["distance_km"].isna().all():
            df["車子所在位置"] = "未定位"
            return df

        nearest_idx = df["distance_km"].idxmin()

        df["車子所在位置"] = ""

        cumulative_min = 0
        speed = 40  # km/h
        used_coming = False  # ⭐ 是否已使用「即將進站」

        for idx, row in df.iterrows():

            if idx < nearest_idx:
                df.at[idx, "車子所在位置"] = str(row["Next_Stop"])

            elif idx == nearest_idx:
                df.at[idx, "車子所在位置"] = "當班"

            else:
                dist = row["distance_km"]
                t_min = (dist / speed) * 60
                cumulative_min += t_min

                minutes = round(cumulative_min)

                if minutes == 0:
                    if not used_coming:
                        df.at[idx, "車子所在位置"] = "即將進站"
                        used_coming = True
                    else:
                        df.at[idx, "車子所在位置"] = "1分鐘"
                else:
                    df.at[idx, "車子所在位置"] = f"{minutes}分鐘"

        return df

    def Search_ForGIS(self, Car_Licence):
        GIS = MySQL_Doing.run(f"select * from ttcarimport where car_licence = '{Car_Licence}' order by seq desc limit 1")
        return GIS
        
    def Processing(self):
        routes = self.Search_All_Route()
        schedules = self.Search_All_Schedual()

        schedules["route_no"] = schedules["route_no"].astype(int)
        routes["route_id"] = routes["route_id"].astype(int)

        result_rows = []

        # ===== ① 組合排班 =====
        for _, row in routes.iterrows():
            rid = row["route_id"]
            rname = row["route_name"]
            rdir = row["direction"]

            target_dirs = ["去程"] if "單" in rdir else ["去程", "返程"]

            for d2 in target_dirs:
                match = schedules[
                    (schedules["route_no"] == rid) &
                    (schedules["direction"] == d2)
                ]

                if len(match) > 0:
                    m = match.iloc[0]
                    result_rows.append({
                        "route_no": rid,
                        "direction": d2,
                        "license_plate": m["license_plate"],
                        "operation_status": m["operation_status"],
                        "vehicle_status": m["vehicle_status"],
                        "X": m["X"],
                        "Y": m["Y"]
                    })
                else:
                    result_rows.append({
                        "route_no": rid,
                        "direction": d2,
                        "license_plate": "無排班",
                        "operation_status": "無排班",
                        "vehicle_status": "無資料",
                        "X": "NONE",
                        "Y": "NONE"
                    })

        # ===== ② 車輛當前位置（計算 當班位置 欄位）=====
        df_status = pd.DataFrame(result_rows)
        df_status["當班位置"] = "NONE"

        for idx, row in df_status.iterrows():
            plate = row["license_plate"]
            veh_status = row["vehicle_status"]
            route_no = row["route_no"]
            direction = row["direction"]

            # 休息 → 當班位置 = NONE
            if veh_status != "on_duty":
                df_status.at[idx, "當班位置"] = "NONE"
                continue

            # on_duty → 用 Search_Stop_Stations + Search_Carinfor 取得「當班位置」
            GIS = self.Search_ForGIS(plate)
            STA = self.Search_Stop_Stations(
                str(route_no),
                Route_Processing.map_direction(direction),
                row["operation_status"]
            )
            info = self.Search_Carinfor(STA, GIS, veh_status)

            # 找出 "當班" 那一列
            try:
                pos = info[info["車子所在位置"] == "當班"]["stop_name"].iloc[0]
                df_status.at[idx, "當班位置"] = pos
            except:
                df_status.at[idx, "當班位置"] = "NONE"

        # ===== ③ 輸出路線+站點 =====
        output_dict = {}
        for _, row in df_status.iterrows():
            rid = row["route_no"]
            d2 = row["direction"]
            key = f"{rid}-GO" if d2 == "去程" else f"{rid}-BACK"

            GIS = self.Search_ForGIS(row["license_plate"])
            STA = self.Search_Stop_Stations(
                str(rid),
                Route_Processing.map_direction(d2),
                row["operation_status"]
            )
            stationCarinfor = self.Search_Carinfor(STA, GIS, row["vehicle_status"])

            output_dict[key] = stationCarinfor

        # ===== ④ ⭐ 最終加上 All_Status =====
        output_dict["All_Status"] = df_status

        return output_dict

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
def unpad(s: str) -> str:
    pad_len = ord(s[-1])
    return s[:-pad_len]

def encrypt_aes(data: dict) -> str:
    """依雷門規範 AES-256-CBC + PKCS7 padding + Base64"""
    key = bytes.fromhex(KEY_HEX)
    iv = bytes.fromhex(IV_HEX)
    json_str = json.dumps(data, separators=(",", ":"))
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted_bytes = cipher.encrypt(pad(json_str.encode("utf-8"), 16))
    return base64.b64encode(encrypted_bytes).decode("utf-8")

def decrypt_aes(enc: str, key: bytes, iv: bytes) -> str:
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = cipher.decrypt(b64decode(enc))
    return unpad(pt.decode("utf-8"))

# --- 計算兩點距離 (Haversine公式) ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # 地球半徑（公尺）
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# --- 統一方向 ---
def normalize_direction(x):
    t = str(x or "").strip()
    if "返" in t or "回" in t or t == "1":
        return "回程"
    return "去程"

# ========== 全域設定 ==========
TZ_NAME = os.getenv("TZ", "Asia/Taipei")
TZ = ZoneInfo(TZ_NAME)
MAIL_SEND_HOUR = int(os.getenv("MAIL_SEND_HOUR", "8"))
MAIL_SEND_MIN = int(os.getenv("MAIL_SEND_MIN", "0"))

# ====================================
# Gmail Letter
# ====================================
# ========== 信件樣板 ==========
MAIL_SUBJECT = "【乘車提醒】您今日的預約資訊"
MAIL_TEXT_TEMPLATE = """親愛的乘客您好，

以下為您今日 ({today}) 的預約資訊：
{lines}

若資訊有誤或需更改，請盡速與我們聯繫。祝您旅途順利！

— 花蓮小巴預約系統
"""

# ========== 郵件發送 ==========
def send_email(receiver_email: str, subject: str, text: str):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = SENDER_EMAIL
    message["To"] = receiver_email
    message.attach(MIMEText(text, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.sendmail(SENDER_EMAIL, receiver_email, message.as_string())

# ========== 查詢今天預約 & 準備寄信名單 ==========
def fetch_today_reservations() -> pd.DataFrame:
    sql = """
    SELECT 
        u.email,
        r.user_id,
        r.reservation_id,
        r.booking_time,
        r.booking_number,
        r.booking_start_station_name,
        r.booking_end_station_name
    FROM reservation r
    JOIN users u ON u.user_id = r.user_id
    WHERE r.review_status = 'approved'
      AND DATE(r.booking_time) = CURDATE()
      AND u.email IS NOT NULL
      AND u.email <> '';
    """
    rows = MySQL_Doing.run(sql)
    return pd.DataFrame(rows)

# ========== 組信內容（依 email 彙整多筆預約） ==========
def build_and_send_emails():
    now = datetime.now(TZ)
    print(f"[{now:%Y-%m-%d %H:%M:%S}] Checking today's reservations...")

    try:
        df = fetch_today_reservations()
    except Exception as e:
        print(f"DB error: {e}")
        return

    if df.empty:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] No approved reservations found today.")
        return

    grouped = df.groupby("email", dropna=True)
    success, fail = 0, 0

    for email, g in grouped:
        lines = [
            f"- 預約編號: {r['reservation_id']}｜時間: {r['booking_time']}｜"
            f"人數: {r['booking_number']}｜{r['booking_start_station_name']} → {r['booking_end_station_name']}"
            for _, r in g.iterrows()
        ]
        body = MAIL_TEXT_TEMPLATE.format(today=f"{now:%Y-%m-%d}", lines="\n".join(lines))

        try:
            send_email(email, MAIL_SUBJECT, body)
            print(f"✔ Sent: {email} ({len(g)} records)")
            success += 1
        except Exception as e:
            print(f"✘ Failed: {email} → {e}")
            fail += 1

    print(f"[{datetime.now(TZ):%Y-%m-%d %H:%M:%S}] Completed — Success: {success}, Fail: {fail}")

# ========== 排程器啟動 ==========
def start_scheduler():
    scheduler = BackgroundScheduler(timezone=TZ)
    # === 你的每日寄信任務 ===
    scheduler.add_job(
        build_and_send_emails,
        CronTrigger(hour=MAIL_SEND_HOUR, minute=MAIL_SEND_MIN, timezone=TZ),
        id="daily_send",
        replace_existing=True
    )
     # === 新增：每 30 秒更新資料 ===
    scheduler.add_job(
        update_route_cache,
        trigger='interval',
        seconds=30,
        id="route_cache",
        replace_existing=True
    )

    scheduler.start()
    app.state.scheduler = scheduler
    # print(f"[scheduler] started — will send emails daily at {MAIL_SEND_HOUR:02d}:{MAIL_SEND_MIN:02d} ({TZ_NAME})")
    print(f"[scheduler] started — daily email + 30 sec route cache running")

    # sched = getattr(app.state, "scheduler", None)
    # if sched:
    #     sched.shutdown()
    #     print("[scheduler] stopped")

# ====================================
# Route Setting
# ====================================
Route_Processing = Route_Processing()
app.state.Total_Route = None
app.state.Schedule_Route = None
app.state.Process_Route = None

def update_route_cache(): 
    print("[Task] Updating route cache...") 
    try: 
        app.state.Total_Route = Route_Processing.Search_All_Route() 
        app.state.Schedule_Route = Route_Processing.Search_All_Schedual() 
        app.state.Process_Route = Route_Processing.Processing() 

        checker = TaiwanHolidayChecker()
        Route_Processing.Today = checker.display()
        Route_Processing.now_time = datetime.now().time()
        print("[Task] Cache updated successfully.") 
        print(Route_Processing.Today, Route_Processing.now_time)
        # print(app.state.Total_Route)
        # print(app.state.Schedule_Route)
        # print(app.state.Process_Route)
    except Exception as e: 
        print("[Task] ERROR:", e)
        
update_route_cache()

@app.on_event("startup")
def on_startup():
    start_scheduler()

@app.on_event("shutdown")
def on_shutdown():
    sched = getattr(app.state, "scheduler", None)
    if sched:
        sched.shutdown()
        print("[scheduler] stopped")
        
# === 前端路線資訊 ===
@app.get("/healthz", tags=["meta"], summary="健康檢查")
def healthz():
    """用於監控或負載平衡器的健康檢查端點"""
    return {"status": "error 404"}

# @api.get("/All_Route", tags=["Client"], summary="所有路線")
# def All_Route():
#     rows = MySQL_Doing.run("SELECT * FROM bus_routes_total")

#     df_cols = MySQL_Doing.run("SHOW COLUMNS FROM bus_routes_total")
#     columns = df_cols["Field"].tolist()

#     df = pd.DataFrame(rows, columns=columns)

#     if "created_at" in df.columns:
#         df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce") \
#             .apply(lambda x: x.to_pydatetime() if pd.notnull(x) else None)

#     records = df.where(pd.notnull(df), None).to_dict(orient="records")
#     return records

@api.get("/Cache/Total_Route", tags=["Latest_Frontendonfor"], summary="Total_Route")
def get_cache_total_route():
    df = app.state.Total_Route
    return [] if df is None else df.to_dict(orient="records")


@api.get("/Cache/Schedule_Route", tags=["Latest_Frontendonfor"], summary="Schedule_Route")
def get_cache_schedule_route():
    df = app.state.Schedule_Route
    return [] if df is None else df.to_dict(orient="records")


@api.get("/Cache/Process_Route", tags=["Latest_Frontendonfor"], summary="Process_Route")
def get_cache_process_route():
    data = app.state.Process_Route
    if data is None:
        return {}

    output = {}
    for key, df in data.items():
        output[key] = df.to_dict(orient="records")
    return output

@api.post("/Route_Stations", tags=["Client"], summary="Latest_Frontendonfor",response_model=List[Define.StationOut])
def get_route_stations(q: Define.RouteStationsQuery):
    # === 建立查詢語句 ===
    sql = "SELECT * FROM bus_route_stations WHERE route_id = %s"
    params = [q.route_id]
    if q.direction:
        sql += " AND direction = %s"
        params.append(q.direction)

    # === 嘗試查詢資料 ===
    try:
        rows = MySQL_Doing.run(sql, params)
    except TypeError:
        # 某些自定義封裝不支援 %s 語法時 fallback
        if q.direction:
            rows = MySQL_Doing.run(
                f"SELECT * FROM bus_route_stations "
                f"WHERE route_id = {int(q.route_id)} AND direction = '{q.direction}'"
            )
        else:
            rows = MySQL_Doing.run(
                f"SELECT * FROM bus_route_stations WHERE route_id = {int(q.route_id)}"
            )

    # === 取出欄位結構 ===
    df_cols = MySQL_Doing.run("SHOW COLUMNS FROM bus_route_stations")
    if isinstance(df_cols, pd.DataFrame):
        columns = df_cols["Field"].tolist()
    elif isinstance(df_cols, list) and len(df_cols) > 0:
        if isinstance(df_cols[0], dict):
            columns = [c["Field"] for c in df_cols]
        else:
            columns = [c[0] for c in df_cols]
    else:
        columns = []

    # === 組成 DataFrame ===
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        return []

    # === 欄位對應與格式轉換 ===
    col_map = {
        "station_name": "stop_name",
        "stop_name": "stop_name",
        "est_time": "eta_from_start",
        "eta_from_start": "eta_from_start",
        "order_no": "stop_order",
        "seq": "stop_order",
        "schedule": "schedule",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # 數值轉換
    for col in ["latitude", "longitude", "eta_from_start", "stop_order"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 時間轉換
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce").apply(
            lambda x: x.to_pydatetime() if pd.notnull(x) else None
        )

    # === 保留需要的欄位 ===
    desired_cols = [
        "station_id",
        "route_id",
        "route_name",
        "direction",
        "stop_name",
        "latitude",
        "longitude",
        "eta_from_start",
        "stop_order",
        "schedule",
        "address",
        "status",
        "created_at",
    ]
    keep_cols = [c for c in desired_cols if c in df.columns]
    df = df[keep_cols]

    # === 轉換為 JSON 物件 ===
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    data: List[Define.StationOut] = [Define.StationOut(**r) for r in records]
    return data

@api.post("/update_vehicle_status", tags=["Latest_Frontendonfor"])
async def update_vehicle_status(

    route_no: int = Body(..., example=1),
    direction: str = Body(..., example="去程"),
    vehicle_status: str = Body(..., example="on_duty")

):
    # === 防呆 ===
    if vehicle_status not in ["on_duty", "rest"]:
        return {"ok": False, "message": "vehicle_status 必須是 on_duty 或 rest"}

    sql = f"""
        UPDATE route_schedule
        SET vehicle_status = '{vehicle_status}'
        WHERE route_no = {route_no}
          AND direction = '{direction}'
          AND operation_status = '正常營運'
    """

    try:
        MySQL_Doing.run(sql)
        return {
            "ok": True,
            "route_no": route_no,
            "direction": direction,
            "vehicle_status": vehicle_status,
            "message": "更新成功"
        }
    except Exception as e:
        return {"ok": False, "message": f"資料庫更新失敗: {e}"}

# @api.get("/Route_ScheduleTime", tags=["Client"], summary="取得路線時刻表（僅以頭尾站決定當前班次）")
# def get_route_schedule_time(route_id: int, direction: str = None):
    """
    只用「頭站與尾站」的時刻表決定當前班次索引 k：
      - 若 now <= head[k] 的第一個班次 → k 即為該索引
      - 若落在 (tail[k-1], tail[k]] 之間 → k
      - 若超過最後一個 tail → k = 最後一班
    接著每一站都取自己 full_schedule 的第 k 筆（若沒有第 k 筆就取最後一筆）。
    這樣所有站的時間屬於同一輪，不會倒退。
    """

    print("=== [DEBUG] /Route_ScheduleTime 開始 ===")
    print(f"[DEBUG] route_id={route_id}, direction={direction}")

    sql = f"""
    SELECT stop_name, schedule, 
            COALESCE(stop_order, 9999) AS ord
    FROM bus_route_stations
    WHERE route_id = {route_id} {f"AND direction='{direction}'" if direction else ""}
    """

    rows = MySQL_Doing.run(sql)
    df = pd.DataFrame(rows)
    print(f"[DEBUG] SQL 查得 {len(df)} 筆站點資料")

    if df.empty:
        print("[WARN] 查無站點資料")
        return {"status": "success", "route_id": route_id, "direction": direction, "data": []}

    df = df.sort_values("ord").reset_index(drop=True)

    # --- 工具：轉時間字串陣列 ---
    def parse_times(s: str):
        out = []
        if not s:
            print("[DEBUG] 空白 schedule 字串")
            return out

        s = str(s).strip()
        print(f"[DEBUG] 解析 schedule 原始字串: {s}")

        for t in s.split(","):
            t = t.strip()
            if not t:
                continue
            parsed = None
            try:
                parsed = datetime.strptime(t, "%H:%M").time()
            except ValueError:
                try:
                    parsed = datetime.strptime(t, "%H:%M:%S").time()
                except ValueError:
                    pass

            if parsed:
                out.append(parsed)
            else:
                print(f"[WARN] 無法解析時間片段: '{t}'")

        print(f"[DEBUG] 解析結果 => {out}")
        return out

    # --- 頭站與尾站 ---
    head_name = df.iloc[0]["stop_name"]
    tail_name = df.iloc[-1]["stop_name"]
    head_times = parse_times(df.iloc[0]["schedule"])
    tail_times = parse_times(df.iloc[-1]["schedule"])
    print(f"[DEBUG] 頭站={head_name} 共 {len(head_times)} 筆，尾站={tail_name} 共 {len(tail_times)} 筆")

    if not head_times or not tail_times:
        print("[WARN] 頭或尾站無時刻資料")
        data = [{
            "stop_name": r["stop_name"],
            "next_time": None,
            "full_schedule": (r["schedule"] or "").strip()
        } for _, r in df.iterrows()]
        return {"status": "success", "route_id": route_id, "direction": direction, "data": data}

    # --- 長度對齊 ---
    L = min(len(head_times), len(tail_times))
    head_times = head_times[:L]
    tail_times = tail_times[:L]

    now = datetime.now().time()
    print(f"[DEBUG] 現在時間={now}")

    # --- 決定班次索引 ---
    def locate_cycle_index(now_t):
        for i, ht in enumerate(head_times):
            if now_t <= ht:
                print(f"[DEBUG] 命中 head[{i}] = {ht}")
                return i
        for i, tt in enumerate(tail_times):
            if now_t <= tt:
                print(f"[DEBUG] 命中 tail[{i}] = {tt}")
                return i
        print("[DEBUG] 超過最後班次，取最後一班")
        return L - 1

    k = locate_cycle_index(now)
    print(f"[DEBUG] 決定使用第 {k} 班")

    # --- 各站取第 k 筆 ---
    results = []
    for _, r in df.iterrows():
        full = (r["schedule"] or "").strip()
        times = parse_times(full)
        if not times:
            print(f"[WARN] 站點 {r['stop_name']} 無有效時刻")
            results.append({"stop_name": r["stop_name"], "next_time": None, "full_schedule": full})
            continue

        idx = min(k, len(times) - 1)
        next_time = times[idx]
        print(f"[DEBUG] 站點 {r['stop_name']} 使用索引 {idx} => {next_time}")
        results.append({
            "stop_name": r["stop_name"],
            "next_time": next_time.strftime("%H:%M"),
            "full_schedule": full
        })

    print(f"[DEBUG] 共產出 {len(results)} 筆時刻資料")
    print("=== [DEBUG] /Route_ScheduleTime 結束 ===")

    return {
        "status": "success",
        "route_id": route_id,
        "direction": direction,
        "data": results
    }

@api.get("/yo_hualien", tags=["Client"], summary="行動遊花蓮")
def yo_hualien():
    rows = MySQL_Doing.run("SELECT station_name, address, latitude, longitude FROM action_tour_hualien")
    columns = ["station_name", "address", "latitude", "longitude"]
    df = pd.DataFrame(rows, columns=columns)
    return df.to_dict(orient="records") 

# @api.get("/GIS_About", tags=["Client"], summary="取得最新車輛資訊")
# def Get_GIS_About():
#     Results = MySQL_Doing.run("""
#     Select route from car_resource
#     where route != 'None'
#     """)

#     # print(Results["route"].tolist())
#     Results = MySQL_Doing.run("""
#     SELECT c.route, c.X, c.Y, c.direction, c.Current_Location
#     FROM car_backup c
#     JOIN (
#         SELECT route, MAX(seq) AS max_seq
#         FROM car_backup
#         WHERE route IN ('1', '2', '3')
#         GROUP BY route
#     ) t ON c.route = t.route AND c.seq = t.max_seq;
#     """)
#     return Results

# @api.get("/GIS_AllFast", tags=["Client"], summary="今日正常營運路線即時摘要（30秒快取）")
# def gis_all_fast():
#     # print("=== [DEBUG] /GIS_AllFast 開始 ===")

#     # 1️⃣ 抓取今日正常營運車輛
#     df_routes = pd.DataFrame(MySQL_Doing.run('''
#         SELECT route_no, direction, license_plate 
#         FROM route_schedule 
#         WHERE operation_status = "正常營運"
#     '''))
#     if df_routes.empty:
#         print("[WARN] 無正常營運路線")
#         return {}

#     df_routes["direction"] = df_routes["direction"].map(normalize_direction)
#     # print(f"[DEBUG] 讀取 route_schedule 共 {len(df_routes)} 筆")

#     # 2️⃣ 讀取所有站點
#     df_stops = pd.DataFrame(MySQL_Doing.run('''
#         SELECT route_id, direction, latitude, longitude, stop_name 
#         FROM bus_route_stations
#     '''))
#     df_stops["direction"] = df_stops["direction"].map(normalize_direction)
#     # print(f"[DEBUG] 讀取 bus_route_stations 共 {len(df_stops)} 筆")

#     results = []

#     # 3️⃣ 每台車找最近站點
#     for _, r in df_routes.iterrows():
#         route_id = int(r["route_no"])
#         plate = str(r["license_plate"])
#         direction = r["direction"]

#         # print(f"\n[DEBUG] 處理路線 {route_id}, 車牌 {plate}, 方向 {direction}")

#         # --- 抓車機資料 ---
#         sql = f'''
#             SELECT 
#                 X AS longitude,
#                 Y AS latitude
#             FROM ttcarimport 
#             WHERE car_licence = "{plate}" 
#             ORDER BY seq DESC 
#             LIMIT 1
#         '''
#         df_car = pd.DataFrame(MySQL_Doing.run(sql))
#         # print(f"[DEBUG] 車牌 {plate} GPS 筆數: {len(df_car)}")

#         if df_car.empty:
#             print(f"[WARN] 車牌 {plate} 無最新位置，略過")
#             continue

#         # --- 經緯度轉換 + 檢查 ---
#         try:
#             car_lat = float(df_car.iloc[0]["latitude"])   # 緯度（應約23.x）
#             car_lon = float(df_car.iloc[0]["longitude"])  # 經度（應約121.x）
#         except Exception as e:
#             print(f"[ERROR] 無法轉換經緯度 ({plate}): {e}")
#             continue

#         # 自動偵測經緯度是否顛倒
#         if abs(car_lat) > 90 or abs(car_lon) > 180:
#             print(f"[WARN] 座標顛倒 lat={car_lat}, lon={car_lon} → 交換")
#             car_lat, car_lon = car_lon, car_lat

#         # 粗略檢查是否在台灣範圍內
#         if not (21.5 <= car_lat <= 25.5 and 119.0 <= car_lon <= 123.0):
#             print(f"[WARN] 座標異常 lat={car_lat}, lon={car_lon}")

#         # print(f"[DEBUG] 正常化後座標: lat={car_lat}, lon={car_lon}")

#         # --- 尋找相同路線、方向的站 ---
#         df_route_stops = df_stops.loc[
#             (df_stops["route_id"] == route_id) &
#             (df_stops["direction"] == direction)
#         ].copy()

#         # print(f"[DEBUG] 匹配站點數: {len(df_route_stops)}")
#         if df_route_stops.empty:
#             print(f"[WARN] 路線 {route_id} ({direction}) 無對應站點")
#             continue

#         # --- 計算距離 ---
#         try:
#             df_route_stops.loc[:, "distance_m"] = df_route_stops.apply(
#                 lambda s: haversine(car_lat, car_lon, float(s["latitude"]), float(s["longitude"])),
#                 axis=1
#             )
#         except Exception as e:
#             print(f"[ERROR] 計算距離失敗: {e}")
#             continue

#         nearest_idx = df_route_stops["distance_m"].idxmin()
#         nearest = df_route_stops.loc[nearest_idx]
#         # print(f"[DEBUG] 最接近站點: {nearest['stop_name']} (距離 {nearest['distance_m']:.2f} 公尺)")

#         # --- 輸出 ---
#         results.append({
#             "route": route_id,
#             "X": car_lon,      # 經度
#             "Y": car_lat,      # 緯度
#             "direction": direction,
#             "Current_Location": nearest["stop_name"]
#         })

#     # print(f"\n[DEBUG] 結果共 {len(results)} 筆")
#     # for i, r in enumerate(results):
#         # print(f"  [{i}] route={r['route']}, dir={r['direction']}, stop={r['Current_Location']}")

#     # print("=== [DEBUG] /GIS_AllFast 結束 ===\n")

#     return pd.DataFrame(results).to_dict()

@api.post("/reservation", tags=["Client"], summary="送出預約")
def push_reservation(req: Define.ReservationReq):
    # 產生一個安全的外部訂單代碼，例如 HBus-8位隨機碼
    booking_code = f"HBus-{uuid.uuid4().hex[:8].upper()}"

    sql = f"""
    INSERT INTO reservation (
        user_id, booking_time, booking_number, 
        booking_start_station_name, booking_end_station_name,
        booking_code
    ) VALUES (
        '{req.user_id}',
        '{req.booking_time}',
        '{req.booking_number}',
        '{req.booking_start_station_name}',
        '{req.booking_end_station_name}',
        '{booking_code}'
    );
    """

    MySQL_Doing.run(sql)

    return {
        "status": "success",
        "reservation_code": booking_code
    }

@api.get("/reservations/my", tags=["Client"], summary="預約查詢")
def show_reservations(user_id: str):
    sql = f"""
    SELECT reservation_id, user_id, booking_time, booking_number, 
           booking_start_station_name, booking_end_station_name,
           review_status, payment_status, dispatch_status
    FROM reservation
    WHERE user_id = '{user_id}'
      AND (review_status IS NULL OR review_status <> 'canceled')
    ORDER BY booking_time DESC
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
    # print("查詢明日預約 user_id=", user_id)
    # print("SQL=", sql)
    results = MySQL_Doing.run(sql)

    return {"status": "success", "sql": results}

@api.post("/reservations/refunded", tags=["Client"], summary="退款")
def Cancled_reservation(req: Define.CancelReq):
    sql = f"""
        UPDATE reservation
        SET payment_status = 'refunded'
        WHERE reservation_id = {int(req.reservation_id)};
    """
    try:
        MySQL_Doing.run(sql)
        return {"status": "success", "reservation_id": req.reservation_id, "payment_status": "refunded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"退款失敗: {e}")

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

@api.get("/privacy", tags=["Client"], summary="privacy")
async def get_privacy():
    gist_url = "https://gist.githubusercontent.com/Cody20179/ef17eeb9e2880a3a677bb5c74232c003/raw/gistfile1.txt"
    resp = requests.get(gist_url)
    return {"content": resp.text}

@api.get("/reserve", tags=["Client"], summary="reserve")
async def get_reserve():
    text = (
        "購票及退款說明\n"
        "一、預約方式與流程\n"
        "1.預約截止時間：\n"
        "乘客最晚須於搭車日前一日 15:00 前完成線上預約。\n"
        "2.預約審核與通知：\n"
        "本公司將於收到預約後進行調度審核。\n"
        "若可提供服務，將以本系統通知乘客進入付款流程。\n"
        "本公司保留因車輛調度、路況或人力限制而無法受理預約之權利。\n"
        "3.付款與派車：\n"
        "乘客須於收到通知後依指示完成線上付款。\n"
        "付款完成後即視為訂位成功，本公司將安排派車。\n"
        "若乘客未於搭車前一日完成付款，視同放棄預約，將不予保留名額。\n"
        "二、乘車須知\n"
        "請於預約時間提前 5 分鐘 在指定上車地點等待。\n"
        "司機將核對人數及訂單編號後提供服務。\n"
        "逾時未到者視為放棄乘車，票款不予退還。\n"
        "三、退票及退款規定\n"
        "1. 乘客申請退票\n"
        "申請時點退款規定\n"
        "搭車當日不受理退票、退款作業\n"
        "2. 以下情形不予退款\n"
        "搭車當日未出現或逾時未到者。\n"
        "乘客個人因素無法搭乘、臨時取消。\n"
        "乘客未於指定時間完成付款導致預約失效（此狀況不會扣款）。\n"
        "3. 因本公司因素之退款\n"
        "若因以下原因導致無法提供服務，將退還全額（含金流費用）：\n"
        "車輛故障或調度異常。\n"
        "天候、道路封閉或不可抗力事件。\n"
        "本公司取消該趟服務。\n"
        "退款將於 3–14 個工作天內（依金流業者規範）退回原付款方式。\n"
        "四、預約變更\n"
        "前一日後恕不受理更改，需重新預約。\n"
        "所有變更需透過線上平台或客服管道提出。"
    )
    return {"content": text}

# @api.post("/car_backup_insert", tags=["Car"], summary="插入車輛備份資料")
# def insert_car_backup(data: Define.CarBackupInsert):

#     # 若未提供 rcv_dt，使用伺服器當前時間
#     rcv_dt = data.rcv_dt or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#     acc_value = "b'1'" if data.acc else "b'0'" if data.acc is not None else "NULL"

#     sql = f"""
#     INSERT INTO car_backup (
#         rcv_dt, car_licence, Gpstime, X, Y, Speed, Deg, acc, route, direction, Current_Location
#     ) VALUES (
#         '{rcv_dt}', '{data.car_licence}', '{data.Gpstime}',
#         {data.X}, {data.Y}, {data.Speed}, {data.Deg},
#         {acc_value},
#         {f"'{data.route}'" if data.route else "NULL"},
#         {f"'{data.direction}'" if data.direction else "NULL"},
#         {f"'{data.Current_Location}'" if data.Current_Location else "NULL"}
#     );
#     """

#     try:
#         MySQL_Doing.run(sql)
#         return {"status": "success", "rcv_dt": rcv_dt, "sql": sql}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


#     qr_text = str(data.get("qrcode", "")).strip()
#     if not qr_text:
#         raise HTTPException(status_code=400, detail="Empty QRCode")

#     try:
#         # 嘗試解密
#         decrypted = decrypt_aes(qr_text, KEY, IV)
#         obj = json.loads(decrypted)

#         rid = obj.get("reservation_id")
#         uid = obj.get("user_id")
#         lid = obj.get("line_id")

#         if not rid or not uid:
#             raise HTTPException(status_code=400, detail="Missing fields")

#         return {"status": "success", "data": obj}

#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"QRCode decrypt failed: {e}")

@api.post("/car_insert", tags=["Car"], summary="插入車輛即時定位資料")
def insert_car(data: Define.CarInsertRequest):
    rcv_dt = data.rcv_dt or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sql = f"""
    INSERT INTO ttcarimport (rcv_dt, car_licence, Gpstime, X, Y, Speed, Deg, acc)
    VALUES (
        '{rcv_dt}',
        '{data.car_licence}',
        '{data.Gpstime}',
        {data.X},
        {data.Y},
        {data.Speed},
        {data.Deg},
        {1 if str(data.acc) in ["1", "true", "True"] else 0}
    );
    """

    MySQL_Doing.run(sql)
    
    return {"status": "success", "message": "資料已插入"}

@api.get("/announcements", tags=["Client"], summary="取得服務公告列表")
def get_announcements():
    sql = "SELECT id, title, content, created_at FROM announcements ORDER BY created_at DESC"
    rows = MySQL_Doing.run(sql)
    if hasattr(rows, "to_dict"):
        return {"status": "success", "data": rows.to_dict(orient="records")}
    return {"status": "success", "data": rows}

@api.post("/announcements/add", tags=["Admin"], summary="新增服務公告")
def add_announcement(title: str = Body(...), content: str = Body(...)):
    sql = f"""
    INSERT INTO announcements (title, content)
    VALUES ('{title}', '{content}');
    """
    MySQL_Doing.run(sql)
    return {"status": "success"}

@api.delete("/announcements/delete/{ann_id}", tags=["Admin"], summary="刪除公告")
def delete_announcement(ann_id: int):
    sql = f"DELETE FROM announcements WHERE id = {ann_id}"
    MySQL_Doing.run(sql)
    return {"status": "success"}

@api.get("/Generate_QRCode", tags=["Utility"], summary="產生路線站點 QRCode 並下載")
def generate_qr_code(
    base_url: str,
    route_id: int,
    stop_count: int,
):
    """
    依據路線 ID 與站點數產生 QR Code 圖片壓縮包，並提供下載。
    - base_url: 前端或公開網址 (例如 https://xxx.ngrok-free.app)
    - route_id: 路線 ID
    - stop_count: 站點數量
    """
    try:
        # 建立暫存目錄
        temp_dir = tempfile.mkdtemp(prefix="qrcodes_")
        for stop_order in range(1, stop_count + 1):
            url = f"{base_url}/routes/{route_id}/stop/{stop_order}"
            img = qrcode.make(url)
            img.save(os.path.join(temp_dir, f"route{route_id}_stop{stop_order}.png"))

        # 壓縮成 zip 方便下載
        zip_path = os.path.join(temp_dir, f"route{route_id}_qrcodes.zip")
        import zipfile
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(temp_dir):
                if fname.endswith(".png"):
                    zf.write(os.path.join(temp_dir, fname), arcname=fname)

        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"route{route_id}_qrcodes.zip",
        )

    except Exception as e:
        return {"status": "error", "message": str(e)}
    # === 路線排班相關操作 ===

@api.get("/route_schedule", tags=["Admin"], summary="取得所有排班")
def get_route_schedule():
    sql = """
    SELECT id, route_no, direction, special_type, operation_status,
           date, departure_time, license_plate, driver_name, employee_id
    FROM route_schedule
    ORDER BY route_no ASC, departure_time ASC
    """
    rows = MySQL_Doing.run(sql)
    if hasattr(rows, "to_dict"):
        return {"status": "success", "data": rows.to_dict(orient="records")}
    return {"status": "success", "data": rows}

@api.post("/route_schedule/add", tags=["Admin"], summary="新增排班")
def add_route_schedule(data: dict = Body(...)):
    sql = f"""
    INSERT INTO route_schedule
      (route_no, direction, special_type, operation_status, date, departure_time, license_plate, driver_name, employee_id)
    VALUES
      ('{data.get("route_no")}', '{data.get("direction")}', {f"'{data.get('special_type')}'" if data.get("special_type") else "NULL"},
       '{data.get("operation_status", "正常營運")}', '{data.get("date")}', '{data.get("departure_time")}',
       '{data.get("license_plate")}', '{data.get("driver_name")}', '{data.get("employee_id")}')
    """
    MySQL_Doing.run(sql)
    return {"status": "success", "message": "新增成功"}

@api.put("/route_schedule/update/{id}", tags=["Admin"], summary="更新排班")
def update_route_schedule(id: int, data: dict = Body(...)):
    sql = f"""
    UPDATE route_schedule SET
        route_no = '{data.get("route_no")}',
        direction = '{data.get("direction")}',
        special_type = {f"'{data.get('special_type')}'" if data.get("special_type") else "NULL"},
        operation_status = '{data.get("operation_status", "正常營運")}',
        date = '{data.get("date")}',
        departure_time = '{data.get("departure_time")}',
        license_plate = '{data.get("license_plate")}',
        driver_name = '{data.get("driver_name")}',
        employee_id = '{data.get("employee_id")}'
    WHERE id = {id}
    """
    MySQL_Doing.run(sql)
    return {"status": "success", "message": f"排班 {id} 更新成功"}

@api.delete("/route_schedule/delete/{id}", tags=["Admin"], summary="刪除排班")
def delete_route_schedule(id: int):
    sql = f"DELETE FROM route_schedule WHERE id = {id}"
    MySQL_Doing.run(sql)
    return {"status": "success", "message": f"排班 {id} 已刪除"}

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
            # print(f"[WARN] Redis 有 session，但 MySQL 查不到 user={uid}，強制重登")
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
    # print(f"[DEBUG] LINE Profile: {profile}")
    # print(f"[DEBUG] LineID={LineID}, UserName={UserName}, AppToken={app_token}")
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
            # print(f"[CLEANUP] 清掉無效 session: user={uid}")
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

@api.get("/boarding_qr/{reservation_id}", tags=["Client"], summary="產生乘車用 QRCode（PNG）")
def create_boarding_qr(reservation_id: int, download: bool = False):
    """
    依據 reservation_id 產生乘車 QR 圖片。
    - 驗證付款與審核狀態
    - 回傳 PNG 檔（或提供下載）
    """
    try:
        token = generate_boarding_token(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"產生失敗: {e}")

    import tempfile, os
    temp_dir = tempfile.mkdtemp(prefix="boarding_")
    img_path = os.path.join(temp_dir, f"boarding_{reservation_id}.png")
    save_qr_png(token, img_path)

    if download:
        # 讓用戶直接下載
        return FileResponse(
            img_path,
            media_type="image/png",
            filename=f"boarding_{reservation_id}.png"
        )
    else:
        # 預設直接串流圖片
        buf = BytesIO()
        img = qrcode.make(token)
        img.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")

@api.post("/boarding_qr/verify", tags=["Client"], summary="驗證乘車 QRCode")
def verify_boarding_qr(data: Define.BoardingQRVerifyRequest):
    token = data.qrcode.strip()
    if not token:
        raise HTTPException(status_code=400, detail="缺少 qrcode")

    result = verify_boarding_token(token)
    if not result.get("ok"):
        print("[DEBUG] verify_boarding_token 驗證失敗:", result)
        return {"status": "error", "reason": result.get("reason")}

    reservation_id = result.get("reservation_id") or result.get("data", {}).get("reservation_id")
    if not reservation_id:
        raise HTTPException(status_code=400, detail="找不到 reservation_id")

    try:
        sql = f"SELECT * FROM reservation WHERE reservation_id = {int(reservation_id)};"
        df = MySQL_Doing.run(sql)
        if df.empty:
            raise HTTPException(status_code=404, detail="查無此預約")

        row = df.iloc[0].to_dict()
        payment_status = row.get("payment_status")
        review_status = row.get("review_status")
        dispatch_status = row.get("dispatch_status")
        user_id = row.get("user_id")

        print(f"[DEBUG] reservation 狀態: payment={payment_status}, review={review_status}, dispatch={dispatch_status}, user_id={user_id}")

        # === [新增] 檢查是否已上車 ===
        if dispatch_status == "assigned":
            return {
                "status": "error",
                "reason": "重複上車（此乘客已驗證過）",
                "reservation_id": reservation_id
            }

        # === 檢查是否具乘車資格 ===
        if payment_status != "paid" or review_status != "approved":
            return {
                "status": "error",
                "reason": f"乘車資格不符（付款:{payment_status}, 審核:{review_status}）",
                "reservation_id": reservation_id
            }

        # --- 查使用者資訊 ---
        user_info = {}
        if user_id:
            user_sql = f"SELECT user_id, username, email, phone FROM users WHERE user_id = {int(user_id)};"
            user_df = MySQL_Doing.run(user_sql)
            if not user_df.empty:
                user_info = user_df.iloc[0].to_dict()
                print(f"[DEBUG] 乘客資訊: {user_info}")

        # --- 更新 dispatch_status ---
        update_sql = f"""
            UPDATE reservation
            SET dispatch_status = 'assigned', updated_at = NOW()
            WHERE reservation_id = {int(reservation_id)};
        """
        MySQL_Doing.run(update_sql)
        print("[DEBUG] dispatch_status 已更新為 assigned")

        return {
            "status": "success",
            "reservation_id": reservation_id,
            "user": user_info,
            "reservation_status": {
                "payment_status": payment_status,
                "review_status": review_status,
                "dispatch_status": "assigned"
            }
        }

    except Exception as e:
        print(f"[ERROR] 驗證乘車資格時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"系統錯誤: {e}")

# ====================================
# 🔁 雷門 callback（伺服器對伺服器）
# ====================================

@app.post("/payments", response_model=Define.CreatePaymentOut)
def create_payment(body: Define.CreatePaymentIn):
    import random
    amt = Decimal(body.amount)
    if amt <= 0 or amt != amt.quantize(Decimal("1")):
        raise HTTPException(status_code=400, detail="amount 必須為正整數")

    reservation_id = body.order_number  # 前端送進來的就是 reservation_id
    random_code = str(random.randint(10**4, 10**5 - 1))  # 5 位隨機數
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")  # 日期時間
    pos_order_number = f"{STORE_CODE}{random_code}{timestamp}"
    # pos_order_number = str(random.randint(10**10, 10**11 - 1))  # 11 位亂數，保證每次不同
    payload = {
        "set_price": str(amt),
        "pos_id": "01",
        "pos_order_number": pos_order_number,  # ← 照規格用亂數，不動加密欄位
        "callback_url": f"{PUBLIC_BASE}/callback",
        "return_url": f"{PUBLIC_BASE}/return",
        "nonce": secrets.token_hex(8),
    }

    # 存 Redis 映射，建議 TTL 例如 3 天 (259200 秒)
    r.setex(f"paymap:{pos_order_number}", 259200, str(reservation_id))

    # === AES 加密 & Hash（保持原規格，不要改）===
    transaction_data = encrypt_aes(payload)  # ← 你的現有實作 :contentReference[oaicite:3]{index=3}
    hash_digest = hashlib.sha256(transaction_data.encode("utf-8")).hexdigest()

    full_url = (
        f"https://{LAYMON}/calc/pay_encrypt/{STORE_CODE}"
        f"?TransactionData={quote(transaction_data)}&HashDigest={hash_digest}"
    )

    return Define.CreatePaymentOut(pay_url=full_url, reservation_id=str(reservation_id))

@app.post("/callback")
async def callback(request: Request):
    body = await request.json()
    # print(body)
    enc_data = body.get("TransactionData")
    hash_digest = body.get("HashDigest")

    if not enc_data or not hash_digest:
        raise HTTPException(status_code=400, detail="缺少必要欄位")

    # 驗證 hash
    local_hash = hashlib.sha256(enc_data.encode("utf-8")).hexdigest()
    if local_hash != hash_digest:
        raise HTTPException(status_code=400, detail="Hash 驗證失敗")

    try:
        KEY_bits = bytes.fromhex(f"{KEY_HEX}")  # 32 bytes
        IV_bits  = bytes.fromhex(f"{IV_HEX}")  # 16 bytes

        # KEY_bits = ''.join(format(b, '08b') for b in KEY.encode())
        # IV_bits = ''.join(format(b, '08b') for b in IV.encode())
        data = decrypt_aes(enc_data,key = KEY_bits, iv = IV_bits) # THere

        # 實體 log 紀錄
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[金流 /callback] [{timestamp}] Decrypted Data: {data}\n"
        
        try:
            # 使用 'a' 模式 (append) 附加內容到檔案
            with open("callback_decrypted_log.txt", "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as file_e:
            # 即使寫檔失敗，也不影響金流流程，僅印出警告
            print(f"[WARN] 寫入解密資料日誌失敗: {file_e}")
        # 實體 log 紀錄

        data = json.loads(data)
        return_code = data.get("return_code")
        transaction_status = data.get("status")
        order_number = data.get("pos_order_number")
        reservation_id = r.get(f"paymap:{order_number}")

        is_success = (return_code == "0000" and transaction_status == 2)

        if order_number and is_success:
            sql = f"UPDATE reservation SET payment_status = 'paid' WHERE reservation_id = '{reservation_id}'"
            print(sql)
            MySQL_Doing.run(sql)

        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解密失敗: {e}")

# ====================================
# 🌐 使用者導回頁
# ====================================
@app.get("/return")
def return_page():
    return RedirectResponse(url=f"{PUBLIC_BASE}?tab=reservations")

# ====================================
# 新增：今日正常營運路線的即時摘要（30秒快取）
# ====================================
_GIS_ALL_CACHE = {"ts": 0.0, "data": None}
_GIS_ALL_TTL = 30  # seconds
_GIS_ALL_LOCK = RLock()

app.include_router(api)
app.mount('/', StaticFiles(directory='dist', html=True), name='client')

@app.exception_handler(StarletteHTTPException)
async def spa_fallback(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):  #AAA
        return await http_exception_handler(request, exc)  # 讓 FastAPI 自己處理 Basic Auth
    try:
        if exc.status_code == 404 and request.method in ("GET", "HEAD"):
            path = request.url.path or "/"
            accept = (request.headers.get("accept") or "").lower()
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

"""
docker compose down
docker compose build
docker compose up -d
"""