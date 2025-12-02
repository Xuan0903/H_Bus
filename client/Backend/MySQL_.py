from dotenv import load_dotenv
from pymysql.err import OperationalError
import pymysql
import pandas as pd
import os
import time

load_dotenv()

class MySQL_Doing:
    def __init__(self):
        self.Host = os.getenv("Host", "192.168.0.126")
        self.User = os.getenv("User", "root")
        self.Port = int(os.getenv("Port", 3307))
        self.Password = os.getenv("Password_SQL", "109109")
        self.Database = os.getenv("Database", "bus_system")
        self.conn = None
        self.last_connect_time = 0
        self.connect_timeout = 5         # ⏱️ 連線逾時（秒）
        self.query_timeout = 10          # ⏱️ 單次查詢逾時（秒）
        self.reconnect_interval = 60     # ⏳ 若超過多久未使用就重連（秒）

        self._ensure_connection()

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
            write_timeout=self.query_timeout
        )

    def _ensure_connection(self):
        """確保連線有效或重新連線"""
        now = time.time()
        if (
            self.conn is None
            or not self.conn.open
            or now - self.last_connect_time > self.reconnect_interval
        ):
            try:
                if self.conn:
                    self.conn.close()
            except:
                pass
            self.conn = self._connect()
            self.last_connect_time = now

    def run(self, sql, params=None):
        """執行 SQL 指令，自動重連＋逾時防護"""
        try:
            self._ensure_connection()
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params or ())
                self.conn.commit()

                if cursor.description:
                    rows = cursor.fetchall()
                    return pd.DataFrame(rows)
                return None
        except (OperationalError, pymysql.MySQLError) as e:
            print("[MySQL] 錯誤:", e)
            # 若連線失效，自動重連一次
            try:
                self.conn = self._connect()
                with self.conn.cursor() as cursor:
                    cursor.execute(sql, params or ())
                    self.conn.commit()
                    if cursor.description:
                        rows = cursor.fetchall()
                        return pd.DataFrame(rows)
                    return None
            except Exception as retry_e:
                print("[MySQL] 重連失敗:", retry_e)
                raise
        finally:
            # 即使有異常，也確保不會掛死連線
            try:
                self.conn.ping(reconnect=False)
            except:
                try:
                    self.conn.close()
                except:
                    pass

MySQL_Doing = MySQL_Doing()
XX = MySQL_Doing.run("show tables")
XX