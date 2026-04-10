#!/usr/bin/env python3
"""
滴答清单收集箱整理 - 修复版
每小时运行：只处理有截止日期的任务
使用正确的方法：创建新任务 + 删除原任务
"""

import requests
import json
import sys

# API配置
API_BASE = "https://api.dida365.com"
TOKEN = "dp_2713ef1e9011476ea73af004dbaedeb6"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# 清单ID映射
PROJECT_MAP = {
    "濠联": "5e4cfef0c7edd11da9d5d956",
    "产品AI": "6825ab4ef12d11b11d7a4438",
    "杂事": "6047b441e99211186ac946e9",
    "旅行": "6825aa6e4750d1b11d7a28a5",
    "学术": "6406ebd9ccacd1017417b974",
    "理财": "69870dfa2fae5176a082bb20",
    "shopee": "686e9aec5c5751e8c67cade5",
    "书籍": "5ff9ffd8fa6d5106156432a9",
    "展览活动": "69a2c97dc101d162759eee4d",
    "健康": "68027b74e3d0d1f4189d4578",
    "影剧": "5ff9fffdf313d106156432d5fc",
    "自我管理": "65e40aed3e64110443527cf5",
    "购物": "6309c13dd063d1013009fb4e",
}

# 关键词→清单 映射
TASK_KEYWORDS = {
    # 活动/社交
    "握手": "展览活动", "活动": "展览活动", "聚会": "展览活动",
    # 濠联
    "濠联": "濠联", "i志愿": "濠联", "青志协": "濠联", "换届": "濠联",
    # 旅行
    "旅行": "旅行", "意大利": "旅行", "东京": "旅行", "旅居": "旅行",
    # AI/产品
    "AI": "产品AI", "ai": "产品AI", "ChatGPT": "产品AI", "产品": "产品AI",
    # 读书
    "书": "书籍", "读书": "书籍", "课程": "书籍",
    # 电影/剧
    "电影": "影剧", "剧": "影剧",
    # 健康
    "健康": "健康", "运动": "健康", "饮食": "健康",
    # 自我管理
    "目标": "自我管理", "复盘": "自我管理", "反思": "自我管理",
    # 理财
    "理财": "理财", "投资": "理财", "稀土": "理财", "万事达": "理财",
    # 学术
    "论文": "学术", "学术": "学术",
    # 杂事
    "宽带": "杂事", "房租": "杂事", "交房": "杂事", "信用卡": "杂事",
    # 购物
    "购物": "购物", "拍房子": "购物",
    # Shopee
    "shopee": "shopee", "Shopee": "shopee",
}

def get_inbox_tasks():
    """获取收集箱中的任务"""
    url = f"{API_BASE}/open/v1/project/inbox/data"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return None

def move_task(task_id, target_project_id, task):
    """移动任务：创建新任务 + 删除原任务"""
    # 构建新任务数据
    new_task = {
        "title": task.get("title"),
        "content": task.get("content", ""),
        "desc": task.get("desc", ""),
        "dueDate": task.get("dueDate"),
        "startDate": task.get("startDate"),
        "isAllDay": task.get("isAllDay", True),
        "priority": task.get("priority", 1),
        "timezone": task.get("timezone", "Asia/Shanghai"),
        "projectId": target_project_id,
    }
    
    # 在目标清单创建新任务
    create_url = f"{API_BASE}/open/v1/task"
    result = requests.post(create_url, headers=HEADERS, json=new_task)
    if result.status_code != 200:
        return False
    
    # 删除原任务
    delete_url = f"{API_BASE}/open/v1/project/inbox/task/{task_id}"
    del_result = requests.delete(delete_url, headers=HEADERS)
    return del_result.status_code == 200

def suggest_project(task_title):
    """根据任务标题建议目标清单"""
    for keyword, project in TASK_KEYWORDS.items():
        if keyword in task_title:
            return project
    return None

def main():
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }
    
    # 获取收集箱任务
    inbox_data = get_inbox_tasks()
    if not inbox_data:
        print(json.dumps({"error": "无法获取收集箱数据", "results": results}))
        sys.exit(1)
    
    # 筛选有截止日期的任务
    tasks_with_dates = [
        task for task in inbox_data.get("tasks", [])
        if task.get("dueDate")
    ]
    
    if not tasks_with_dates:
        print(json.dumps({"message": "收集箱中没有带截止日期的任务", "results": results}))
        sys.exit(0)
    
    # 处理每个任务
    for task in tasks_with_dates:
        task_id = task["id"]
        task_title = task["title"]
        due_date = task.get("dueDate", "")[:10]
        
        suggested = suggest_project(task_title)
        
        if suggested and suggested in PROJECT_MAP:
            project_id = PROJECT_MAP[suggested]
            success = move_task(task_id, project_id, task)
            
            if success:
                results["success"].append({
                    "title": task_title,
                    "dueDate": due_date,
                    "target": suggested
                })
            else:
                results["failed"].append({
                    "title": task_title,
                    "reason": "移动失败"
                })
        else:
            results["skipped"].append({
                "title": task_title,
                "dueDate": due_date,
                "reason": "未找到对应清单"
            })
    
    # 输出结果
    print(json.dumps({
        "message": f"处理完成：{len(results['success'])}个移动成功，{len(results['skipped'])}个跳过，{len(results['failed'])}个失败",
        "results": results
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
