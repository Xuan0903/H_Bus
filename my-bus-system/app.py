from fastapi import FastAPI, HTTPException, Depends, Query, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, Boolean, ForeignKey, text, func, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel,Field
from pathlib import Path
from typing import Optional, Literal, List, Tuple, Dict, Set
import bcrypt, os
from dotenv import load_dotenv
from collections import defaultdict
from calendar import monthrange
from datetime import datetime, timezone, timedelta, date, time
import pytz
from MySQL import MySQL_Run
import pandas as pd
import hashlib
import xml.etree.ElementTree as ET
try:
    import redis  # redis-py
except Exception:  # pragma: no cover
    redis = None

# 設定台北時區
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

def get_taipei_time():
    """取得台北時間"""
    return datetime.now(TAIPEI_TZ)

def get_taiwan_datetime():
    """取得台灣時間的 datetime 物件（無時區資訊，供資料庫使用）"""
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)

# ===== 預約分析共用工具 =====
RESERVATION_STATUS_PRIORITY = [
    "pending",
    "approved",
    "assigned",
    "in_progress",
    "completed",
    "canceled",
    "rejected",
    "failed",
]

REVIEW_STATUS_PRIORITY = [
    "pending",
    "approved",
    "rejected",
    "canceled",
]

def _add_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _month_last_day(value: date) -> date:
    return date(value.year, value.month, monthrange(value.year, value.month)[1])


def _parse_month_string(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except Exception:
        raise HTTPException(status_code=400, detail="月份格式需為 YYYY-MM")


def _normalize_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(TAIPEI_TZ).replace(tzinfo=None)
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _generate_week_ranges(target_year: int, target_month: int) -> List[Dict[str, date]]:
    last_day = monthrange(target_year, target_month)[1]
    ranges: List[Dict[str, date]] = []
    day = 1
    week_index = 1
    while day <= last_day:
        start_date = date(target_year, target_month, day)
        end_day = min(day + 6, last_day)
        end_date = date(target_year, target_month, end_day)
        ranges.append({
            "week": week_index,
            "start": start_date,
            "end": end_date,
            "label": f"{start_date.month}/{start_date.day}-{end_date.month}/{end_date.day}",
        })
        day += 7
        week_index += 1
    return ranges


def _normalize_status(value, fallback: str = 'unknown') -> str:
    if value is None:
        return fallback
    value_str = str(value).strip()
    if not value_str:
        return fallback
    lower = value_str.lower()
    if lower in {'', 'none', 'null'}:
        return fallback
    return lower


def _sort_status_keys(keys: Set[str], priority: List[str]) -> List[str]:
    if not keys:
        return []
    working = set(keys)
    unknown_present = 'unknown' in working
    if unknown_present:
        working.remove('unknown')
    ordered = [item for item in priority if item in working]
    remainder = sorted(working - set(ordered))
    result = ordered + remainder
    if unknown_present:
        result.append('unknown')
    return result


def _fetch_reservations_in_range(start_dt: datetime, end_dt: datetime):
    sql = """
        SELECT
            COALESCE(created_at, booking_time) AS event_time,
            reservation_status,
            review_status
        FROM reservation
        WHERE (
            (created_at IS NOT NULL AND created_at >= %s AND created_at < %s)
            OR (created_at IS NULL AND booking_time IS NOT NULL AND booking_time >= %s AND booking_time < %s)
        )
    """
    return MySQL_Run(sql, (start_dt, end_dt, start_dt, end_dt)) or []


def _ensure_datetime_window(start: date, end: date) -> Tuple[datetime, datetime]:
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
    return start_dt, end_dt

# 載入環境變數
load_dotenv()

# MySQL 資料庫設定
DATABASE_URL = f"mysql+pymysql://root:109109@192.168.0.126:3307/bus_system"
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DB_HOST = os.getenv("MYSQL_HOST", "localhost")
DB_PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DATABASE", "bus_system")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 資料庫模型（匹配實際表結構）
class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(String(100), unique=True)
    username = Column(String(100))
    password = Column(String(255))  # 雜湊密碼
    email = Column(String(255))
    phone = Column(String(20))
    # 使用台灣時間（無時區資訊）以確保與需求一致
    created_at = Column(TIMESTAMP, default=get_taiwan_datetime)
    updated_at = Column(TIMESTAMP, default=get_taiwan_datetime, onupdate=get_taiwan_datetime)
    last_login = Column(TIMESTAMP, nullable=True)
    status = Column(Enum('active', 'inactive'), default='active')
    # 與資料庫一致，並兼容歷史資料 'None'
    reservation_status = Column(
        Enum('no_reservation', 'pending', 'approved', 'rejected', 'completed', 'None'),
        default='no_reservation'
    )  # 預約狀態
    preferences = Column(String)  # TEXT in MySQL
    privacy_settings = Column(String)  # TEXT in MySQL

class AdminUser(Base):
    __tablename__ = "admin_users"
    admin_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("admin_roles.role_id"))
    last_login = Column(TIMESTAMP, nullable=True)
    login_attempts = Column(Integer, default=0)
    status = Column(Enum('active', 'inactive'), default='active')
    created_by = Column(Integer, ForeignKey("admin_users.admin_id"))
    created_at = Column(TIMESTAMP, default=get_taiwan_datetime)
    updated_at = Column(TIMESTAMP, default=get_taiwan_datetime, onupdate=get_taiwan_datetime)

class AdminRole(Base):
    __tablename__ = "admin_roles"
    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(100), unique=True, nullable=False)
    role_description = Column(String)  # TEXT in MySQL
    permissions = Column(String)  # TEXT in MySQL
    is_system_role = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())

class InMemoryRedis:
    """極簡 In-Memory Redis 替代品（僅供開發測試）。
    支援本檔案用到的方法：get, setex, delete, incr, expire, ttl, ping, set
    注意：非多進程安全，不適合正式環境。
    """
    def __init__(self):
        import time
        self._now = time
        self._store = {}  # key -> (value:str, expire_at:float|None)

    def _expired(self, key):
        v = self._store.get(key)
        if not v:
            return True
        _, exp = v
        if exp is None:
            return False
        if self._now.time() >= exp:
            self._store.pop(key, None)
            return True
        return False

    def ping(self):
        return True

    def get(self, key):
        if self._expired(key):
            return None
        return self._store.get(key, (None, None))[0]

    def set(self, key, value):
        self._store[key] = (str(value), None)
        return True

    def setex(self, key, ttl, value):
        self._store[key] = (str(value), self._now.time() + int(ttl))
        return True

    def delete(self, *keys):
        c = 0
        for k in keys:
            if k in self._store:
                self._store.pop(k, None)
                c += 1
        return c

    def incr(self, key):
        if self._expired(key):
            self._store.pop(key, None)
        val, exp = self._store.get(key, ("0", None))
        try:
            n = int(val) + 1
        except Exception:
            n = 1
        self._store[key] = (str(n), exp)
        return n

    def expire(self, key, ttl):
        if key in self._store:
            v, _ = self._store[key]
            self._store[key] = (v, self._now.time() + int(ttl))
            return True
        return False

    def ttl(self, key):
        if key not in self._store:
            return -2  # Redis: key 不存在
        v, exp = self._store[key]
        if exp is None:
            return -1  # 沒有 TTL
        remain = int(round(exp - self._now.time()))
        if remain <= 0:
            self._store.pop(key, None)
            return -2
        return remain

# Pydantic 模型（更新以匹配表結構）
class UserCreate(BaseModel):
    line_id: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # 明文密碼，會在API中雜湊
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = 'active'
    reservation_status: Optional[Literal["no_reservation", "pending", "approved", "rejected", "completed"]] = 'no_reservation'
    preferences: Optional[str] = None
    privacy_settings: Optional[str] = None

class UserUpdate(BaseModel):
    line_id: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # 明文密碼，會在API中雜湊
    email: Optional[str] = None
    phone: Optional[str] = None
    last_login: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None
    reservation_status: Optional[Literal["no_reservation", "pending", "approved", "rejected", "completed"]] = None
    preferences: Optional[str] = None
    privacy_settings: Optional[str] = None

class AdminUserCreate(BaseModel):
    username: str
    password: str
    role_id: Optional[int] = None
    status: Optional[str] = 'active'
    created_by: Optional[int] = None

class AdminUserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role_id: Optional[int] = None
    last_login: Optional[str] = None
    login_attempts: Optional[int] = None
    status: Optional[str] = None
    created_by: Optional[int] = None

class AdminRoleCreate(BaseModel):
    role_name: str
    role_description: Optional[str] = None
    permissions: Optional[str] = None
    is_system_role: Optional[bool] = False

class AdminRoleUpdate(BaseModel):
    role_name: Optional[str] = None
    role_description: Optional[str] = None
    permissions: Optional[str] = None
    is_system_role: Optional[bool] = None

class OTPRequest(BaseModel):
    account: str
    purpose: Optional[str] = "login"  # login | signup | reset
    channel: Optional[str] = None      # email | sms | null

class OTPVerify(BaseModel):
    account: str
    code: str
    purpose: Optional[str] = "login"

class LoginRequest(BaseModel):
    username: str
    password: str

class Route(BaseModel):
    route_id: int
    route_name: str
    stop_count: int
    direction: Literal["單向", "雙向"]
    start_stop: Optional[str] = None
    end_stop: Optional[str] = None
    status: int
    created_at: Optional[datetime] = None

# ====== 請求模型 ======
class RouteStationsQuery(BaseModel):
    route_id: int = Field(..., ge=1)
    # 可選：若你要過濾去/回/單程
    direction: Optional[Literal["去程", "回程", "單程"]] = None

# ====== 回應模型（對齊你實際的欄位）======
class StationOut(BaseModel):
    route_id: int
    route_name: str
    direction: Optional[str] = None
    stop_name: str
    latitude: float
    longitude: float
    eta_from_start: Optional[int] = None  # 分鐘(或秒) 看你DB定義
    stop_order: Optional[int] = None
    created_at: Optional[datetime] = None

# ====== Reservation 模型 ======
class ReservationCreate(BaseModel):
    user_id: Optional[int] = None
    booking_time: Optional[datetime] = None
    booking_number: Optional[int] = None
    booking_start_station_name: Optional[str] = None
    booking_end_station_name: Optional[str] = None
    payment_method: Optional[str] = None
    payment_record: Optional[str] = None
    payment_status: Optional[Literal['pending','paid','failed','refunded']] = 'pending'
    review_status: Optional[Literal['pending','approved','rejected','canceled']] = 'pending'
    dispatch_status: Optional[Literal['not_assigned','assigned']] = 'not_assigned'

class ReservationUpdate(BaseModel):
    user_id: Optional[int] = None
    booking_time: Optional[datetime] = None
    booking_number: Optional[int] = None
    booking_start_station_name: Optional[str] = None
    booking_end_station_name: Optional[str] = None
    payment_method: Optional[str] = None
    payment_record: Optional[str] = None
    payment_status: Optional[Literal['pending','paid','failed','refunded']] = None
    review_status: Optional[Literal['pending','approved','rejected','canceled']] = None
    dispatch_status: Optional[Literal['not_assigned','assigned']] = None


class CarResourceCreate(BaseModel):
    car_licence: str = Field(..., min_length=1, max_length=20)
    max_passengers: int = Field(..., ge=1)
    car_status: Optional[Literal['service','paused','maintenance','retired']] = 'service'
    commission_date: Optional[date] = None
    last_service_date: Optional[date] = None

class CarResourceUpdate(BaseModel):
    car_licence: Optional[str] = Field(None, min_length=1, max_length=20)
    max_passengers: Optional[int] = Field(None, ge=1)
    car_status: Optional[Literal['service','paused','maintenance','retired']] = None
    commission_date: Optional[date] = None
    last_service_date: Optional[date] = None

# 依賴注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 工具函數
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """從 Bearer token 中獲取當前用戶"""
    token = credentials.credentials
    
    # 簡單的 token 解析 (格式: admin_{user_id}_token)
    if not token.startswith('admin_') or not token.endswith('_token'):
        raise HTTPException(status_code=401, detail="無效的 token 格式")
    
    try:
        # 從 token 中提取用戶 ID
        user_id = int(token.split('_')[1])
        user = db.query(AdminUser).filter(AdminUser.admin_id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="用戶不存在")
        return user
    except (ValueError, IndexError):
        raise HTTPException(status_code=401, detail="無效的 token")

def check_permission(user, permission: str, db: Session) -> bool:
    role = db.query(AdminRole).filter(AdminRole.role_id == user.role_id).first()
    if not role:
        return False
    permissions = role.permissions.split(',') if role.permissions else []  # 假設 permissions 是逗號分隔
    return permission in permissions

def get_role_by_id(db: Session, role_id: Optional[int]) -> Optional[AdminRole]:
    if role_id is None:
        return None
    return db.query(AdminRole).filter(AdminRole.role_id == role_id).first()

def get_role_name(db: Session, role_id: Optional[int]) -> Optional[str]:
    role = get_role_by_id(db, role_id)
    return (role.role_name if role else None)

# Redis 相關輔助函數
def get_redis():
    if redis is None:
        # 若無 redis 模組，回退至記憶體版（僅開發用）
        if not hasattr(app.state, "redis") or app.state.redis is None:
            print("[OTP] redis 模組未安裝，改用 InMemoryRedis（開發用）")
            app.state.redis = InMemoryRedis()
        return app.state.redis
    if not hasattr(app.state, "redis") or app.state.redis is None:
        try:
            app.state.redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            app.state.redis.ping()
        except Exception as e:  # pragma: no cover
            # 連線失敗時回退到 InMemoryRedis：開發測試無阻
            print(f"[OTP] Redis 連線失敗，改用 InMemoryRedis：{e}")
            app.state.redis = InMemoryRedis()
    return app.state.redis

def _norm_account(acc: str) -> str:
    return (acc or "").strip().lower()

def _hash_key(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()

def _otp_keys(purpose: str, acc_hash: str):
    return {
        "code": f"otp:{purpose}:{acc_hash}",
        "tries": f"otp:{purpose}:{acc_hash}:tries",
        "cooldown": f"otp:{purpose}:{acc_hash}:cooldown",
        "lock": f"otp:{purpose}:{acc_hash}:lock",
        "dest_rl": f"otp:rl:dest:{acc_hash}",
    }

def _ip_key(ip: str) -> str:
    return f"otp:rl:ip:{ip}"

# 排班調度數據模型
class ScheduleCreate(BaseModel):
    route_no: str = Field(..., min_length=1, max_length=20)  # 對應 bus_routes_total.route_id
    direction: Optional[str] = Field(None, max_length=10)
    special_type: Optional[str] = Field(None, max_length=50)
    operation_status: Optional[str] = Field(None, max_length=20)
    schedule_date: Optional[date] = Field(None)  # 暫停營運時可為空
    departure_time: Optional[time] = Field(None)  # 暫停營運時可為空
    license_plate: Optional[str] = Field(None, min_length=1, max_length=20)  # 對應 car_resource.car_licence，暫停營運時可為空
    driver_name: Optional[str] = Field(None, min_length=1, max_length=50)  # 暫停營運時可為空
    employee_id: Optional[str] = Field(None, min_length=1, max_length=20)  # 暫停營運時可為空

class ScheduleUpdate(BaseModel):
    route_no: Optional[str] = Field(None, min_length=1, max_length=20)
    direction: Optional[str] = Field(None, max_length=10)
    special_type: Optional[str] = Field(None, max_length=50)
    operation_status: Optional[str] = Field(None, max_length=20)
    schedule_date: Optional[date] = Field(None)  # 重命名避免與date類型衝突
    departure_time: Optional[time] = Field(None)
    license_plate: Optional[str] = Field(None, min_length=1, max_length=20)
    driver_name: Optional[str] = Field(None, min_length=1, max_length=50)
    employee_id: Optional[str] = Field(None, min_length=1, max_length=20)


# FastAPI 應用
app = FastAPI()

# 動態 CORS 設定函數
def is_allowed_origin(origin: str) -> bool:
    """檢查來源是否被允許"""
    allowed_patterns = [
        "http://localhost:5173",
        "http://127.0.0.1:5173", 
        "http://192.168.0.",  # 192.168.0.x 網段
        "http://192.168.1.",  # 192.168.1.x 網段
        "http://10.0.0.",     # 10.0.0.x 網段
        ":5173"               # 任何使用 5173 port 的地址
    ]
    
    for pattern in allowed_patterns:
        if pattern in origin:
            return True
    return False

# 加入 CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):(5173|3000|8080)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 登入 API
@app.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.username == request.username).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="無效憑證")
    
    # 檢查用戶狀態
    if user.status != 'active':
        status_messages = {
            'inactive': '帳號已停用，請聯繫管理員'
        }
        raise HTTPException(status_code=401, detail=status_messages.get(user.status, '帳號狀態異常'))
    
    # 驗證密碼
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="無效憑證")
    
    # 更新 last_login 為台北時間
    user.last_login = get_taiwan_datetime()
    db.commit()
    
    # 獲取角色資訊
    role = db.query(AdminRole).filter(AdminRole.role_id == user.role_id).first()
    
    # 回傳前端期望的格式
    return {
        "access_token": f"admin_{user.admin_id}_token", # 簡化的 token
        "token_type": "bearer",
        "user_id": user.admin_id,
        "username": user.username,
        "role": role.role_name if role else None
    }

# 儀表板統計 API
@app.get("/api/dashboard/member-stats")
def get_member_statistics(db: Session = Depends(get_db)):
    """
    取得會員統計資料
    """
    try:
        # 計算總會員數
        total_members = db.query(User).count()
        
        # 計算活躍會員數 (status = 'active')
        active_members = db.query(User).filter(User.status == 'active').count()
        
        # 計算本月新會員數 (使用台北時區)
        taipei_now = get_taipei_time()
        start_of_month = taipei_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # 轉換為無時區的 datetime 供資料庫查詢使用
        start_of_month_naive = start_of_month.replace(tzinfo=None)
        
        # 先檢查 User 模型是否有 created_at 欄位
        try:
            new_members_this_month = db.query(User).filter(User.created_at >= start_of_month_naive).count()
        except AttributeError:
            # 如果沒有 created_at 欄位，則設為 0
            new_members_this_month = 0
        
        return {
            "success": True,
            "data": {
                "total_members": total_members,
                "active_members": active_members,
                "new_members_this_month": new_members_this_month,
                "growth_rate": round((new_members_this_month / max(total_members - new_members_this_month, 1)) * 100, 2) if total_members > 0 else 0
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": {
                "total_members": 0,
                "active_members": 0,
                "new_members_this_month": 0,
                "growth_rate": 0
            }
        }

# 會員增長趨勢 API
@app.get("/api/dashboard/member-growth")
def get_member_growth_trend(days: int = 7, db: Session = Depends(get_db)):
    """
    取得會員增長趨勢資料
    參數: days - 查詢天數 (1, 7, 30)
    """
    try:
        from datetime import timedelta
        from sqlalchemy import func, extract
        
        taipei_now = get_taipei_time()
        start_date = taipei_now - timedelta(days=days)
        start_date_naive = start_date.replace(tzinfo=None)
        
        # 根據天數決定分組方式
        if days == 1:
            # 最近1天：按小時分組
            growth_data = []
            for i in range(24):
                hour_start = (taipei_now - timedelta(hours=23-i)).replace(minute=0, second=0, microsecond=0)
                hour_end = hour_start + timedelta(hours=1)
                
                count = db.query(User).filter(
                    User.created_at >= hour_start.replace(tzinfo=None),
                    User.created_at < hour_end.replace(tzinfo=None)
                ).count()
                
                growth_data.append({
                    "period": hour_start.strftime("%H:00"),
                    "count": count,
                    "cumulative": sum([x["count"] for x in growth_data]) + count
                })
                
        elif days == 7:
            # 近7天：按天分組
            growth_data = []
            cumulative_count = db.query(User).filter(
                User.created_at < start_date_naive
            ).count()
            
            for i in range(days):
                day_start = (start_date + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                
                daily_count = db.query(User).filter(
                    User.created_at >= day_start.replace(tzinfo=None),
                    User.created_at < day_end.replace(tzinfo=None)
                ).count()
                
                cumulative_count += daily_count
                
                growth_data.append({
                    "period": day_start.strftime("%m/%d"),
                    "count": daily_count,
                    "cumulative": cumulative_count
                })
                
        else:  # days == 30
            # 近30天：按週分組
            growth_data = []
            cumulative_count = db.query(User).filter(
                User.created_at < start_date_naive
            ).count()
            
            # 分成5週，每週6天
            for week in range(5):
                week_start = start_date + timedelta(days=week*6)
                week_end = week_start + timedelta(days=6)
                
                weekly_count = db.query(User).filter(
                    User.created_at >= week_start.replace(tzinfo=None),
                    User.created_at < week_end.replace(tzinfo=None)
                ).count()
                
                cumulative_count += weekly_count
                
                growth_data.append({
                    "period": f"{week_start.strftime('%m/%d')}",
                    "count": weekly_count,
                    "cumulative": cumulative_count
                })
        
        # 計算統計資料
        total_growth = sum([x["count"] for x in growth_data])
        avg_daily = round(total_growth / max(days, 1), 1)
        
        return {
            "success": True,
            "data": {
                "growth_data": growth_data,
                "total_growth": total_growth,
                "avg_daily": avg_daily,
                "period_days": days
            }
        }
    except Exception as e:
        # 回傳預設資料以避免前端錯誤
        default_data = []
        if days == 1:
            default_data = [{"period": f"{i}:00", "count": 0, "cumulative": 0} for i in range(24)]
        elif days == 7:
            default_data = [{"period": f"0{i+1}/0{i+1}", "count": 0, "cumulative": 0} for i in range(7)]
        else:
            default_data = [{"period": f"Week{i+1}", "count": 0, "cumulative": 0} for i in range(5)]
        
        return {
            "success": False,
            "error": str(e),
            "data": {
                "growth_data": default_data,
                "total_growth": 0,
                "avg_daily": 0,
                "period_days": days
            }
        }

# 預約統計（本月/今日/狀態）
@app.get("/api/dashboard/reservation-stats")
def get_reservation_stats(db: Session = Depends(get_db)):
    """
    回傳預約統計：
    - this_month: 本月建立的預約數（以 created_at 為主，若無則以 booking_time）
    - today_new: 今日新建立的預約數
    - pending: 審核中筆數（review_status='pending'）
    - completed: 已完成筆數（reservation_status='completed'）
    - last_month: 上月建立的預約數
    - growth_rate: 相較上月成長率（%）
    """
    try:
        now = get_taipei_time()
        # 本月第一天 00:00
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # 下月第一天 00:00
        if start_of_month.month == 12:
            next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
        else:
            next_month = start_of_month.replace(month=start_of_month.month + 1)
        # 今日 00:00
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 上月第一天與上月結束
        if start_of_month.month == 1:
            last_month_start = start_of_month.replace(year=start_of_month.year - 1, month=12)
        else:
            last_month_start = start_of_month.replace(month=start_of_month.month - 1)

        # 轉為 naive datetime（去除 tzinfo）
        som = start_of_month.replace(tzinfo=None)
        next_m = next_month.replace(tzinfo=None)
        today0 = start_of_today.replace(tzinfo=None)
        lm_start = last_month_start.replace(tzinfo=None)

        # 優先以 created_at 計算，若資料沒有 created_at 則 fallback 以 booking_time
        def _count_between(col: str, start_dt, end_dt):
            sql = f"SELECT COUNT(*) as c FROM reservation WHERE {col} >= %s AND {col} < %s"
            try:
                res = MySQL_Run(sql, (start_dt, end_dt))
                return int(res[0]['c']) if res else 0
            except Exception:
                return 0

        # 嘗試用 created_at
        this_month = _count_between('created_at', som, next_m)
        today_new = _count_between('created_at', today0, now.replace(tzinfo=None))
        last_month = _count_between('created_at', lm_start, som)

        # 若全部為 0，改用 booking_time
        if this_month == 0 and last_month == 0 and today_new == 0:
            this_month = _count_between('booking_time', som, next_m)
            today_new = _count_between('booking_time', today0, now.replace(tzinfo=None))
            last_month = _count_between('booking_time', lm_start, som)

        # 狀態統計
        try:
            pending = MySQL_Run("SELECT COUNT(*) as c FROM reservation WHERE review_status = 'pending'")[0]['c']
        except Exception:
            pending = 0
        try:
            completed = MySQL_Run("SELECT COUNT(*) as c FROM reservation WHERE reservation_status = 'completed'")[0]['c']
        except Exception:
            completed = 0

        growth_rate = 0.0
        try:
            if last_month > 0:
                growth_rate = round((this_month - last_month) / last_month * 100.0, 2)
        except Exception:
            growth_rate = 0.0

        return {
            "success": True,
            "data": {
                "this_month": this_month,
                "today_new": today_new,
                "pending": pending,
                "completed": completed,
                "last_month": last_month,
                "growth_rate": growth_rate,
            },
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": {
                "this_month": 0,
                "today_new": 0,
                "pending": 0,
                "completed": 0,
                "last_month": 0,
                "growth_rate": 0.0,
            },
        }

@app.get("/api/dashboard/reservations/trend")
def get_reservation_trend(
    mode: Literal['monthly', 'range'] = Query('monthly'),
    year: Optional[int] = None,
    month: Optional[int] = None,
    start_month: Optional[str] = Query(None, description="起始月份 YYYY-MM"),
    end_month: Optional[str] = Query(None, description="結束月份 YYYY-MM"),
):
    try:
        mode_value = (mode or 'monthly').lower()
        if mode_value not in ('monthly', 'range'):
            raise HTTPException(status_code=400, detail="mode 僅支援 monthly 或 range")

        now = get_taipei_time()

        if mode_value == 'monthly':
            target_year = year or now.year
            target_month = month or now.month
            if target_month < 1 or target_month > 12:
                raise HTTPException(status_code=400, detail="month 需介於 1-12")

            start_date = date(target_year, target_month, 1)
            last_day = monthrange(target_year, target_month)[1]
            end_date = date(target_year, target_month, last_day)
            start_dt, end_dt = _ensure_datetime_window(start_date, end_date)

            rows = _fetch_reservations_in_range(start_dt, end_dt)
            weeks = _generate_week_ranges(target_year, target_month)
            week_totals = [0 for _ in weeks]
            for row in rows:
                event_dt = _normalize_datetime(row.get('event_time'))
                if not event_dt:
                    continue
                event_date = event_dt.date()
                if event_date < start_date or event_date > end_date:
                    continue
                diff = (event_date - start_date).days
                index = min(diff // 7, len(weeks) - 1)
                week_totals[index] += 1

            total = sum(week_totals)
            weeks_output = []
            for info, count in zip(weeks, week_totals):
                weeks_output.append({
                    "week": info['week'],
                    "label": info['label'],
                    "start_date": info['start'].isoformat(),
                    "end_date": info['end'].isoformat(),
                    "count": count,
                })

            return {
                "success": True,
                "data": {
                    "mode": "monthly",
                    "year": target_year,
                    "month": target_month,
                    "weeks": weeks_output,
                    "total": total,
                },
            }

        # range mode
        if not start_month or not end_month:
            raise HTTPException(status_code=400, detail="range 模式需提供 start_month 與 end_month")

        start_date = _parse_month_string(start_month)
        end_marker = _parse_month_string(end_month)
        if end_marker < start_date:
            raise HTTPException(status_code=400, detail="end_month 不可早於 start_month")

        end_date = _month_last_day(end_marker)
        start_dt, end_dt = _ensure_datetime_window(start_date, end_date)
        rows = _fetch_reservations_in_range(start_dt, end_dt)

        month_totals: Dict[str, int] = defaultdict(int)
        for row in rows:
            event_dt = _normalize_datetime(row.get('event_time'))
            if not event_dt:
                continue
            event_date = event_dt.date()
            if event_date < start_date or event_date > end_date:
                continue
            key = event_date.strftime("%Y-%m")
            month_totals[key] += 1

        months_output = []
        total = 0
        cursor = start_date
        while cursor <= end_date:
            key = cursor.strftime("%Y-%m")
            count = month_totals.get(key, 0)
            months_output.append({
                "month": key,
                "label": f"{cursor.year}年{cursor.month}月",
                "count": count,
            })
            total += count
            cursor = _add_month(cursor)

        return {
            "success": True,
            "data": {
                "mode": "range",
                "start_month": start_date.strftime("%Y-%m"),
                "end_month": end_date.strftime("%Y-%m"),
                "months": months_output,
                "total": total,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        print("get_reservation_trend error:", exc)
        raise HTTPException(status_code=500, detail="取得預約趨勢資料時發生錯誤")

@app.get("/api/dashboard/reservations/status")
def get_reservation_status_distribution(
    mode: Literal['monthly', 'range'] = Query('monthly'),
    year: Optional[int] = None,
    month: Optional[int] = None,
    start_month: Optional[str] = Query(None, description="日期格式 YYYY-MM"),
    end_month: Optional[str] = Query(None, description="日期格式 YYYY-MM"),
):
    try:
        mode_value = (mode or 'monthly').lower()
        if mode_value not in ('monthly', 'range'):
            raise HTTPException(status_code=400, detail="mode 參數僅支援 monthly 或 range")

        now = get_taipei_time()

        if mode_value == 'monthly':
            target_year = year or now.year
            target_month = month or now.month
            if target_month < 1 or target_month > 12:
                raise HTTPException(status_code=400, detail="month 需介於 1-12")

            start_date = date(target_year, target_month, 1)
            last_day = monthrange(target_year, target_month)[1]
            end_date = date(target_year, target_month, last_day)
            start_dt, end_dt = _ensure_datetime_window(start_date, end_date)

            rows = _fetch_reservations_in_range(start_dt, end_dt)
            weeks = _generate_week_ranges(target_year, target_month)
            week_buckets: List[Dict[str, object]] = []
            for _ in weeks:
                week_buckets.append({
                    "reservation_status": defaultdict(int),
                    "review_status": defaultdict(int),
                    "total": 0,
                })

            reservation_keys: Set[str] = set()
            review_keys: Set[str] = set()

            for row in rows:
                event_dt = _normalize_datetime(row.get('event_time'))
                if not event_dt:
                    continue
                event_date = event_dt.date()
                if event_date < start_date or event_date > end_date:
                    continue
                diff = (event_date - start_date).days
                index = min(diff // 7, len(weeks) - 1)
                bucket = week_buckets[index]
                bucket['total'] = bucket['total'] + 1

                r_status = _normalize_status(row.get('reservation_status'))
                rv_status = _normalize_status(row.get('review_status'))
                bucket['reservation_status'][r_status] += 1
                bucket['review_status'][rv_status] += 1
                reservation_keys.add(r_status)
                review_keys.add(rv_status)

            reservation_key_order = _sort_status_keys(reservation_keys, RESERVATION_STATUS_PRIORITY)
            review_key_order = _sort_status_keys(review_keys, REVIEW_STATUS_PRIORITY)

            weeks_output = []
            total = 0
            for info, bucket in zip(weeks, week_buckets):
                total += bucket['total']
                weeks_output.append({
                    "week": info['week'],
                    "label": info['label'],
                    "start_date": info['start'].isoformat(),
                    "end_date": info['end'].isoformat(),
                    "total": bucket['total'],
                    "reservation_status": {key: bucket['reservation_status'].get(key, 0) for key in reservation_key_order},
                    "review_status": {key: bucket['review_status'].get(key, 0) for key in review_key_order},
                })

            return {
                "success": True,
                "data": {
                    "mode": "monthly",
                    "year": target_year,
                    "month": target_month,
                    "weeks": weeks_output,
                    "total": total,
                    "reservation_status_keys": reservation_key_order,
                    "review_status_keys": review_key_order,
                },
            }

        # range mode
        if not start_month or not end_month:
            raise HTTPException(status_code=400, detail="range 模式需提供 start_month 與 end_month")

        start_date = _parse_month_string(start_month)
        end_marker = _parse_month_string(end_month)
        if end_marker < start_date:
            raise HTTPException(status_code=400, detail="結束月份不可早於開始月份")

        end_date = _month_last_day(end_marker)
        start_dt, end_dt = _ensure_datetime_window(start_date, end_date)
        rows = _fetch_reservations_in_range(start_dt, end_dt)

        month_stats: Dict[str, Dict[str, object]] = {}
        reservation_keys: Set[str] = set()
        review_keys: Set[str] = set()

        for row in rows:
            event_dt = _normalize_datetime(row.get('event_time'))
            if not event_dt:
                continue
            event_date = event_dt.date()
            if event_date < start_date or event_date > end_date:
                continue
            key = event_date.strftime("%Y-%m")
            stats = month_stats.get(key)
            if stats is None:
                stats = {
                    "reservation_status": defaultdict(int),
                    "review_status": defaultdict(int),
                    "total": 0,
                }
                month_stats[key] = stats

            stats['total'] = stats['total'] + 1
            r_status = _normalize_status(row.get('reservation_status'))
            rv_status = _normalize_status(row.get('review_status'))
            stats['reservation_status'][r_status] += 1
            stats['review_status'][rv_status] += 1
            reservation_keys.add(r_status)
            review_keys.add(rv_status)

        reservation_key_order = _sort_status_keys(reservation_keys, RESERVATION_STATUS_PRIORITY)
        review_key_order = _sort_status_keys(review_keys, REVIEW_STATUS_PRIORITY)

        months_output = []
        total = 0
        cursor = start_date
        while cursor <= end_date:
            key = cursor.strftime("%Y-%m")
            stats = month_stats.get(key)
            if stats is None:
                stats = {
                    "reservation_status": defaultdict(int),
                    "review_status": defaultdict(int),
                    "total": 0,
                }
            total += stats['total']
            months_output.append({
                "month": key,
                "label": f"{cursor.year}年{cursor.month}月",
                "total": stats['total'],
                "reservation_status": {item: stats['reservation_status'].get(item, 0) for item in reservation_key_order},
                "review_status": {item: stats['review_status'].get(item, 0) for item in review_key_order},
            })
            cursor = _add_month(cursor)

        return {
            "success": True,
            "data": {
                "mode": "range",
                "start_month": start_date.strftime("%Y-%m"),
                "end_month": end_date.strftime("%Y-%m"),
                "months": months_output,
                "total": total,
                "reservation_status_keys": reservation_key_order,
                "review_status_keys": review_key_order,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        print("get_reservation_status_distribution error:", exc)
        raise HTTPException(status_code=500, detail="取得預約狀態資料時發生錯誤")

# 路線統計（總數/啟用/站點覆蓋率）
@app.get("/api/dashboard/route-stats")
def get_route_stats():
    """
    回傳路線統計：
    - total: bus_routes_total 總路線數
    - active: 啟用路線數（status = 1）
    - inactive: 停用路線數
    - on_time_rate: 以有站點的路線比率作為近似值（DISTINCT route_id / total）
    """
    try:
        t_total = MySQL_Run("SELECT COUNT(*) as c FROM bus_routes_total")[0]['c']
        try:
            t_active = MySQL_Run("SELECT COUNT(*) as c FROM bus_routes_total WHERE status = 1")[0]['c']
        except Exception:
            t_active = 0
        inactive = max(t_total - t_active, 0)
        try:
            with_stations = MySQL_Run("SELECT COUNT(DISTINCT route_id) as c FROM bus_route_stations")[0]['c']
        except Exception:
            with_stations = 0
        #rate = round((with_stations / max(t_total, 1)) * 100.0, 1)
        return {
            "success": True,
            "data": {
                "total": int(t_total),
                "active": int(t_active),
                "inactive": int(inactive),
                #"on_time_rate": rate,
                "routes_with_stations": int(with_stations),
            },
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": {
                "total": 0,
                "active": 0,
                "inactive": 0,
                "on_time_rate": 0.0,
                "routes_with_stations": 0,
            },
        }
        
# 會員活躍度分析 API
@app.get("/api/dashboard/member-activity")
def get_member_activity(days: int = 7, db: Session = Depends(get_db)):
    """
    取得會員活躍度分析數據
    
    參數:
    - days: 分析天數 (1, 7, 30)
    """
    try:
        # 計算時間範圍
        end_date = get_taipei_time()
        start_date = end_date - timedelta(days=days)
        start_date_naive = start_date.replace(tzinfo=None)
        end_date_naive = end_date.replace(tzinfo=None)
        
        # 定義活躍度標準
        # 高活躍：最近登入 <= 3天
        # 中活躍：最近登入 4-7天  
        # 低活躍：最近登入 8-30天
        # 不活躍：最近登入 > 30天 或從未登入
        
        now_naive = end_date.replace(tzinfo=None)
        high_active_cutoff = now_naive - timedelta(days=3)
        medium_active_cutoff = now_naive - timedelta(days=7)
        low_active_cutoff = now_naive - timedelta(days=30)
        
        # 查詢各活躍度級別的會員數量
        high_active = db.query(User).filter(
            User.status == 'active',
            User.last_login.isnot(None),
            User.last_login >= high_active_cutoff
        ).count()
        
        medium_active = db.query(User).filter(
            User.status == 'active',
            User.last_login.isnot(None),
            User.last_login >= medium_active_cutoff,
            User.last_login < high_active_cutoff
        ).count()
        
        low_active = db.query(User).filter(
            User.status == 'active',
            User.last_login.isnot(None),
            User.last_login >= low_active_cutoff,
            User.last_login < medium_active_cutoff
        ).count()
        
        inactive = db.query(User).filter(
            User.status == 'active'
        ).filter(
            (User.last_login.is_(None)) | 
            (User.last_login < low_active_cutoff)
        ).count()
        
        # 計算總數和活躍率
        total_members = high_active + medium_active + low_active + inactive
        active_members = high_active + medium_active
        active_rate = round((active_members / total_members * 100), 1) if total_members > 0 else 0
        
        # 計算最大值用於百分比計算
        max_count = max(high_active, medium_active, low_active, inactive) if total_members > 0 else 1
        
        # 構建活躍度數據
        activity_data = [
            {
                "label": "高活躍",
                "count": high_active,
                "percentage": round((high_active / max_count * 100), 1) if max_count > 0 else 0
            },
            {
                "label": "中活躍", 
                "count": medium_active,
                "percentage": round((medium_active / max_count * 100), 1) if max_count > 0 else 0
            },
            {
                "label": "低活躍",
                "count": low_active,
                "percentage": round((low_active / max_count * 100), 1) if max_count > 0 else 0
            },
            {
                "label": "不活躍",
                "count": inactive,
                "percentage": round((inactive / max_count * 100), 1) if max_count > 0 else 0
            }
        ]
        
        return {
            "success": True,
            "data": {
                "activity_data": activity_data,
                "summary": {
                    "active_rate": active_rate,
                    "active_members": active_members,
                    "total_members": total_members
                },
                "period_days": days
            }
        }
        
    except Exception as e:
        print(f"會員活躍度查詢錯誤: {e}")
        # 返回預設數據以防錯誤
        return {
            "success": False,
            "data": {
                "activity_data": [
                    {"label": "高活躍", "count": 0, "percentage": 0},
                    {"label": "中活躍", "count": 0, "percentage": 0},
                    {"label": "低活躍", "count": 0, "percentage": 0},
                    {"label": "不活躍", "count": 0, "percentage": 0}
                ],
                "summary": {
                    "active_rate": 0,
                    "active_members": 0,
                    "total_members": 0
                },
                "period_days": days
            }
        }

# 管理員統計 API
@app.get("/api/dashboard/admin-stats")
def get_admin_statistics(db: Session = Depends(get_db)):
    """
    取得管理員統計資料
    """
    try:
        # 計算總管理員數
        total_admins = db.query(AdminUser).count()
        
        # 計算角色數量
        total_roles = db.query(AdminRole).count()
        
        # 假設目前在線管理員為 1 (可以根據實際需求修改)
        online_admins = 1
        
        return {
            "success": True,
            "data": {
                "total_admins": total_admins,
                "online_admins": online_admins,
                "total_roles": total_roles,
                "active_today": 1
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": {
                "total_admins": 0,
                "online_admins": 0,
                "total_roles": 0,
                "active_today": 0
            }
        }

# 資料庫狀況 API
@app.get("/api/dashboard/database-stats")
def get_database_statistics(db: Session = Depends(get_db)):
    """
    取得資料庫狀況統計
    """
    try:
        from time import time
        start_time = time()
        
        # 測試資料庫連線
        db.execute(text("SELECT 1"))
        
        connection_time = round((time() - start_time) * 1000, 2)  # 轉換為毫秒
        
        # 取得資料表數量
        result = db.execute(text("SHOW TABLES"))
        total_tables = len(list(result))
        
        return {
            "success": True,
            "data": {
                "status": "正常",
                "connection_time": connection_time,
                "total_tables": total_tables,
                "health": "良好" if connection_time < 100 else "一般"
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": {
                "status": "異常",
                "connection_time": 9999,
                "total_tables": 0,
                "health": "異常"
            }
        }

# 用戶管理 API
@app.get("/users")
def get_users(
    page: int = 1,
    limit: int = 10,
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # 基本查詢
    query = db.query(User)
    
    # 搜尋條件（ID、用戶名、LINE ID、Email、電話）
    if search:
        search_pattern = f"%{search}%"
        try:
            # 嘗試將輸入轉成整數，供精確比對 user_id
            search_id = int(search)
        except (TypeError, ValueError):
            search_id = None

        conditions = [
            User.username.like(search_pattern),
            User.email.like(search_pattern),
            User.phone.like(search_pattern),
            User.line_id.like(search_pattern),
        ]
        # 允許以 ID 搜尋（精確或以 CAST 模糊）
        if search_id is not None:
            conditions.append(User.user_id == search_id)
        # CAST user_id 為字串做模糊，兼容輸入前綴/混合字串
        try:
            from sqlalchemy import cast, String
            conditions.append(cast(User.user_id, String).like(search_pattern))
        except Exception:
            pass

        from sqlalchemy import or_
        query = query.filter(or_(*conditions))
    
    # 狀態篩選
    if status:
        query = query.filter(User.status == status)
    
    # 計算總數
    total = query.count()
    
    # 分頁
    users = query.offset((page - 1) * limit).limit(limit).all()
    
    # 格式化回應
    users_data = []
    for u in users:
        # 兼容舊值：DB 可能存在 'None'，統一轉成 'no_reservation'
        rsv = u.reservation_status
        if rsv == 'None' or rsv is None:
            rsv_out = 'no_reservation'
        else:
            rsv_out = rsv
        users_data.append({
            "user_id": u.user_id,
            "line_id": u.line_id,
            "username": u.username,
            "email": u.email,
            "phone": u.phone,
            "status": u.status,
            "reservation_status": rsv_out,
            "preferences": u.preferences,
            "privacy_settings": u.privacy_settings,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "updated_at": u.updated_at.isoformat() if u.updated_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None
        })
    
    return {
        "users": users_data,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit
    }

## 移除早期未受權限保護的 create_user，改用下方受保護版本

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用戶不存在")
    return {
        "user_id": user.user_id, 
        "line_id": user.line_id, 
        "username": user.username, 
        "email": user.email, 
        "phone": user.phone, 
        "status": user.status,
        "reservation_status": ('no_reservation' if (user.reservation_status in (None, 'None')) else user.reservation_status),
        "preferences": user.preferences, 
        "privacy_settings": user.privacy_settings,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None
    }

# 用戶登入驗證 API
class UserLogin(BaseModel):
    username: str
    password: str

@app.post("/users/login")
def login_user(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="用戶名或密碼錯誤")
    
    # 檢查用戶狀態：停用則禁止登入
    if user.status != 'active':
        status_messages = {
            'inactive': '帳號已停用，請聯絡管理員'
        }
        raise HTTPException(status_code=401, detail=status_messages.get(user.status, '帳號狀態異常'))
    
    # 檢查用戶是否有密碼設定
    if not user.password:
        raise HTTPException(status_code=401, detail="用戶尚未設定密碼，請聯絡管理員")
    
    # 檢查密碼
    try:
        if not bcrypt.checkpw(login_data.password.encode('utf-8'), user.password.encode('utf-8')):
            raise HTTPException(status_code=401, detail="用戶名或密碼錯誤")
    except ValueError:
        # 密碼格式不正確，可能是舊格式或損壞的資料
        raise HTTPException(status_code=401, detail="密碼格式錯誤，請聯絡管理員重設密碼")
    
    # 更新最後登入時間（台灣時間）
    user.last_login = get_taiwan_datetime()
    db.commit()
    
    return {
        "message": "登入成功",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "line_id": user.line_id,
            "email": user.email,
            "phone": user.phone,
            "status": user.status,
            "reservation_status": user.reservation_status
        }
    }

# 管理員用戶 API
@app.get("/api/admin/users")
def get_admin_users(
    page: int = 1,
    limit: int = 10,
    search: Optional[str] = None,
    status: Optional[str] = None,
    order: Literal['asc', 'desc'] = 'desc',
    db: Session = Depends(get_db)
):
    """
    取得管理員用戶列表（支援分頁和搜尋）
    
    參數:
    - page: 頁碼 (預設 1)
    - limit: 每頁筆數 (預設 10)
    - search: 搜尋關鍵字（搜尋用戶名）
    - status: 狀態篩選 (active, inactive)
    """
    try:
        # 建立基本查詢
        query = db.query(AdminUser, AdminRole).join(
            AdminRole, AdminUser.role_id == AdminRole.role_id, isouter=True
        )
        
        # 搜尋功能
        if search:
            query = query.filter(AdminUser.username.contains(search))
        
        # 狀態篩選
        if status:
            query = query.filter(AdminUser.status == status)
        
        # 排序
        order_value = (order or 'desc').lower()
        if order_value not in ('asc', 'desc'):
            order_value = 'desc'
        order_column = AdminUser.admin_id.desc() if order_value == 'desc' else AdminUser.admin_id.asc()
        query = query.order_by(order_column)

        # 計算總筆數
        total = query.count()
        
        # 分頁
        offset = (page - 1) * limit
        admin_users = query.offset(offset).limit(limit).all()
        
        # 格式化結果
        result = []
        for admin_user, admin_role in admin_users:
            result.append({
                "admin_id": admin_user.admin_id,
                "username": admin_user.username,
                "role_id": admin_user.role_id,
                "role_name": admin_role.role_name if admin_role else "未指定",
                "status": admin_user.status,
                "last_login": admin_user.last_login.isoformat() if admin_user.last_login else None,
                "login_attempts": admin_user.login_attempts,
                "created_at": admin_user.created_at.isoformat() if admin_user.created_at else None
            })
        
        return {
            "success": True,
            "data": {
                "admin_users": result,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit
                }
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"取得管理員列表失敗: {str(e)}"
        }

# 取得管理員角色列表
@app.get("/api/admin/roles")
def get_admin_roles(db: Session = Depends(get_db)):
    """取得所有管理員角色"""
    try:
        roles = db.query(AdminRole).all()
        return {
            "success": True,
            "data": [{
                "role_id": role.role_id,
                "role_name": role.role_name,
                "role_description": role.role_description
            } for role in roles]
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"取得角色列表失敗: {str(e)}"
        }

@app.post("/api/admin/users")
def create_admin_user(user: AdminUserCreate, db: Session = Depends(get_db), current_user: AdminUser = Depends(get_current_user)):
    """建立新的管理員用戶"""
    try:
        # 獲取當前用戶角色
        current_role = db.query(AdminRole).filter(AdminRole.role_id == current_user.role_id).first()
        
        # 權限檢查
        target_role_name = get_role_name(db, user.role_id)
        if not target_role_name:
            return {"success": False, "message": "指定的角色不存在"}

        trn = target_role_name.lower()

        if current_role and (current_role.role_name or '').lower() == 'super_admin':
            # Super Admin 可以創建任何非 super_admin 之外的角色（若已存在 super_admin）
            if trn == 'super_admin':
                existing_super_admin_count = (
                    db.query(AdminUser)
                    .join(AdminRole, AdminUser.role_id == AdminRole.role_id)
                    .filter(func.lower(AdminRole.role_name) == 'super_admin')
                    .count()
                )
                if existing_super_admin_count >= 1:
                    return {
                        "success": False,
                        "message": "系統只能有一組 Super Admin"
                    }
        elif current_role and (current_role.role_name or '').lower() == 'admin':
            # Admin 只能創建 Dispatcher 帳號
            if trn != 'dispatcher':
                return {
                    "success": False,
                    "message": "高級管理員只能創建 Dispatcher 角色的帳號"
                }
        else:
            return {
                "success": False,
                "message": "沒有權限創建用戶"
            }
        
        # 檢查用戶名是否已存在
        existing_user = db.query(AdminUser).filter(AdminUser.username == user.username).first()
        if existing_user:
            return {
                "success": False,
                "message": "用戶名已存在"
            }
        
        hashed_password = hash_password(user.password)
        new_user = AdminUser(
            username=user.username, 
            password_hash=hashed_password, 
            role_id=user.role_id, 
            status=user.status, 
            created_by=user.created_by
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return {
            "success": True,
            "data": {
                "admin_id": new_user.admin_id,
                "message": "管理員用戶建立成功"
            }
        }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "message": f"建立管理員用戶失敗: {str(e)}"
        }

@app.put("/api/admin/users/{admin_id}")
def update_admin_user(admin_id: int, user_update: AdminUserUpdate, db: Session = Depends(get_db), current_user: AdminUser = Depends(get_current_user)):
    """更新管理員用戶"""
    try:            
        # 獲取當前用戶角色
        current_role = db.query(AdminRole).filter(AdminRole.role_id == current_user.role_id).first()
        
        user = db.query(AdminUser).filter(AdminUser.admin_id == admin_id).first()
        if not user:
            return {
                "success": False,
                "message": "管理員用戶不存在"
            }
        
        # 獲取要編輯的用戶角色
        target_role = db.query(AdminRole).filter(AdminRole.role_id == user.role_id).first()
        
        # 權限檢查
        if current_role and (current_role.role_name or '').lower() == 'super_admin':
            # Super Admin 可以修改其他用戶的任何屬性，但有特定限制
            if admin_id == current_user.admin_id:
                # Super Admin 不能修改自己的角色權限（包括降級為 Admin）
                if hasattr(user_update, 'role_id') and user_update.role_id and user_update.role_id != user.role_id:
                    return {
                        "success": False,
                        "message": "Super Admin 不能修改自己的角色權限，包括降級為 Admin"
                    }
                # Super Admin 不能把自己的狀態改為停用
                if hasattr(user_update, 'status') and user_update.status and user_update.status == 'inactive':
                    return {
                        "success": False,
                        "message": "Super Admin 不能停用自己的帳號"
                    }
            else:
                # Super Admin 不能修改其他 Super Admin 的任何資訊
                if target_role and target_role.role_name == 'super_admin':
                    return {
                        "success": False,
                        "message": "Super Admin 不能修改其他 Super Admin 的資訊"
                    }
        elif current_role and (current_role.role_name or '').lower() == 'admin':
            # Admin 的權限限制：只能操作 Dispatcher，用戶角色不可變，可變更其餘資訊（含狀態/密碼/用戶名）
            if target_role and (target_role.role_name or '').lower() == 'super_admin':
                return {"success": False, "message": "不能修改 Super Admin 用戶"}
            if target_role and (target_role.role_name or '').lower() == 'admin':
                return {"success": False, "message": "高級管理員不能修改其他 Admin 用戶"}
            # 不能修改角色
            if hasattr(user_update, 'role_id') and user_update.role_id and user_update.role_id != user.role_id:
                return {"success": False, "message": "無權限修改用戶角色"}
        else:
            return {
                "success": False,
                "message": "沒有權限修改用戶"
            }
        
        # 如果要更新用戶名，檢查是否已存在
        if hasattr(user_update, 'username') and user_update.username and user_update.username != user.username:
            existing_user = db.query(AdminUser).filter(
                AdminUser.username == user_update.username,
                AdminUser.admin_id != admin_id
            ).first()
            if existing_user:
                return {
                    "success": False,
                    "message": "用戶名已存在"
                }
        
        # 更新字段
        for key, value in user_update.dict(exclude_unset=True).items():
            if key == "password":
                # 只有密碼不為空時才更新
                if value and value.strip():
                    setattr(user, "password_hash", hash_password(value))
            else:
                setattr(user, key, value)
        
        db.commit()
        return {
            "success": True,
            "message": "管理員用戶更新成功"
        }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "message": f"更新管理員用戶失敗: {str(e)}"
        }

@app.delete("/api/admin/users/{admin_id}")
def delete_admin_user(admin_id: int, db: Session = Depends(get_db), current_user: AdminUser = Depends(get_current_user)):
    """刪除管理員用戶"""
    try:
        # 獲取當前用戶角色
        current_role = db.query(AdminRole).filter(AdminRole.role_id == current_user.role_id).first()
        
        user = db.query(AdminUser).filter(AdminUser.admin_id == admin_id).first()
        if not user:
            return {
                "success": False,
                "message": "管理員用戶不存在"
            }
            
        # 獲取要刪除用戶的角色
        target_role = db.query(AdminRole).filter(AdminRole.role_id == user.role_id).first()
        
        # 權限檢查
        if current_role and (current_role.role_name or '').lower() == 'super_admin':
            # Super Admin 可以刪除 Admin 用戶，但不能刪除自己或其他 Super Admin
            if admin_id == current_user.admin_id:
                return {
                    "success": False,
                    "message": "不能刪除自己的帳號"
                }
            # Super Admin 不能刪除其他 Super Admin
            if target_role and (target_role.role_name or '').lower() == 'super_admin':
                return {
                    "success": False,
                    "message": "Super Admin 不能刪除其他 Super Admin"
                }
        elif current_role and (current_role.role_name or '').lower() == 'admin':
            # Admin 只能刪除 Dispatcher
            if not (target_role and (target_role.role_name or '').lower() == 'dispatcher'):
                return {"success": False, "message": "高級管理員僅可刪除 Dispatcher 用戶"}
        else:
            return {
                "success": False,
                "message": "沒有權限刪除用戶"
            }
        
        # 檢查是否為系統管理員（可選的保護機制）
        if user.admin_id == 1:  # 假設 ID 1 是超級管理員
            return {
                "success": False,
                "message": "無法刪除超級管理員"
            }
        
        db.delete(user)
        db.commit()
        return {
            "success": True,
            "message": "管理員用戶刪除成功"
        }
    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "message": f"刪除管理員用戶失敗: {str(e)}"
        }

@app.get("/")
def root():
    return {
        "message": "Hualien Mini Bus Backend System",
        "status": "Running",
        "features": ["User Management", "Access Control", "Database Integration"]
    }

@app.get("/All_Route", response_model=List[Route])
def All_Route():
    try:
        rows = MySQL_Run("SELECT * FROM bus_routes_total")

        # MySQL_Run may return list of dicts (DictCursor) or list of tuples.
        if not rows:
            return []

        # If rows are dicts, build DataFrame directly
        if isinstance(rows, list) and isinstance(rows[0], dict):
            df = pd.DataFrame(rows)
        else:
            # fallback: get columns and construct DataFrame
            cols = MySQL_Run("SHOW COLUMNS FROM bus_routes_total")
            try:
                columns = [c[0] for c in cols]
            except Exception:
                # if cols are dicts
                columns = [c.get('Field') or list(c.values())[0] for c in cols]
            df = pd.DataFrame(rows, columns=columns)

        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce") \
                .apply(lambda x: x.to_pydatetime() if pd.notnull(x) else None)

        records = df.where(pd.notnull(df), None).to_dict(orient="records")
        return records
    except Exception as e:
        print(f"All_Route error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 新增路線的請求模型
class RouteCreate(BaseModel):
    route_name: str
    direction: Optional[str] = None
    start_stop: Optional[str] = None
    end_stop: Optional[str] = None
    stop_count: Optional[int] = 0
    status: Optional[int] = 1

@app.post("/api/routes/create")
def create_route(route: RouteCreate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """在 bus_routes_total 建立一筆新路線記錄"""
    try:
        # (已改為使用參數化檢查，移除早期非參數化檢查以避免 SQL 注入風險)

        # 使用參數化查詢，避免 SQL 注入
        stop_count = int(route.stop_count or 0)
        status = int(route.status or 1)

        # direction 只能是 '單向' 或 '雙向'（bus_routes_total schema）
        direction_val = route.direction if route.direction in ('單向', '雙向') else None

        # 檢查同名路線（參數化）
        check_sql = "SELECT COUNT(*) as count FROM bus_routes_total WHERE route_name = %s"
        check_result = MySQL_Run(check_sql, (route.route_name,))
        if check_result and check_result[0].get('count', 0) > 0:
            raise HTTPException(status_code=400, detail="路線名稱已存在")

        # 建構 INSERT 的欄位與參數
        cols = ['route_name', 'stop_count', 'status']
        placeholders = ['%s', '%s', '%s']
        params = [route.route_name, stop_count, status]
        if direction_val:
            cols.insert(2, 'direction')
            placeholders.insert(2, '%s')
            params.insert(2, direction_val)
        if route.start_stop:
            cols.append('start_stop')
            placeholders.append('%s')
            params.append(route.start_stop)
        if route.end_stop:
            cols.append('end_stop')
            placeholders.append('%s')
            params.append(route.end_stop)

        sql = f"INSERT INTO bus_routes_total ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        insert_res = MySQL_Run(sql, tuple(params))

        # MySQL_Run 對非 SELECT 會回傳 dict {status, lastrowid}
        new_route_id = None
        try:
            if isinstance(insert_res, dict) and insert_res.get('lastrowid'):
                new_route_id = int(insert_res.get('lastrowid'))
        except Exception:
            new_route_id = None

        # 若沒拿到 lastrowid，嘗試使用 SELECT LAST_INSERT_ID() 作為 fallback（但需注意連線會不同）
        if not new_route_id:
            try:
                last = MySQL_Run("SELECT LAST_INSERT_ID() as id")
                if last and isinstance(last, list) and len(last) > 0:
                    if isinstance(last[0], dict):
                        new_route_id = int(last[0].get('id') or last[0].get('LAST_INSERT_ID()') or 0)
                    else:
                        new_route_id = int(last[0][0])
            except Exception:
                new_route_id = None

    # 不再自動在 bus_route_stations 建立 placeholder 站點

        return {"message": "路線新增成功", "ok": True, "route_id": new_route_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"新增路線失敗: {e}")
        raise HTTPException(status_code=500, detail=f"新增路線失敗: {str(e)}")

class RouteUpdate(BaseModel):
    route_id: int
    route_name: Optional[str] = None
    direction: Optional[str] = None
    start_stop: Optional[str] = None
    end_stop: Optional[str] = None
    stop_count: Optional[int] = None
    status: Optional[int] = None

@app.put("/api/routes/update")
def update_route(route: RouteUpdate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """更新 bus_routes_total 的欄位（部分更新）"""
    try:
        # 確認 route 存在
        check_sql = "SELECT COUNT(*) as cnt FROM bus_routes_total WHERE route_id = %s"
        check_res = MySQL_Run(check_sql, (route.route_id,))
        if not check_res or check_res[0].get('cnt', 0) == 0:
            raise HTTPException(status_code=404, detail="找不到指定的路線")

        updates = []
        params = []

        if route.route_name is not None:
            # 檢查同名（排除自己）
            exist_sql = "SELECT COUNT(*) as c FROM bus_routes_total WHERE route_name = %s AND route_id != %s"
            exist_res = MySQL_Run(exist_sql, (route.route_name, route.route_id))
            if exist_res and exist_res[0].get('c', 0) > 0:
                raise HTTPException(status_code=400, detail="路線名稱已存在")
            updates.append("route_name = %s")
            params.append(route.route_name)

        if route.direction is not None:
            if route.direction not in ('單向', '雙向'):
                raise HTTPException(status_code=400, detail="direction 必須為 '單向' 或 '雙向'")
            updates.append("direction = %s")
            params.append(route.direction)

        if route.start_stop is not None:
            updates.append("start_stop = %s")
            params.append(route.start_stop)

        if route.end_stop is not None:
            updates.append("end_stop = %s")
            params.append(route.end_stop)

        if route.stop_count is not None:
            updates.append("stop_count = %s")
            params.append(int(route.stop_count))

        if route.status is not None:
            updates.append("status = %s")
            params.append(int(route.status))

        if not updates:
            return {"message": "沒有欄位需要更新", "ok": True}

        params.append(route.route_id)
        sql = f"UPDATE bus_routes_total SET {', '.join(updates)} WHERE route_id = %s"
        MySQL_Run(sql, tuple(params))

        return {"message": "路線更新成功", "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"更新路線失敗: {e}")
        raise HTTPException(status_code=500, detail=f"更新路線失敗: {str(e)}")

class RouteDelete(BaseModel):
    route_id: int

@app.delete("/api/routes/delete")
def delete_route(req: RouteDelete, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """刪除路線：會同時刪除對應的 bus_route_stations 以及 bus_routes_total 的紀錄（若存在）。"""
    try:
        rid = int(req.route_id)

        # 先確認是否有此路線（優先查 bus_routes_total）
        try:
            chk = MySQL_Run("SELECT COUNT(*) as cnt FROM bus_routes_total WHERE route_id = %s", (rid,))
        except TypeError:
            chk = MySQL_Run(f"SELECT COUNT(*) as cnt FROM bus_routes_total WHERE route_id = {rid}")

        exists = False
        if chk and isinstance(chk, list) and chk[0].get('cnt', 0) > 0:
            exists = True
        else:
            # 若 bus_routes_total 沒有紀錄，檢查 bus_route_stations
            try:
                chk2 = MySQL_Run("SELECT COUNT(*) as cnt FROM bus_route_stations WHERE route_id = %s", (rid,))
            except TypeError:
                chk2 = MySQL_Run(f"SELECT COUNT(*) as cnt FROM bus_route_stations WHERE route_id = {rid}")
            if chk2 and isinstance(chk2, list) and chk2[0].get('cnt', 0) > 0:
                exists = True

        if not exists:
            raise HTTPException(status_code=404, detail="找不到指定的路線")

        # 刪除該路線的站點（若有）
        try:
            MySQL_Run("DELETE FROM bus_route_stations WHERE route_id = %s", (rid,))
        except TypeError:
            MySQL_Run(f"DELETE FROM bus_route_stations WHERE route_id = {rid}")

        # 刪除 bus_routes_total 中的路線紀錄（若有）
        try:
            MySQL_Run("DELETE FROM bus_routes_total WHERE route_id = %s", (rid,))
        except TypeError:
            MySQL_Run(f"DELETE FROM bus_routes_total WHERE route_id = {rid}")

        return {"message": "路線刪除成功", "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"刪除路線失敗: {e}")
        raise HTTPException(status_code=500, detail=f"刪除路線失敗: {str(e)}")

@app.post("/Route_Stations", response_model=List[StationOut])
def get_route_stations(q: RouteStationsQuery):
    # --- 參數化查詢（你的 MySQL_Run 若支援 params，優先這個寫法） ---
    sql = "SELECT * FROM bus_route_stations WHERE route_id = %s"
    params = [q.route_id]
    if q.direction:
        sql += " AND direction = %s"
        params.append(q.direction)

    try:
        rows = MySQL_Run(sql, params)  # 若你的 MySQL_Run 不支援 params，就 fallback 用 f-string，但要小心注入
    except TypeError:
        # Fallback：有些自寫函式沒有 params 參數
        # 請務必確認 direction 的字串來源可信
        if q.direction:
            rows = MySQL_Run(f"SELECT * FROM bus_route_stations WHERE route_id = {int(q.route_id)} AND direction = '{q.direction}'")
        else:
            rows = MySQL_Run(f"SELECT * FROM bus_route_stations WHERE route_id = {int(q.route_id)}")

    columns = [c[0] for c in MySQL_Run("SHOW COLUMNS FROM bus_route_stations")]
    df = pd.DataFrame(rows, columns=columns)

    # --- 沒資料的處理（擇一：回404 或 回[]）---
    if df.empty:
        # 選擇一：回空陣列（前端好處理）
        return []
        # 選擇二：回 404
        # raise HTTPException(status_code=404, detail=f"route_id={q.route_id} 無站點資料")

    # --- 欄位名稱正規化（把 DB 欄位映射成 API 欄位）---
    col_map = {
        "station_name": "stop_name",
        "stop_name": "stop_name",
        "est_time": "eta_from_start",
        "eta_from_start": "eta_from_start",
        "order_no": "stop_order",
        "seq": "stop_order",
        # 你若有 station_id 欄位但不打算輸出，就不要映射
    }
    # 只 rename 存在的欄位，避免 KeyError
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # --- 型別防呆：數值、時間、NaN 轉換 ---
    # 經緯度
    if "latitude" in df.columns:
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    if "longitude" in df.columns:
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    # 到站時間 / 順序
    if "eta_from_start" in df.columns:
        df["eta_from_start"] = pd.to_numeric(df["eta_from_start"], errors="coerce").astype("Int64")
    if "stop_order" in df.columns:
        df["stop_order"] = pd.to_numeric(df["stop_order"], errors="coerce").astype("Int64")

    # created_at -> datetime（避免 pandas.Timestamp 造成驗證錯誤）
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce") \
            .apply(lambda x: x.to_pydatetime() if pd.notnull(x) else None)

    # 只保留我們要輸出的欄位（避免多餘欄位觸發驗證錯）
    desired_cols = [
        "route_id", "route_name", "direction", "stop_name",
        "latitude", "longitude", "eta_from_start", "stop_order", "created_at"
    ]
    keep_cols = [c for c in desired_cols if c in df.columns]
    df = df[keep_cols]

    # NaN -> None
    records = df.where(pd.notnull(df), None).to_dict(orient="records")

    # （可選）逐筆建模，能更早在後端發現資料異常
    data: List[StationOut] = [StationOut(**r) for r in records]
    return data

# ===== 路線站點管理 API =====
class StationCreate(BaseModel):
    route_id: int
    route_name: str
    direction: str
    stop_name: str
    latitude: float
    longitude: float
    stop_order: int
    eta_from_start: int
    address: Optional[str] = None
    
    # 新增：順序調整選項
    replace_existing: Optional[bool] = False
    auto_reorder: Optional[bool] = False

class StationUpdate(BaseModel):
    route_id: int
    route_name: str
    direction: str
    stop_name: str
    latitude: float
    longitude: float
    stop_order: int
    eta_from_start: int
    address: Optional[str] = None
    # optional 原始識別欄位（由前端提供），用於安全更新定位
    original_stop_name: Optional[str] = None
    original_stop_order: Optional[int] = None

# ===== XML 匯入相關模型 =====
class XMLStationData(BaseModel):
    stop_name: str
    latitude: float
    longitude: float
    stop_order: int
    eta_from_start: int = 0
    address: Optional[str] = None
    direction: str  # "去程" 或 "回程"

class XMLRouteData(BaseModel):
    route_name: str
    direction: str  # "單向" 或 "雙向"
    start_stop: Optional[str] = None
    end_stop: Optional[str] = None
    status: int = 1
    stations: List[XMLStationData]

class XMLImportPreview(BaseModel):
    """XML匯入預覽結果"""
    total_routes: int
    total_stations: int
    conflicts: List[Dict]
    warnings: List[str]
    success: bool
    message: str

class XMLImportOptions(BaseModel):
    """XML匯入選項"""
    overwrite_existing: bool = False  # 是否覆蓋現有路線
    auto_resolve_conflicts: bool = True  # 自動解決衝突
    skip_invalid_data: bool = True  # 跳過無效資料

@app.post("/api/route-stations/create")
def create_route_station(station: StationCreate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """創建新的路線站點 - 支援順序調整"""
    try:
        # 若前端未提供 route_name，嘗試以 route_id 去 bus_routes_total 查回
        if not station.route_name or str(station.route_name).strip() == '':
            try:
                rr = MySQL_Run("SELECT route_name FROM bus_routes_total WHERE route_id = %s", (station.route_id,))
                if rr and isinstance(rr, list) and len(rr) > 0 and isinstance(rr[0], dict):
                    station.route_name = rr[0].get('route_name') or station.route_name
            except Exception:
                pass

        # 檢查是否有特殊處理指令
        station_data = station.dict() if hasattr(station, 'dict') else station.__dict__
        replace_existing = station_data.get('replace_existing', False)
        auto_reorder = station_data.get('auto_reorder', False)
        
        # 調試信息
        print(f"調試: replace_existing={replace_existing}, auto_reorder={auto_reorder}")
        print(f"調試: station_data keys: {list(station_data.keys())}")

        if replace_existing:
            # 交換位置模式：先確保沒有衝突，再插入新站點
            try:
                # 查找目標位置的所有信息
                conflict_result = MySQL_Run(
                    """SELECT station_id, route_id, route_name, direction, stop_name, 
                           latitude, longitude, stop_order, eta_from_start, address
                       FROM bus_route_stations 
                       WHERE route_id = %s AND direction = %s AND stop_order = %s""",
                    (station.route_id, station.direction, station.stop_order)
                )
                
                if conflict_result:
                    conflict_station = conflict_result[0]
                    
                    # 找到最大順序並準備新位置
                    max_order_result = MySQL_Run(
                        "SELECT COALESCE(MAX(stop_order), 0) + 1 as next_order FROM bus_route_stations WHERE route_id = %s AND direction = %s",
                        (station.route_id, station.direction)
                    )
                    next_order = max_order_result[0]['next_order'] if max_order_result else station.stop_order + 1
                    
                    # 第一步：直接刪除衝突站點
                    MySQL_Run(
                        "DELETE FROM bus_route_stations WHERE station_id = %s",
                        (conflict_station['station_id'],)
                    )
                    
                    # 第二步：插入新站點到目標位置
                    MySQL_Run(
                        """INSERT INTO bus_route_stations 
                           (route_id, route_name, direction, stop_name, latitude, longitude, stop_order, eta_from_start, address)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (station.route_id, station.route_name, station.direction, station.stop_name,
                         station.latitude, station.longitude, station.stop_order, station.eta_from_start, station.address or "")
                    )
                    
                    # 第三步：重新插入原站點到新位置
                    MySQL_Run(
                        """INSERT INTO bus_route_stations 
                           (route_id, route_name, direction, stop_name, latitude, longitude, stop_order, eta_from_start, address)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (conflict_station['route_id'], conflict_station['route_name'], conflict_station['direction'], conflict_station['stop_name'],
                         conflict_station['latitude'], conflict_station['longitude'], next_order, conflict_station['eta_from_start'], conflict_station['address'] or "")
                    )
                    
                    # 記錄操作歷史（使用正確的枚舉值）
                    MySQL_Run(
                        """INSERT INTO station_order_history 
                           (route_id, direction, operation_type, old_order, new_order, station_name, operator_id)
                           VALUES (%s, %s, 'UPDATE', %s, %s, %s, %s)""",
                        (station.route_id, station.direction, conflict_station['stop_order'], 
                         next_order, conflict_station['stop_name'], current_user.admin_id)
                    )
                    
                    # 記錄新增歷史
                    MySQL_Run(
                        """INSERT INTO station_order_history 
                           (route_id, direction, operation_type, new_order, station_name, operator_id)
                           VALUES (%s, %s, 'INSERT', %s, %s, %s)""",
                        (station.route_id, station.direction, station.stop_order, station.stop_name, current_user.admin_id)
                    )
                    
                    # 交換完成，直接返回，不執行後續的一般插入邏輯
                    return {"message": "站點交換成功", "ok": True}
                    
            except Exception as e:
                print(f"交換位置失敗: {e}")
                raise HTTPException(status_code=500, detail=f"交換位置失敗: {str(e)}")

        elif auto_reorder:
            # 自動調整模式：安全地將後續站點順序 +1
            try:
                # 先獲取需要調整的站點列表（從大到小順序，避免約束衝突）
                stations_to_update = MySQL_Run(
                    """SELECT station_id, stop_order FROM bus_route_stations 
                       WHERE route_id = %s AND direction = %s AND stop_order >= %s
                       ORDER BY stop_order DESC""",
                    (station.route_id, station.direction, station.stop_order)
                )
                
                # 從最大順序開始逐個更新（避免中間狀態違反約束）
                for station_to_update in stations_to_update:
                    MySQL_Run(
                        "UPDATE bus_route_stations SET stop_order = %s WHERE station_id = %s",
                        (station_to_update['stop_order'] + 1, station_to_update['station_id'])
                    )
                
                # 記錄批次調整歷史
                MySQL_Run(
                    """INSERT INTO station_order_history 
                       (route_id, direction, operation_type, old_order, new_order, station_name, operator_id)
                       VALUES (%s, %s, 'REORDER', %s, NULL, 'BATCH_ADJUSTMENT', %s)""",
                    (station.route_id, station.direction, station.stop_order, current_user.admin_id)
                )
                
                # 現在插入新站點到已調整的位置
                MySQL_Run(
                    """INSERT INTO bus_route_stations 
                       (route_id, route_name, direction, stop_name, latitude, longitude, stop_order, eta_from_start, address)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (station.route_id, station.route_name, station.direction, station.stop_name,
                     station.latitude, station.longitude, station.stop_order, station.eta_from_start, station.address or "")
                )
                
                # 記錄新增歷史
                MySQL_Run(
                    """INSERT INTO station_order_history 
                       (route_id, direction, operation_type, new_order, station_name, operator_id)
                       VALUES (%s, %s, 'INSERT', %s, %s, %s)""",
                    (station.route_id, station.direction, station.stop_order, station.stop_name, current_user.admin_id)
                )
                
                # 插入調整完成，直接返回，不執行後續的一般插入邏輯
                return {"message": "站點插入調整成功", "ok": True}
            except Exception as e:
                print(f"自動調整失敗: {e}")
                raise HTTPException(status_code=500, detail=f"自動調整失敗: {str(e)}")

        # 插入新站點
        sql = """
        INSERT INTO bus_route_stations 
        (route_id, route_name, direction, stop_name, latitude, longitude, stop_order, eta_from_start, address)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            station.route_id,
            station.route_name,
            station.direction,
            station.stop_name,
            station.latitude,
            station.longitude,
            station.stop_order,
            station.eta_from_start,
            station.address or ""
        )
        MySQL_Run(sql, params)
        
        # 記錄新增歷史 (使用正確的欄位名稱)
        MySQL_Run(
            """INSERT INTO station_order_history 
               (route_id, direction, operation_type, new_order, station_name, operator_id)
               VALUES (%s, %s, 'INSERT', %s, %s, %s)""",
            (station.route_id, station.direction, station.stop_order, station.stop_name, current_user.admin_id)
        )
        
        return {"message": "站點創建成功", "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"創建站點失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"創建站點失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"創建站點失敗: {str(e)}")

@app.put("/api/route-stations/update")
def update_route_station(station: StationUpdate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """更新路線站點：允許自由改順序，後端自動重排避免衝突。"""
    try:
        # 支援前端傳 original_stop_order 或 original_stop_name 作為原始定位值
        orig_order = getattr(station, 'original_stop_order', None)
        orig_name = getattr(station, 'original_stop_name', None)

        # 若更改 stop_order：採用列表移動演算法以保持唯一性
        try:
            if orig_order is not None and station.stop_order is not None and int(station.stop_order) != int(orig_order):
                new_order = int(station.stop_order)
                old_order = int(orig_order)
                if new_order < old_order:
                    # 上移：new..old-1 全部 +1
                    MySQL_Run(
                        """
                        UPDATE bus_route_stations
                        SET stop_order = stop_order + 1
                        WHERE route_id = %s AND stop_order >= %s AND stop_order < %s
                        """,
                        (station.route_id, new_order, old_order)
                    )
                else:
                    # 下移：old+1..new 全部 -1
                    MySQL_Run(
                        """
                        UPDATE bus_route_stations
                        SET stop_order = stop_order - 1
                        WHERE route_id = %s AND stop_order <= %s AND stop_order > %s
                        """,
                        (station.route_id, new_order, old_order)
                    )
        except Exception:
            # 重排失敗不阻斷
            pass

        if orig_order is not None:
            where_sql = "WHERE route_id = %s AND stop_order = %s"
            where_params = (station.route_id, orig_order)
        elif orig_name:
            where_sql = "WHERE route_id = %s AND stop_name = %s"
            where_params = (station.route_id, orig_name)
        else:
            # 最後回退使用 route_id + stop_order（使用者在表單未提供 original_* 時）
            where_sql = "WHERE route_id = %s AND stop_order = %s"
            where_params = (station.route_id, station.stop_order)

        sql = f"""
        UPDATE bus_route_stations
        SET route_name = %s, direction = %s,
            stop_name = %s, latitude = %s,
            longitude = %s, stop_order = %s,
            eta_from_start = %s,
            address = %s
        {where_sql}
        """

        params = (
            station.route_name,
            station.direction,
            station.stop_name,
            station.latitude,
            station.longitude,
            station.stop_order,
            station.eta_from_start,
            station.address or ""
        ) + tuple(where_params)

        MySQL_Run(sql, params)
        return {"message": "站點更新成功", "ok": True}
    except Exception as e:
        print(f"更新站點失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新站點失敗: {str(e)}")

@app.delete("/api/route-stations/delete")
def delete_route_station(route_id: int, stop_order: int, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """刪除路線站點"""
    try:
        # 先檢查記錄是否存在（參數化）
        check_sql = "SELECT COUNT(*) as count FROM bus_route_stations WHERE route_id = %s AND stop_order = %s"
        check_result = MySQL_Run(check_sql, (route_id, stop_order))

        if not check_result or check_result[0].get('count', 0) == 0:
            raise HTTPException(status_code=404, detail="找不到要刪除的站點")

        sql = "DELETE FROM bus_route_stations WHERE route_id = %s AND stop_order = %s"
        MySQL_Run(sql, (route_id, stop_order))
        return {"message": "站點刪除成功", "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"刪除站點失敗: {str(e)}")  # 加入日誌
        raise HTTPException(status_code=500, detail=f"刪除站點失敗: {str(e)}")

@app.get("/api/routes")
def get_all_routes():
    """獲取所有路線（從 bus_route_stations 表中提取）"""
    try:
        # 從 bus_route_stations 表中獲取所有不同的路線名稱和對應的 route_id
        rows = MySQL_Run("""
            SELECT DISTINCT route_id, route_name 
            FROM bus_route_stations 
            ORDER BY route_id
        """)
        
        # 如果某些路線沒有 route_id，我們給它們分配一個
        routes = []
        for row in rows:
            if row['route_id'] is None or row['route_id'] == '':
                # 為沒有 route_id 的路線分配一個基於名稱的 ID
                route_name = row['route_name']
                if route_name == '市民小巴-行動遊花蓮':
                    route_id = 4
                else:
                    # 為其他沒有 route_id 的路線生成 ID
                    route_id = hash(route_name) % 10000  # 簡單的雜湊函數
                routes.append({'route_id': route_id, 'route_name': route_name})
            else:
                routes.append({'route_id': row['route_id'], 'route_name': row['route_name']})
        
        return {"routes": routes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取路線失敗: {str(e)}")

@app.get("/api/route-stations")
def get_route_stations(
    route_id: Optional[int] = None,
    direction: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    order: Literal['asc', 'desc'] = 'desc'
):
    """獲取篩選後的路線站點（支援分頁和搜尋）"""
    try:
        # 建構查詢條件
        conditions = []
        params = []
        
        if route_id:
            conditions.append("route_id = %s")
            params.append(route_id)
        
        if direction:
            conditions.append("direction = %s")
            params.append(direction)
        
        if search:
            conditions.append("(stop_name LIKE %s OR address LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        # 建構 WHERE 子句
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 計算總數
        count_sql = f"SELECT COUNT(*) as total FROM bus_route_stations WHERE {where_clause}"
        count_result = MySQL_Run(count_sql, tuple(params) if params else ())
        total = count_result[0]['total'] if count_result else 0
        
        # 計算分頁
        offset = (page - 1) * page_size
        
        # 建構主要查詢
        order_value = (order or 'desc').lower()
        if order_value not in ('asc', 'desc'):
            order_value = 'desc'
        order_clause = 'DESC' if order_value == 'desc' else 'ASC'
        sql = f"""
        SELECT * FROM bus_route_stations 
        WHERE {where_clause} 
        ORDER BY route_id {order_clause}, stop_order 
        LIMIT %s OFFSET %s
        """
        
        params.extend([page_size, offset])
        rows = MySQL_Run(sql, tuple(params))
        
        return {
            "stations": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    except Exception as e:
        print(f"獲取站點失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"獲取站點失敗: {str(e)}")

@app.get("/api/route-stations/check-conflict")
def check_station_order_conflict(
    route_id: int,
    direction: str,
    stop_order: int,
    current_user: AdminUser = Depends(get_current_user)
):
    """檢查站點順序是否衝突"""
    try:
        sql = """
            SELECT station_id, stop_name, stop_order 
            FROM bus_route_stations 
            WHERE route_id = %s AND direction = %s AND stop_order = %s
        """
        
        result = MySQL_Run(sql, (route_id, direction, stop_order))
        
        if result:
            return {
                "hasConflict": True,
                "conflictStation": result[0]
            }
        else:
            return {
                "hasConflict": False,
                "conflictStation": None
            }
            
    except Exception as e:
        print("check_station_order_conflict error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/route-stations/suggest-order")
def suggest_station_order(
    route_id: int,
    direction: str,
    current_user: AdminUser = Depends(get_current_user)
):
    """建議下一個可用的站點順序"""
    try:
        sql = """
            SELECT COALESCE(MAX(stop_order), 0) + 1 as suggested_order
            FROM bus_route_stations 
            WHERE route_id = %s AND direction = %s
        """
        
        result = MySQL_Run(sql, (route_id, direction))
        suggested_order = result[0]['suggested_order'] if result else 1
        
        return {
            "suggestedOrder": suggested_order
        }
            
    except Exception as e:
        print("suggest_station_order error:", e)
        raise HTTPException(status_code=500, detail=str(e))

# =================  Reservation APIs  =================
def _ensure_admin_or_super(db: Session, current_user: AdminUser):
    role = get_role_by_id(db, current_user.role_id)
    if not role or (role.role_name or '').lower() not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail='沒有權限執行此操作')

@app.get("/api/reservations")
def list_reservations(
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    payment_status: Optional[str] = None,
    review_status: Optional[str] = None,
    dispatch_status: Optional[str] = None,
    order: Literal['asc', 'desc'] = 'desc'
):
    try:
        cond = []
        params: List = []
        if search:
            cond.append("(booking_start_station_name LIKE %s OR booking_end_station_name LIKE %s OR CAST(user_id AS CHAR) LIKE %s)")
            s = f"%{search}%"
            params.extend([s, s, s])
        if payment_status:
            cond.append("payment_status = %s")
            params.append(payment_status)
        if review_status:
            cond.append("review_status = %s")
            params.append(review_status)
        if dispatch_status:
            cond.append("dispatch_status = %s")
            params.append(dispatch_status)

        where_clause = " AND ".join(cond) if cond else "1=1"

        cnt_sql = f"SELECT COUNT(*) as total FROM reservation WHERE {where_clause}"
        total = MySQL_Run(cnt_sql, tuple(params))[0]['total']

        offset = (page - 1) * limit
        order_value = (order or 'desc').lower()
        if order_value not in ('asc', 'desc'):
            order_value = 'desc'
        order_clause = 'DESC' if order_value == 'desc' else 'ASC'
        list_sql = f"""
            SELECT reservation_id, user_id, booking_time, booking_number,
                   booking_start_station_name, booking_end_station_name,
                   payment_method, payment_record, payment_status,
                   review_status, dispatch_status, reservation_status,
                   created_at, updated_at
            FROM reservation
            WHERE {where_clause}
            ORDER BY reservation_id {order_clause}
            LIMIT %s OFFSET %s
        """
        rows = MySQL_Run(list_sql, tuple(params + [limit, offset]))
        return {
            "success": True,
            "data": rows,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        print("list_reservations error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reservations")
def create_reservation(payload: ReservationCreate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_admin_or_super(db, current_user)
    try:
        cols = []
        vals = []
        params: List = []
        data = payload.dict(exclude_unset=True)
        for k in [
            'user_id','booking_time','booking_number','booking_start_station_name',
            'booking_end_station_name','payment_method','payment_record',
            'payment_status','review_status','dispatch_status']:
            if k in data and data[k] is not None:
                cols.append(k)
                vals.append('%s')
                params.append(data[k])
        if not cols:
            raise HTTPException(status_code=400, detail='缺少必要欄位')
        sql = f"INSERT INTO reservation ({', '.join(cols)}) VALUES ({', '.join(vals)})"
        res = MySQL_Run(sql, tuple(params))
        new_id = None
        if isinstance(res, dict) and res.get('lastrowid'):
            new_id = int(res['lastrowid'])
        return {"success": True, "reservation_id": new_id}
    except Exception as e:
        print("create_reservation error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/reservations/{reservation_id}")
def update_reservation(reservation_id: int, payload: ReservationUpdate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_admin_or_super(db, current_user)
    try:
        data = payload.dict(exclude_unset=True)
        if not data:
            return {"success": True, "message": "沒有變更"}
        sets = []
        params: List = []
        for k, v in data.items():
            sets.append(f"{k} = %s")
            params.append(v)
        params.append(reservation_id)
        sql = f"UPDATE reservation SET {', '.join(sets)} WHERE reservation_id = %s"
        MySQL_Run(sql, tuple(params))
        return {"success": True}
    except Exception as e:
        print("update_reservation error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/reservations/{reservation_id}")
def delete_reservation(reservation_id: int, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_admin_or_super(db, current_user)
    try:
        chk = MySQL_Run("SELECT COUNT(*) as c FROM reservation WHERE reservation_id = %s", (reservation_id,))
        if not chk or chk[0]['c'] == 0:
            raise HTTPException(status_code=404, detail='預約不存在')
        MySQL_Run("DELETE FROM reservation WHERE reservation_id = %s", (reservation_id,))
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print("delete_reservation error:", e)
        raise HTTPException(status_code=500, detail=str(e))

def _serialize_member(row: dict):
    data = dict(row)
    for key in ('created_at', 'updated_at', 'last_login'):
        value = data.get(key)
        if value is not None and hasattr(value, 'isoformat'):
            data[key] = value.isoformat()
    return data

@app.get("/api/members")
def list_members(
    page: int = 1,
    limit: int = 10,
    search: Optional[str] = None,
    status: Optional[str] = None,
    order: Literal['asc', 'desc'] = 'desc'
):
    try:
        page = max(page, 1)
        limit = max(limit, 1)
        conditions: List[str] = []
        params: List = []
        if status:
            conditions.append('status = %s')
            params.append(status)
        if search:
            keyword = f"%{search}%"
            conditions.append('(CAST(user_id AS CHAR) LIKE %s OR username LIKE %s OR line_id LIKE %s OR email LIKE %s OR phone LIKE %s)')
            params.extend([keyword, keyword, keyword, keyword, keyword])
        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        count_sql = f"SELECT COUNT(*) as total FROM users WHERE {where_clause}"
        count_res = MySQL_Run(count_sql, tuple(params) if params else ())
        total = count_res[0]['total'] if count_res else 0
        offset = (page - 1) * limit
        order_value = (order or 'desc').lower()
        if order_value not in ('asc', 'desc'):
            order_value = 'desc'
        list_sql = f"""
            SELECT user_id, username, line_id, email, phone, status, reservation_status,
                   preferences, privacy_settings, created_at, updated_at, last_login
            FROM users
            WHERE {where_clause}
            ORDER BY user_id {'DESC' if order_value == 'desc' else 'ASC'}
            LIMIT %s OFFSET %s
        """
        rows = MySQL_Run(list_sql, tuple(params + [limit, offset]))
        return {
            'success': True,
            'users': [_serialize_member(r) for r in rows],
            'total': total,
            'page': page,
            'limit': limit,
            'total_pages': (total + limit - 1) // limit
        }
    except Exception as e:
        print('list_members error:', e)
        raise HTTPException(status_code=500, detail=str(e))

def _serialize_car_resource(row: dict):
    data = dict(row)
    for key in ('commission_date', 'last_service_date'):
        value = data.get(key)
        if value is not None and hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data

@app.get("/api/cars")
def list_cars(
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
    order: Literal['asc', 'desc'] = 'desc'
):
    try:
        page = max(page, 1)
        limit = max(limit, 1)
        valid_status = {'service', 'paused', 'maintenance', 'retired'}
        conditions: List[str] = []
        params: List = []
        if search:
            conditions.append("car_licence LIKE %s")
            params.append(f"%{search}%")
        if status:
            if status not in valid_status:
                raise HTTPException(status_code=400, detail='無效的車輛狀態')
            conditions.append("car_status = %s")
            params.append(status)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        cnt_sql = f"SELECT COUNT(*) as total FROM car_resource WHERE {where_clause}"
        cnt_res = MySQL_Run(cnt_sql, tuple(params))
        total = cnt_res[0]['total'] if cnt_res else 0
        offset = (page - 1) * limit
        order_value = (order or 'desc').lower()
        if order_value not in ('asc', 'desc'):
            order_value = 'desc'
        order_clause = 'DESC' if order_value == 'desc' else 'ASC'
        list_sql = f"""
            SELECT car_id, car_licence, max_passengers, car_status, commission_date, last_service_date
            FROM car_resource
            WHERE {where_clause}
            ORDER BY car_id {order_clause}
            LIMIT %s OFFSET %s
        """
        rows = MySQL_Run(list_sql, tuple(params + [limit, offset]))
        return {
            "success": True,
            "data": [_serialize_car_resource(r) for r in rows],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print("list_cars error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cars")
def create_car_resource(payload: CarResourceCreate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_admin_or_super(db, current_user)
    try:
        data = payload.dict(exclude_unset=True)
        licence = (data.get('car_licence') or '').strip()
        if not licence:
            raise HTTPException(status_code=400, detail='車牌號碼不可為空')
        data['car_licence'] = licence
        if data.get('max_passengers') is not None and data['max_passengers'] < 1:
            raise HTTPException(status_code=400, detail='可載人數必須大於 0')
        columns: List[str] = []
        placeholders: List[str] = []
        params: List = []
        for key in ['car_licence','max_passengers','car_status','commission_date','last_service_date']:
            if key in data and data[key] is not None:
                columns.append(key)
                placeholders.append('%s')
                params.append(data[key])
        if not columns:
            raise HTTPException(status_code=400, detail='缺少必要欄位')
        sql = f"INSERT INTO car_resource ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        res = MySQL_Run(sql, tuple(params))
        new_id = None
        if isinstance(res, dict) and res.get('lastrowid'):
            new_id = int(res['lastrowid'])
        return {"success": True, "car_id": new_id}
    except HTTPException:
        raise
    except Exception as e:
        print("create_car_resource error:", e)
        msg = str(e)
        if 'Duplicate entry' in msg and 'car_licence' in msg:
            raise HTTPException(status_code=400, detail='車牌號碼已存在')
        raise HTTPException(status_code=500, detail=msg)

@app.put("/api/cars/{car_id}")
def update_car_resource(car_id: int, payload: CarResourceUpdate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_admin_or_super(db, current_user)
    try:
        data = payload.dict(exclude_unset=True)
        if 'car_licence' in data and data['car_licence'] is not None:
            data['car_licence'] = data['car_licence'].strip()
            if not data['car_licence']:
                raise HTTPException(status_code=400, detail='車牌號碼不可為空')
        if 'max_passengers' in data and data['max_passengers'] is not None and data['max_passengers'] < 1:
            raise HTTPException(status_code=400, detail='可載人數必須大於 0')
        if not data:
            return {"success": True, "message": "沒有變更"}
        sets: List[str] = []
        params: List = []
        for key, value in data.items():
            sets.append(f"{key} = %s")
            params.append(value)
        params.append(car_id)
        sql = f"UPDATE car_resource SET {', '.join(sets)} WHERE car_id = %s"
        MySQL_Run(sql, tuple(params))
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print("update_car_resource error:", e)
        msg = str(e)
        if 'Duplicate entry' in msg and 'car_licence' in msg:
            raise HTTPException(status_code=400, detail='車牌號碼已存在')
        raise HTTPException(status_code=500, detail=msg)

@app.delete("/api/cars/{car_id}")
def delete_car_resource(car_id: int, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_admin_or_super(db, current_user)
    try:
        chk = MySQL_Run("SELECT COUNT(*) as c FROM car_resource WHERE car_id = %s", (car_id,))
        if not chk or chk[0]['c'] == 0:
            raise HTTPException(status_code=404, detail='車輛不存在')
        MySQL_Run("DELETE FROM car_resource WHERE car_id = %s", (car_id,))
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print("delete_car_resource error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cars/stats")
def get_car_stats():
    try:
        total_res = MySQL_Run("SELECT COUNT(*) as total FROM car_resource")
        total = total_res[0]['total'] if total_res else 0

        status_rows = MySQL_Run("SELECT car_status, COUNT(*) as count FROM car_resource GROUP BY car_status")
        status_counts = {key: 0 for key in ['service', 'paused', 'maintenance', 'retired']}
        for row in status_rows:
            key = row.get('car_status')
            if key in status_counts:
                status_counts[key] = row.get('count', 0)

        new_rows = MySQL_Run("""
            SELECT COUNT(*) AS cnt
            FROM car_resource
            WHERE commission_date IS NOT NULL
              AND DATE_FORMAT(commission_date, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m')
        """)
        new_this_month = new_rows[0]['cnt'] if new_rows else 0

        return {
            'success': True,
            'data': {
                'total': total,
                'new_this_month': new_this_month,
                'status_counts': status_counts
            }
        }
    except Exception as e:
        print('get_car_stats error:', e)
        raise HTTPException(status_code=500, detail=str(e))

# ========== 會員管理：權限保護 ==========
@app.post("/Create_users")
def create_user(user: UserCreate, db: Session = Depends(get_db), current_user: AdminUser = Depends(get_current_user)):
    # 僅 super_admin 與 admin 可新增會員；dispatcher 禁止
    role = get_role_by_id(db, current_user.role_id)
    if not role or role.role_name not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="沒有權限新增會員")

    user_data = user.dict(exclude_unset=True)
    
    # 處理密碼雜湊
    if user_data.get('password') and isinstance(user_data['password'], str) and user_data['password'].strip():
        hashed_password = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt())
        user_data['password'] = hashed_password.decode('utf-8')
    else:
        user_data['password'] = None
    
    optional_fields = ['preferences', 'privacy_settings', 'reservation_status']
    for field in optional_fields:
        if field in user_data:
            if not user_data[field] or (isinstance(user_data[field], str) and not user_data[field].strip()):
                user_data[field] = None

    if not user_data.get('reservation_status') or user_data.get('reservation_status') == 'None':
        user_data['reservation_status'] = 'no_reservation'

    conflict_fields = []
    if user_data.get('username') and str(user_data['username']).strip():
        exist = db.query(User).filter(User.username == str(user_data['username']).strip()).first()
        if exist:
            conflict_fields.append('username')
    if user_data.get('phone') and str(user_data['phone']).strip():
        exist = db.query(User).filter(User.phone == str(user_data['phone']).strip()).first()
        if exist:
            conflict_fields.append('phone')
    if user_data.get('email') and str(user_data['email']).strip():
        exist = db.query(User).filter(User.email == str(user_data['email']).strip()).first()
        if exist:
            conflict_fields.append('email')
    if user_data.get('line_id') and str(user_data['line_id']).strip():
        exist = db.query(User).filter(User.line_id == str(user_data['line_id']).strip()).first()
        if exist:
            conflict_fields.append('line_id')

    if conflict_fields:
        raise HTTPException(status_code=409, detail=f"以下欄位已存在: {', '.join(conflict_fields)}")
    
    new_user = User(**user_data)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"user_id": new_user.user_id, "message": "用戶建立成功"}

@app.put("/users/{user_id}")
def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db), current_user: AdminUser = Depends(get_current_user)):
    role = get_role_by_id(db, current_user.role_id)
    if not role or role.role_name not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="沒有權限更新會員")

    user_data = user.dict(exclude_unset=True)
    target = db.query(User).filter(User.user_id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用戶不存在")

    if 'password' in user_data and user_data['password']:
        hashed_password = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt())
        user_data['password'] = hashed_password.decode('utf-8')
    elif 'password' in user_data:
        user_data['password'] = target.password

    # 清理空白字串
    for k in ['preferences', 'privacy_settings']:
        if k in user_data and isinstance(user_data[k], str) and not user_data[k].strip():
            user_data[k] = None

    for key, value in user_data.items():
        setattr(target, key, value)
    try:
        target.updated_at = get_taiwan_datetime()
    except Exception:
        pass
    db.commit()
    return {"message": "用戶更新成功"}

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: AdminUser = Depends(get_current_user)):
    role = get_role_by_id(db, current_user.role_id)
    if not role or role.role_name not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="沒有權限刪除會員")

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用戶不存在")
    db.delete(user)
    db.commit()
    return {"message": "用戶刪除成功"}

# ===== XML 匯入功能 API =====
def parse_xml_content(xml_content: str) -> List[XMLRouteData]:
    """解析XML內容並轉換為路線資料"""
    try:
        root = ET.fromstring(xml_content)
        routes = []
        
        # 支援多種XML格式
        route_elements = root.findall('.//route')
        if not route_elements:
            # 嘗試其他可能的結構
            route_elements = root.findall('./route') or root.findall('route')
        
        for route_elem in route_elements:
            # 解析路線基本資訊
            route_name = route_elem.find('route_name')
            if route_name is None or not route_name.text:
                continue
                
            direction = route_elem.find('direction')
            direction_text = direction.text if direction is not None else "雙向"
            
            start_stop = route_elem.find('start_stop')
            start_stop_text = start_stop.text if start_stop is not None else None
            
            end_stop = route_elem.find('end_stop')
            end_stop_text = end_stop.text if end_stop is not None else None
            
            status = route_elem.find('status')
            status_value = int(status.text) if status is not None and status.text.isdigit() else 1
            
            # 解析站點資訊
            stations = []
            station_elements = route_elem.findall('.//station')
            
            for station_elem in station_elements:
                try:
                    stop_name = station_elem.find('stop_name')
                    if stop_name is None or not stop_name.text:
                        continue
                    
                    latitude = station_elem.find('latitude')
                    longitude = station_elem.find('longitude')
                    stop_order = station_elem.find('stop_order')
                    
                    if latitude is None or longitude is None or stop_order is None:
                        continue
                    
                    # 取得方向資訊（優先從屬性，其次從元素）
                    station_direction = station_elem.get('direction')
                    if not station_direction:
                        dir_elem = station_elem.find('direction')
                        station_direction = dir_elem.text if dir_elem is not None else "去程"
                    
                    eta_elem = station_elem.find('eta_from_start')
                    eta_value = int(eta_elem.text) if eta_elem is not None and eta_elem.text.isdigit() else 0
                    
                    address_elem = station_elem.find('address')
                    address_value = address_elem.text if address_elem is not None else None
                    
                    station_data = XMLStationData(
                        stop_name=stop_name.text.strip(),
                        latitude=float(latitude.text),
                        longitude=float(longitude.text),
                        stop_order=int(stop_order.text),
                        eta_from_start=eta_value,
                        address=address_value,
                        direction=station_direction
                    )
                    stations.append(station_data)
                    
                except (ValueError, AttributeError) as e:
                    print(f"跳過無效站點資料: {e}")
                    continue
            
            if stations:  # 只有當有有效站點時才添加路線
                route_data = XMLRouteData(
                    route_name=route_name.text.strip(),
                    direction=direction_text,
                    start_stop=start_stop_text,
                    end_stop=end_stop_text,
                    status=status_value,
                    stations=stations
                )
                routes.append(route_data)
        
        return routes
        
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"XML格式錯誤: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析XML失敗: {str(e)}")

def validate_xml_route_data(route_data: XMLRouteData) -> List[str]:
    """驗證單一路線資料並返回警告訊息"""
    warnings = []
    
    # 檢查路線名稱
    if not route_data.route_name or route_data.route_name.strip() == "":
        warnings.append("路線名稱不能為空")
    
    # 檢查方向
    if route_data.direction not in ["單向", "雙向"]:
        warnings.append(f"路線方向 '{route_data.direction}' 無效，應為 '單向' 或 '雙向'")
    
    # 檢查站點
    if not route_data.stations:
        warnings.append("路線沒有站點資料")
    else:
        station_orders = {}
        for station in route_data.stations:
            # 檢查站點方向
            if station.direction not in ["去程", "回程"]:
                warnings.append(f"站點 '{station.stop_name}' 方向 '{station.direction}' 無效，應為 '去程' 或 '回程'")
            
            # 檢查座標範圍（台灣地區）
            if not (21.5 <= station.latitude <= 25.5):
                warnings.append(f"站點 '{station.stop_name}' 緯度 {station.latitude} 超出台灣範圍")
            if not (119.5 <= station.longitude <= 122.5):
                warnings.append(f"站點 '{station.stop_name}' 經度 {station.longitude} 超出台灣範圍")
            
            # 檢查順序重複
            direction_key = f"{station.direction}_{station.stop_order}"
            if direction_key in station_orders:
                warnings.append(f"站點順序衝突：{station.direction} 第 {station.stop_order} 站重複")
            station_orders[direction_key] = station.stop_name
    
    return warnings

@app.post("/api/xml/upload")
async def upload_xml_file(file: UploadFile = File(...), current_user: AdminUser = Depends(get_current_user)):
    """上傳XML檔案並回傳解析結果"""
    try:
        # 檢查檔案類型
        if not file.filename.lower().endswith('.xml'):
            raise HTTPException(status_code=400, detail="請上傳XML檔案")
        
        # 讀取檔案內容
        content = await file.read()
        xml_content = content.decode('utf-8')
        
        # 解析XML
        routes = parse_xml_content(xml_content)
        
        if not routes:
            raise HTTPException(status_code=400, detail="XML檔案中沒有找到有效的路線資料")
        
        # 驗證資料
        all_warnings = []
        total_stations = 0
        
        for route in routes:
            warnings = validate_xml_route_data(route)
            if warnings:
                all_warnings.extend([f"路線 '{route.route_name}': {w}" for w in warnings])
            total_stations += len(route.stations)
        
        return {
            "success": True,
            "message": "XML檔案解析成功",
            "total_routes": len(routes),
            "total_stations": total_stations,
            "warnings": all_warnings,
            "routes": [route.dict() for route in routes]
        }
        
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="檔案編碼錯誤，請確保使用UTF-8編碼")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"處理檔案失敗: {str(e)}")

@app.post("/api/xml/preview")
def preview_xml_import(routes_data: List[XMLRouteData], current_user: AdminUser = Depends(get_current_user)):
    """預覽XML匯入結果，檢查衝突"""
    try:
        conflicts = []
        warnings = []
        total_stations = 0
        
        for route_data in routes_data:
            # 驗證路線資料
            route_warnings = validate_xml_route_data(route_data)
            if route_warnings:
                warnings.extend([f"路線 '{route_data.route_name}': {w}" for w in route_warnings])
            
            # 檢查路線名稱是否已存在
            existing_route = MySQL_Run("SELECT route_id, route_name FROM bus_routes_total WHERE route_name = %s", (route_data.route_name,))
            if existing_route:
                conflicts.append({
                    "type": "route_exists",
                    "route_name": route_data.route_name,
                    "existing_route_id": existing_route[0]["route_id"],
                    "message": f"路線 '{route_data.route_name}' 已存在"
                })
            
            total_stations += len(route_data.stations)
        
        return XMLImportPreview(
            total_routes=len(routes_data),
            total_stations=total_stations,
            conflicts=conflicts,
            warnings=warnings,
            success=len(conflicts) == 0,
            message="預覽完成" if len(conflicts) == 0 else f"發現 {len(conflicts)} 個衝突"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"預覽失敗: {str(e)}")

@app.post("/api/xml/import")
def import_xml_data(request_data: dict, current_user: AdminUser = Depends(get_current_user)):
    """執行XML資料匯入"""
    try:
        # 從請求中提取資料
        routes_data = [XMLRouteData(**route) for route in request_data.get('routes_data', [])]
        options_dict = request_data.get('options', {})
        options = XMLImportOptions(**options_dict)
        
        import_results = []
        total_imported_routes = 0
        total_imported_stations = 0
        errors = []
        
        for route_data in routes_data:
            try:
                # 檢查路線是否已存在
                existing_route = MySQL_Run("SELECT route_id FROM bus_routes_total WHERE route_name = %s", (route_data.route_name,))
                
                route_id = None
                if existing_route:
                    if options.overwrite_existing:
                        # 刪除現有路線和站點
                        route_id = existing_route[0]["route_id"]
                        MySQL_Run("DELETE FROM bus_route_stations WHERE route_id = %s", (route_id,))
                        MySQL_Run("DELETE FROM bus_routes_total WHERE route_id = %s", (route_id,))
                    else:
                        errors.append(f"路線 '{route_data.route_name}' 已存在，跳過匯入")
                        continue
                
                # 建立路線
                route_cols = ['route_name', 'stop_count', 'direction', 'start_stop', 'end_stop', 'status']
                route_values = [
                    route_data.route_name,
                    len(route_data.stations),
                    route_data.direction,
                    route_data.start_stop,
                    route_data.end_stop,
                    route_data.status
                ]
                
                placeholders = ', '.join(['%s'] * len(route_values))
                sql = f"INSERT INTO bus_routes_total ({', '.join(route_cols)}) VALUES ({placeholders})"
                result = MySQL_Run(sql, route_values)
                
                if isinstance(result, dict) and 'lastrowid' in result:
                    route_id = result['lastrowid']
                else:
                    # 如果沒有取得lastrowid，查詢路線ID
                    route_query = MySQL_Run("SELECT route_id FROM bus_routes_total WHERE route_name = %s", (route_data.route_name,))
                    if route_query:
                        route_id = route_query[0]["route_id"]
                
                if not route_id:
                    errors.append(f"建立路線 '{route_data.route_name}' 失敗")
                    continue
                
                # 建立站點
                stations_imported = 0
                for station in route_data.stations:
                    try:
                        station_cols = ['route_id', 'route_name', 'direction', 'stop_name', 'latitude', 'longitude', 'stop_order', 'eta_from_start', 'address']
                        station_values = [
                            route_id,
                            route_data.route_name,
                            station.direction,
                            station.stop_name,
                            station.latitude,
                            station.longitude,
                            station.stop_order,
                            station.eta_from_start,
                            station.address
                        ]
                        
                        station_placeholders = ', '.join(['%s'] * len(station_values))
                        station_sql = f"INSERT INTO bus_route_stations ({', '.join(station_cols)}) VALUES ({station_placeholders})"
                        MySQL_Run(station_sql, station_values)
                        stations_imported += 1
                        
                    except Exception as station_error:
                        if options.skip_invalid_data:
                            errors.append(f"站點 '{station.stop_name}' 匯入失敗: {str(station_error)}")
                        else:
                            raise station_error
                
                import_results.append({
                    "route_name": route_data.route_name,
                    "route_id": route_id,
                    "stations_imported": stations_imported,
                    "success": True
                })
                total_imported_routes += 1
                total_imported_stations += stations_imported
                
            except Exception as route_error:
                if options.skip_invalid_data:
                    errors.append(f"路線 '{route_data.route_name}' 匯入失敗: {str(route_error)}")
                    import_results.append({
                        "route_name": route_data.route_name,
                        "success": False,
                        "error": str(route_error)
                    })
                else:
                    raise route_error
        
        return {
            "success": True,
            "message": f"匯入完成：{total_imported_routes} 條路線，{total_imported_stations} 個站點",
            "total_imported_routes": total_imported_routes,
            "total_imported_stations": total_imported_stations,
            "results": import_results,
            "errors": errors
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"匯入失敗: {str(e)}")

# ========== 排班調度管理 API ==========

def _serialize_schedule(row: dict):
    """序列化排班資料"""
    return {
        "id": row.get("id"),
        "route_no": row.get("route_no"),
        "route_name": row.get("route_name"),  # 從JOIN取得
        "direction": row.get("direction"),
        "special_type": row.get("special_type"),
        "operation_status": row.get("operation_status"),
        "date": row.get("date").strftime("%Y-%m-%d") if row.get("date") else None,
        "departure_time": str(row.get("departure_time")) if row.get("departure_time") else None,
        "license_plate": row.get("license_plate"),
        "car_status": row.get("car_status"),  # 從car_resource JOIN取得
        "driver_name": row.get("driver_name"),
        "employee_id": row.get("employee_id")
    }

@app.get("/api/schedules")
def list_schedules(
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    route_no: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    operation_status: Optional[str] = None,
    sort: Optional[str] = 'date_desc',
    current_user: AdminUser = Depends(get_current_user)
):
    """取得排班列表"""
    try:
        conditions = []
        params = []
        
        # 搜尋條件
        if search:
            conditions.append("(rs.route_no LIKE %s OR rs.license_plate LIKE %s OR rs.driver_name LIKE %s OR rs.employee_id LIKE %s OR bt.route_name LIKE %s)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param, search_param, search_param])
        
        if route_no:
            conditions.append("rs.route_no = %s")
            params.append(route_no)
            
        if date_from:
            conditions.append("rs.date >= %s")
            params.append(date_from)
            
        if date_to:
            conditions.append("rs.date <= %s")
            params.append(date_to)
            
        if operation_status:
            conditions.append("rs.operation_status = %s")
            params.append(operation_status)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 計算總數
        count_sql = f"""
            SELECT COUNT(*) as total 
            FROM route_schedule rs
            LEFT JOIN bus_routes_total bt ON rs.route_no = bt.route_id
            WHERE {where_clause}
        """
        total = MySQL_Run(count_sql, tuple(params))[0]['total']
        
        # 取得資料
        offset = (page - 1) * limit
        
        # 排序邏輯
        order_clause = "rs.date DESC, rs.departure_time ASC"  # 預設排序
        if sort:
            if sort == 'date_asc':
                order_clause = "rs.date ASC, rs.departure_time ASC"
            elif sort == 'date_desc':
                order_clause = "rs.date DESC, rs.departure_time ASC"
            elif sort == 'departure_asc':
                order_clause = "rs.departure_time ASC, rs.date DESC"
            elif sort == 'departure_desc':
                order_clause = "rs.departure_time DESC, rs.date DESC"
            elif sort == 'route_asc':
                order_clause = "rs.route_no ASC, rs.date DESC"
            elif sort == 'route_desc':
                order_clause = "rs.route_no DESC, rs.date DESC"
        
        list_sql = f"""
            SELECT rs.*, bt.route_name, cr.car_status
            FROM route_schedule rs
            LEFT JOIN bus_routes_total bt ON rs.route_no = bt.route_id
            LEFT JOIN car_resource cr ON rs.license_plate = cr.car_licence
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """
        rows = MySQL_Run(list_sql, tuple(params + [limit, offset]))
        
        return {
            "success": True,
            "data": [_serialize_schedule(row) for row in rows],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        print("list_schedules error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/schedules")
def create_schedule(payload: ScheduleCreate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """新增排班"""
    _ensure_admin_or_super(db, current_user)
    try:
        # 驗證路線是否存在
        route_check = MySQL_Run("SELECT COUNT(*) as cnt FROM bus_routes_total WHERE route_id = %s", (payload.route_no,))
        if not route_check or route_check[0]['cnt'] == 0:
            raise HTTPException(status_code=400, detail=f"路線編號 {payload.route_no} 不存在")
        
        # 正常營運需要驗證完整資料
        if payload.operation_status == '正常營運':
            if not payload.schedule_date or not payload.departure_time or not payload.license_plate or not payload.driver_name or not payload.employee_id:
                raise HTTPException(status_code=400, detail="正常營運狀態下必須提供日期、發車時間、車牌號碼、駕駛員姓名和員工編號")
            
            # 驗證車輛是否存在且可用
            car_check = MySQL_Run("SELECT car_status FROM car_resource WHERE car_licence = %s", (payload.license_plate,))
            if not car_check:
                raise HTTPException(status_code=400, detail=f"車牌 {payload.license_plate} 不存在")
            if car_check[0]['car_status'] not in ['service']:
                raise HTTPException(status_code=400, detail=f"車牌 {payload.license_plate} 目前狀態為 {car_check[0]['car_status']}，無法派車")
            
            # 檢查衝突：同一天同一車牌不能在多條路線
            license_conflict = MySQL_Run("""
                SELECT COUNT(*) as cnt FROM route_schedule 
                WHERE license_plate = %s AND date = %s
            """, (payload.license_plate, payload.schedule_date))
            
            if license_conflict and license_conflict[0]['cnt'] > 0:
                raise HTTPException(status_code=400, detail=f"車牌 {payload.license_plate} 在 {payload.schedule_date} 當天已有其他路線排班")
            
            # 檢查衝突：同一天同一駕駛員不能在多條路線
            driver_conflict = MySQL_Run("""
                SELECT COUNT(*) as cnt FROM route_schedule 
                WHERE driver_name = %s AND date = %s
            """, (payload.driver_name, payload.schedule_date))
            
            if driver_conflict and driver_conflict[0]['cnt'] > 0:
                raise HTTPException(status_code=400, detail=f"駕駛員 {payload.driver_name} 在 {payload.schedule_date} 當天已有其他路線排班")
            
            # 檢查衝突：同一天同一員工編號不能在多條路線
            employee_conflict = MySQL_Run("""
                SELECT COUNT(*) as cnt FROM route_schedule 
                WHERE employee_id = %s AND date = %s
            """, (payload.employee_id, payload.schedule_date))
            
            if employee_conflict and employee_conflict[0]['cnt'] > 0:
                raise HTTPException(status_code=400, detail=f"員工編號 {payload.employee_id} 在 {payload.schedule_date} 當天已有其他路線排班")
        
        # 插入資料（需要將schedule_date轉換為date欄位，過濾None值）
        data = payload.dict(exclude_none=True)
        # 將schedule_date重新命名為date以符合資料庫欄位
        if 'schedule_date' in data:
            data['date'] = data.pop('schedule_date')
        
        columns = list(data.keys())
        placeholders = ', '.join(['%s'] * len(columns))
        values = list(data.values())
        
        sql = f"INSERT INTO route_schedule ({', '.join(columns)}) VALUES ({placeholders})"
        result = MySQL_Run(sql, tuple(values))
        
        return {"success": True, "schedule_id": result.get('lastrowid')}
        
    except HTTPException:
        raise
    except Exception as e:
        print("create_schedule error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/schedules/{schedule_id}")
def update_schedule(schedule_id: int, payload: ScheduleUpdate, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """更新排班"""
    _ensure_admin_or_super(db, current_user)
    try:
        # 檢查排班是否存在
        schedule_check = MySQL_Run("SELECT * FROM route_schedule WHERE id = %s", (schedule_id,))
        if not schedule_check:
            raise HTTPException(status_code=404, detail="排班記錄不存在")
        
        current_schedule = schedule_check[0]
        data = payload.dict(exclude_unset=True)
        
        # 將schedule_date轉換為date以符合資料庫欄位
        if 'schedule_date' in data:
            data['date'] = data.pop('schedule_date')
        
        if not data:
            return {"success": True, "message": "沒有變更"}
        
        # 如果修改了路線編號，驗證是否存在
        if 'route_no' in data:
            route_check = MySQL_Run("SELECT COUNT(*) as cnt FROM bus_routes_total WHERE route_id = %s", (data['route_no'],))
            if not route_check or route_check[0]['cnt'] == 0:
                raise HTTPException(status_code=400, detail=f"路線編號 {data['route_no']} 不存在")
        
        # 取得更新後的營運狀態
        check_operation_status = data.get('operation_status', current_schedule['operation_status'])
        
        # 正常營運需要額外驗證
        if check_operation_status == '正常營運':
            # 如果修改了車牌，驗證是否存在且可用
            if 'license_plate' in data:
                car_check = MySQL_Run("SELECT car_status FROM car_resource WHERE car_licence = %s", (data['license_plate'],))
                if not car_check:
                    raise HTTPException(status_code=400, detail=f"車牌 {data['license_plate']} 不存在")
                if car_check[0]['car_status'] not in ['service']:
                    raise HTTPException(status_code=400, detail=f"車牌 {data['license_plate']} 目前狀態為 {car_check[0]['car_status']}，無法派車")
            
            # 準備檢查衝突的資料
            check_license = data.get('license_plate', current_schedule['license_plate'])
            check_date = data.get('date', current_schedule['date'])
            check_driver = data.get('driver_name', current_schedule['driver_name'])
            check_employee = data.get('employee_id', current_schedule['employee_id'])
            
            # 只有在有車牌資料時才檢查車牌衝突
            if check_license:
                license_conflict = MySQL_Run("""
                    SELECT COUNT(*) as cnt FROM route_schedule 
                    WHERE license_plate = %s AND date = %s AND id != %s
                """, (check_license, check_date, schedule_id))
                
                if license_conflict and license_conflict[0]['cnt'] > 0:
                    raise HTTPException(status_code=400, detail=f"車牌 {check_license} 在 {check_date} 當天已有其他路線排班")
            
            # 只有在有駕駛員資料時才檢查駕駛員衝突
            if check_driver:
                driver_conflict = MySQL_Run("""
                    SELECT COUNT(*) as cnt FROM route_schedule 
                    WHERE driver_name = %s AND date = %s AND id != %s
                """, (check_driver, check_date, schedule_id))
                
                if driver_conflict and driver_conflict[0]['cnt'] > 0:
                    raise HTTPException(status_code=400, detail=f"駕駕駛員 {check_driver} 在 {check_date} 當天已有其他路線排班")
            
            # 只有在有員工編號資料時才檢查員工編號衝突
            if check_employee:
                employee_conflict = MySQL_Run("""
                    SELECT COUNT(*) as cnt FROM route_schedule 
                    WHERE employee_id = %s AND date = %s AND id != %s
                """, (check_employee, check_date, schedule_id))
                
                if employee_conflict and employee_conflict[0]['cnt'] > 0:
                    raise HTTPException(status_code=400, detail=f"員工編號 {check_employee} 在 {check_date} 當天已有其他路線排班")
        
        # 更新資料
        sets = []
        params = []
        for key, value in data.items():
            sets.append(f"{key} = %s")
            params.append(value)
        params.append(schedule_id)
        
        sql = f"UPDATE route_schedule SET {', '.join(sets)} WHERE id = %s"
        MySQL_Run(sql, tuple(params))
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        print("update_schedule error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, current_user: AdminUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """刪除排班"""
    _ensure_admin_or_super(db, current_user)
    try:
        # 檢查排班是否存在
        schedule_check = MySQL_Run("SELECT COUNT(*) as cnt FROM route_schedule WHERE id = %s", (schedule_id,))
        if not schedule_check or schedule_check[0]['cnt'] == 0:
            raise HTTPException(status_code=404, detail="排班記錄不存在")
        
        MySQL_Run("DELETE FROM route_schedule WHERE id = %s", (schedule_id,))
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        print("delete_schedule error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/schedules/routes")
def get_schedule_routes(current_user: AdminUser = Depends(get_current_user)):
    """取得可用路線選項"""
    try:
        routes = MySQL_Run("SELECT route_id, route_name FROM bus_routes_total WHERE status = 1 ORDER BY route_id")
        return {
            "success": True,
            "data": routes
        }
    except Exception as e:
        print("get_schedule_routes error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/schedules/cars")
def get_schedule_cars(current_user: AdminUser = Depends(get_current_user)):
    """取得可用車輛選項"""
    try:
        cars = MySQL_Run("SELECT car_licence, car_status FROM car_resource WHERE car_status = 'service' ORDER BY car_licence")
        return {
            "success": True,
            "data": cars
        }
    except Exception as e:
        print("get_schedule_cars error:", e)
        raise HTTPException(status_code=500, detail=str(e))

# ========== 同時開啟前後端 ==========
app.mount('/home', StaticFiles(directory='dist', html=True), name='client')
@app.get("/home", response_class=FileResponse)
async def serve_home_root():
    index_path = Path("dist/index.html")
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend build not found")

@app.get("/home/{full_path:path}", response_class=FileResponse)
async def serve_home_routes(full_path: str):
    base_dir = Path("dist")
    candidate = base_dir / full_path
    index_path = base_dir / "index.html"
    if candidate.is_file():
        return FileResponse(candidate)
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend build not found")
