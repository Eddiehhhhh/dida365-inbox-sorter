#!/usr/bin/env python3
"""
滴答清单收集箱整理 - 防重复版
每小时运行：只处理有截止日期的任务
核心修复：删除 API 有 bug，返回 200 但实际未删除
解决方案：创建前先检查目标清单是否已有同名任务
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

# 缓存已获取的清单任务，避免重复请求
_project_tasks_cache = {}


def get_project_tasks(project_id):
    """获取指定清单的所有任务（带缓存）"""
    if project_id in _project_tasks_cache:
        return _project_tasks_cache[project_id]

    url = f"{API_BASE}/open/v1/project/{project_id}/data"
    response = requests.get(url, headers=HEADERS, timeout=10)
    if response.status_code == 200:
        data = response.json()
        tasks = data.get("tasks", [])
        _project_tasks_cache[project_id] = tasks
        return tasks
    return []


def task_exists_in_project(project_id, task_title):
    """检查目标清单是否已有同名任务"""
    tasks = get_project_tasks(project_id)
    for task in tasks:
        # 只比较标题，忽略细节差异
        if task.get("title", "").strip() == task_title.strip():
            return True
    return False


def get_inbox_tasks():
    """获取收集箱中的任务"""
    url = f"{API_BASE}/open/v1/project/inbox/data"
    response = requests.get(url, headers=HEADERS, timeout=10)
    if response.status_code == 200:
        return response.json()
    return None


def move_task(task_id, target_project_id, task, target_name):
    """移动任务：先检查防重复，再创建，忽略删除结果"""
    task_title = task.get("title", "").strip()

    # 关键修复：先检查目标清单是否已有同名任务
    if task_exists_in_project(target_project_id, task_title):
        print(f"  ⚠️ 跳过（目标清单已有）: {task_title} → {target_name}")
        return "skipped_duplicate"

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
    result = requests.post(create_url, headers=HEADERS, json=new_task, timeout=10)

    if result.status_code == 200:
        print(f"  ✅ 已创建: {task_title} → {target_name}")
        return "success"
    else:
        print(f"  ❌ 创建失败: {task_title}, 状态码: {result.status_code}")
        return "failed"


def suggest_project(task_title):
    """根据任务标题建议目标清单"""
    for keyword, project in TASK_KEYWORDS.items():
        if keyword in task_title:
            return project
    return None


def main():
    print("=" * 50)
    print("滴答清单收集箱整理 - 防重复版")
    print("=" * 50)

    results = {
        "success": [],
        "failed": [],
        "skipped": [],
        "skipped_duplicate": []
    }

    # 获取收集箱任务
    print("\n📥 获取收集箱任务...")
    inbox_data = get_inbox_tasks()
    if not inbox_data:
        print("❌ 无法获取收集箱数据")
        sys.exit(1)

    # 筛选有截止日期的任务
    tasks_with_dates = [
        task for task in inbox_data.get("tasks", [])
        if task.get("dueDate")
    ]

    print(f"📋 收集箱中有 {len(tasks_with_dates)} 个带截止日期的任务")

    if not tasks_with_dates:
        print("✅ 没有需要整理的任务")
        sys.exit(0)

    # 处理每个任务
    print("\n🔄 开始整理...\n")
    for task in tasks_with_dates:
        task_id = task["id"]
        task_title = task.get("title", "")
        due_date = task.get("dueDate", "")[:10]

        suggested = suggest_project(task_title)

        if suggested and suggested in PROJECT_MAP:
            project_id = PROJECT_MAP[suggested]
            result = move_task(task_id, project_id, task, suggested)

            if result == "success":
                results["success"].append({
                    "title": task_title,
                    "dueDate": due_date,
                    "target": suggested
                })
            elif result == "skipped_duplicate":
                results["skipped_duplicate"].append({
                    "title": task_title,
                    "dueDate": due_date,
                    "target": suggested
                })
            else:
                results["failed"].append({
                    "title": task_title,
                    "reason": "创建失败"
                })
        else:
            results["skipped"].append({
                "title": task_title,
                "dueDate": due_date,
                "reason": "未找到对应清单"
            })

    # 输出结果
    print("\n" + "=" * 50)
    print("📊 整理结果:")
    print(f"   ✅ 新建移动: {len(results['success'])} 个")
    print(f"   ⏭️  已存在跳过: {len(results['skipped_duplicate'])} 个")
    print(f"   ⏭️  无匹配跳过: {len(results['skipped'])} 个")
    print(f"   ❌ 失败: {len(results['failed'])} 个")
    print("=" * 50)

    # JSON 输出供 GitHub Actions 使用
    print(json.dumps({
        "message": f"处理完成：{len(results['success'])}个新建，{len(results['skipped_duplicate'])}个已存在，{len(results['skipped'])}个跳过，{len(results['failed'])}个失败",
        "results": results
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
