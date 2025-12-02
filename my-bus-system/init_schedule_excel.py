#!/usr/bin/env python3
"""
初始化排班管理 Excel 檔案
這個腳本會：
1. 建立 schedule_data.xlsx 檔案
2. 初始化 route_schedule 表格的固定 5 筆記錄
3. 提供測試資料範例
"""

import pandas as pd
import os
from datetime import datetime
from MySQL import MySQL_Run

def init_schedule_excel():
    """初始化排班 Excel 檔案"""
    excel_file = "schedule_data.xlsx"
    
    print("正在初始化排班 Excel 檔案...")
    
    # 建立 DataFrame 結構
    df = pd.DataFrame(columns=[
        'id',  # 自動遞增的序號
        'route_no',  # 路線編號
        'route_name',  # 路線名稱
        'direction',  # 方向（去程/返程/其他）
        'special_type',  # 特殊營運型態
        'operation_status',  # 營運狀態
        'date',  # 日期
        'departure_time',  # 發車時間
        'license_plate',  # 車牌號碼
        'car_status',  # 車輛狀態
        'driver_name',  # 駕駛員姓名
        'employee_id',  # 員工編號
        'created_at',  # 建立時間
        'updated_at',  # 更新時間
        'is_deleted'  # 軟刪除標記（0=正常，1=已刪除）
    ])
    
    # 加入一些範例資料
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sample_data = [
        {
            'id': 1,
            'route_no': '1',
            'route_name': '市民小巴5',
            'direction': '去程',
            'special_type': '',
            'operation_status': '正常營運',
            'date': '2024-10-22',
            'departure_time': '08:00',
            'license_plate': 'AAA-1234',
            'car_status': 'service',
            'driver_name': '王小明',
            'employee_id': 'D001',
            'created_at': now,
            'updated_at': now,
            'is_deleted': 0
        },
        {
            'id': 2,
            'route_no': '1',
            'route_name': '市民小巴5',
            'direction': '返程',
            'special_type': '',
            'operation_status': '正常營運',
            'date': '2024-10-22',
            'departure_time': '08:30',
            'license_plate': 'BBB-5678',
            'car_status': 'service',
            'driver_name': '李小華',
            'employee_id': 'D002',
            'created_at': now,
            'updated_at': now,
            'is_deleted': 0
        },
        {
            'id': 3,
            'route_no': '2',
            'route_name': '市民小巴6',
            'direction': '去程',
            'special_type': '',
            'operation_status': '正常營運',
            'date': '2024-10-22',
            'departure_time': '09:00',
            'license_plate': 'CCC-9012',
            'car_status': 'service',
            'driver_name': '張小美',
            'employee_id': 'D003',
            'created_at': now,
            'updated_at': now,
            'is_deleted': 0
        },
        {
            'id': 4,
            'route_no': '2',
            'route_name': '市民小巴6',
            'direction': '返程',
            'special_type': '',
            'operation_status': '正常營運',
            'date': '2024-10-22',
            'departure_time': '09:30',
            'license_plate': 'DDD-3456',
            'car_status': 'service',
            'driver_name': '陳小強',
            'employee_id': 'D004',
            'created_at': now,
            'updated_at': now,
            'is_deleted': 0
        },
        {
            'id': 5,
            'route_no': '3',
            'route_name': '市民小巴7',
            'direction': '去程',  # 由於資料庫限制，使用去程
            'special_type': '不分方向',  # 在這裡標註
            'operation_status': '正常營運',
            'date': '2024-10-22',
            'departure_time': '10:00',
            'license_plate': 'EEE-7890',
            'car_status': 'service',
            'driver_name': '林小芳',
            'employee_id': 'D005',
            'created_at': now,
            'updated_at': now,
            'is_deleted': 0
        }
    ]
    
    # 建立 DataFrame
    df = pd.DataFrame(sample_data)
    
    # 寫入 Excel 檔案
    df.to_excel(excel_file, index=False)
    print(f"✅ Excel 檔案已建立: {excel_file}")
    
    return excel_file

def init_route_schedule_table():
    """初始化 route_schedule 表格的固定 5 筆記錄"""
    
    print("正在初始化 route_schedule 表格...")
    
    try:
        # 清空現有資料
        MySQL_Run("DELETE FROM route_schedule")
        print("✅ 已清空 route_schedule 表格")
        
        # 預定義的 5 個路線-方向組合
        route_combinations = [
            {
                'route_no': 1,  # 使用整數類型
                'direction': '去程',
                'special_type': '',
                'operation_status': '正常營運',
                'date': '2024-10-22',
                'departure_time': '08:00',
                'license_plate': 'AAA-1234',
                'driver_name': '王小明',
                'employee_id': 'D001'
            },
            {
                'route_no': 1,  # 使用整數類型
                'direction': '返程',
                'special_type': '',
                'operation_status': '正常營運',
                'date': '2024-10-22',
                'departure_time': '08:30',
                'license_plate': 'BBB-5678',
                'driver_name': '李小華',
                'employee_id': 'D002'
            },
            {
                'route_no': 2,  # 使用整數類型
                'direction': '去程',
                'special_type': '',
                'operation_status': '正常營運',
                'date': '2024-10-22',
                'departure_time': '09:00',
                'license_plate': 'CCC-9012',
                'driver_name': '張小美',
                'employee_id': 'D003'
            },
            {
                'route_no': 2,  # 使用整數類型
                'direction': '返程',
                'special_type': '',
                'operation_status': '正常營運',
                'date': '2024-10-22',
                'departure_time': '09:30',
                'license_plate': 'DDD-3456',
                'driver_name': '陳小強',
                'employee_id': 'D004'
            },
            {
                'route_no': 3,  # 使用整數類型
                'direction': '去程',  # 由於 enum 限制，暫時使用去程
                'special_type': '不分方向',  # 在這裡標註
                'operation_status': '正常營運',
                'date': '2024-10-22',
                'departure_time': '10:00',
                'license_plate': 'EEE-7890',
                'driver_name': '林小芳',
                'employee_id': 'D005'
            }
        ]
        
        # 插入固定的 5 筆記錄
        for record in route_combinations:
            columns = list(record.keys())
            placeholders = ', '.join(['%s'] * len(columns))
            values = list(record.values())
            
            sql = f"INSERT INTO route_schedule ({', '.join(columns)}) VALUES ({placeholders})"
            MySQL_Run(sql, tuple(values))
        
        print("✅ 已初始化 route_schedule 表格的固定 5 筆記錄")
        
        # 檢查結果
        result = MySQL_Run("SELECT COUNT(*) as cnt FROM route_schedule")
        print(f"✅ route_schedule 表格目前有 {result[0]['cnt']} 筆記錄")
        
    except Exception as e:
        print(f"❌ 初始化 route_schedule 表格失敗: {e}")
        raise

def main():
    """主要初始化程序"""
    print("========== 排班管理系統初始化 ==========")
    
    try:
        # 初始化 Excel 檔案
        excel_file = init_schedule_excel()
        
        # 初始化資料庫表格
        init_route_schedule_table()
        
        print("\n========== 初始化完成 ==========")
        print(f"✅ Excel 檔案: {excel_file}")
        print("✅ route_schedule 表格已準備就緒")
        print("✅ 系統已準備好使用 Excel 為主的排班管理")
        
        print("\n說明：")
        print("- schedule_data.xlsx 是主要的排班資料存儲")
        print("- route_schedule 表格維持固定 5 筆記錄供前端 APP 使用")
        print("- 所有 CRUD 操作都會先更新 Excel，然後同步到 route_schedule")
        
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
        return False
    
    return True

if __name__ == "__main__":
    main()