from dotenv import load_dotenv
from pymysql.err import OperationalError
import pymysql
import pandas as pd
import os
import time

load_dotenv()

class MySQL_Doing:
    """
    通用版 MySQL 操作工具

    功能：
    - 設定從 .env 讀取：
        Host, User, Port, Password_SQL, Database
    - 單一長連線（self.conn），每次 query 前檢查是否可用
    - 斷線 / 超時 自動重連 + 重試
    - 回傳 pandas.DataFrame（有結果集時）
    """

    def __init__(self):
        # 基本連線設定（可被 .env 覆蓋）
        self.Host = os.getenv("Host", "127.0.0.1")
        self.User = os.getenv("User", "root")
        self.Port = int(os.getenv("Port", 3307))
        self.Password = os.getenv("Password_SQL", "")
        self.Database = os.getenv("Database", "")

        # Timeouts / 重試設定（可從 .env 調整）
        self.connect_timeout = int(os.getenv("MYSQL_CONNECT_TIMEOUT", 5))   # 連線逾時（秒）
        self.query_timeout = int(os.getenv("MYSQL_QUERY_TIMEOUT", 10))      # 單次查詢逾時（秒）
        self.reconnect_interval = int(os.getenv("MYSQL_RECONNECT_INTERVAL", 60))  # 超過多久未使用就重連（秒）
        self.max_retries = int(os.getenv("MYSQL_MAX_RETRIES", 3))          # 最多重試次數

        # 內部狀態
        self.conn = None
        self.last_connect_time = 0

    # ------------------------------
    # 連線管理
    # ------------------------------
    def _connect(self):
        """建立新的資料庫連線"""
        return pymysql.connect(
            host=self.Host,
            user=self.User,
            port=self.Port,
            password=self.Password,
            database=self.Database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=self.connect_timeout,
            read_timeout=self.query_timeout,
            write_timeout=self.query_timeout,
        )

    def _ensure_connection(self):
        """確保 self.conn 是可用的，必要時重新連線"""
        now = time.time()

        need_reconnect = (
            self.conn is None
            or not getattr(self.conn, "open", False)
            or (now - self.last_connect_time) > self.reconnect_interval
        )

        if need_reconnect:
            # 先把舊連線關掉（如果有的話）
            try:
                if self.conn:
                    self.conn.close()
            except:
                pass

            self.conn = self._connect()
            self.last_connect_time = now

    def _close_connection_if_dead(self):
        """檢查連線是否還活著，不活就關掉，讓下次 query 自己重連"""
        if not self.conn:
            return
        try:
            # ping(reconnect=False) 若連線已死會丟例外
            self.conn.ping(reconnect=False)
        except:
            try:
                self.conn.close()
            except:
                pass
            finally:
                self.conn = None

    # ------------------------------
    # 對外主要介面
    # ------------------------------
    def run(self, sql, params=None):
        """
        執行 SQL 指令：
        - SELECT 會回傳 pandas.DataFrame
        - INSERT / UPDATE / DELETE 回傳 None
        - 自動重連 + 多次重試（只針對斷線類錯誤）
        """
        attempt = 0
        last_error = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                self._ensure_connection()

                with self.conn.cursor() as cursor:
                    cursor.execute(sql, params or ())
                    # autocommit=True，但這裡保險一下
                    self.conn.commit()

                    if cursor.description:  # 有結果集（SELECT）
                        rows = cursor.fetchall()
                        return pd.DataFrame(rows)
                    else:
                        return None

            except (OperationalError, pymysql.MySQLError) as e:
                last_error = e
                print(f"[MySQL] 錯誤（第 {attempt} 次嘗試）:", e)

                # 判斷是否為「斷線 / 超時」類錯誤 → 可以重試
                err_code = None
                if hasattr(e, "args") and len(e.args) > 0:
                    err_code = e.args[0]

                # 常見斷線錯誤代碼：2006, 2013, 1047, 2014 等
                transient_codes = {2006, 2013, 1047, 2014}
                is_transient = (
                    isinstance(err_code, int) and err_code in transient_codes
                ) or any(code in str(e) for code in ["2013", "2006", "10060"])

                # 先把當前連線關掉，下次 loop 會重連
                try:
                    if self.conn:
                        self.conn.close()
                except:
                    pass
                finally:
                    self.conn = None

                if is_transient and attempt < self.max_retries:
                    # 等一下再重試
                    time.sleep(0.5)
                    continue
                else:
                    # 非可重試錯誤 / 次數用完 → 直接丟出去
                    raise

            finally:
                # 每次執行後檢查連線狀態，不活就關掉
                self._close_connection_if_dead()

        # 如果跑到這裡表示所有重試都失敗
        raise OperationalError(
            f"MySQL 連線失敗或查詢失敗（已重試 {self.max_retries} 次）：{last_error}"
        )
