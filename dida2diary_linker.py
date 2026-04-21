#!/usr/bin/env python3
"""
滴答清单任务 → 日记中心自动关联
功能：根据滴答清单的任务，自动关联到Notion日记中心

流程：
1. 获取滴答清单指定日期的任务（含日期范围匹配）
2. 在任务中心搜索匹配的任务
3. 将匹配的任务关联到日记中心
"""

import requests
import json
from datetime import datetime, timedelta

# ============== 配置 ==============
# 从环境变量读取敏感信息
import os
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DIDA_TOKEN = os.environ.get("DIDA_TOKEN", "")

if not NOTION_TOKEN or not DIDA_TOKEN:
    raise ValueError("请设置环境变量 NOTION_TOKEN 和 DIDA_TOKEN")

# Notion数据库ID
DIARY_DB_ID = "4e6607f4-7140-4317-8fc9-d52102337869"  # 日记中心
TASK_DB_ID = "18133b33-7f23-8032-8f8e-e9e7c821f021"   # 任务中心（事件与任务）

# API基础配置
NOTION_VERSION = "2022-06-28"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}
DIDA_HEADERS = {
    "Authorization": f"Bearer {DIDA_TOKEN}",
    "Content-Type": "application/json"
}
DIDA_BASE = "https://api.dida365.com"


def get_dida_tasks_for_date(target_date: str) -> list:
    """
    获取滴答清单指定日期的任务
    包括：截止日期在当天的任务 + 日期范围覆盖当天的任务
    检查所有清单（不只是收集箱）
    """
    # 所有清单ID
    PROJECT_IDS = {
        "濠联": "5e4cfef0c7edd11da9d5d956",
        "产品AI": "6825ab4ef12d11b11d7a4438",
        "杂事": "6047b441e99211186ac946e9",
        "旅行": "6825aa6e4750d1b11d7a28a5",
        "学术": "6406ebd9ccacd1017417b974",
        "理财": "69870dfa2fae5176a082bb20",
        "shopee": "686e9aec5c5751e8c67cade5",
        "书籍": "5ff9ffd8fa6d5106156432a9",
        "工作": "6493430012fa510358848b31",
        "健康": "68027b74e3d0d1f4189d4578",
        "影剧": "5ff9fffdf313d106156432d5fc",
        "展览活动": "69a2c97dc101d162759eee4d",
        "自我管理": "65e40aed3e64110443527cf5",
        "购物": "6309c13dd063d1013009fb4e",
    }
    
    all_tasks = []
    
    # 先获取收集箱
    inbox_url = f"{DIDA_BASE}/open/v1/project/inbox/data"
    response = requests.get(inbox_url, headers=DIDA_HEADERS)
    if response.status_code == 200:
        data = response.json()
        all_tasks.extend(data.get("tasks", []))
    
    # 再遍历所有清单
    for project_name, project_id in PROJECT_IDS.items():
        url = f"{DIDA_BASE}/open/v1/project/{project_id}/data"
        resp = requests.get(url, headers=DIDA_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            tasks = data.get("tasks", [])
            all_tasks.extend(tasks)
    
    # 去重（根据task_id）
    seen_ids = set()
    unique_tasks = []
    for t in all_tasks:
        tid = t.get("id", "")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            unique_tasks.append(t)
    
    # 匹配目标日期
    matched_tasks = []
    for task in unique_tasks:
        task_id = task.get("id", "")
        title = task.get("title", "")
        due_date = task.get("dueDate", "")[:10] if task.get("dueDate") else ""
        start_date = task.get("startDate", "")[:10] if task.get("startDate") else ""
        
        # 匹配条件：
        # 1. 截止日期 = 目标日期
        # 2. 开始日期 = 目标日期
        # 3. 日期范围包含目标日期
        is_match = False
        
        if due_date == target_date or start_date == target_date:
            is_match = True
        elif start_date and due_date:
            # 检查目标日期是否在[start_date, due_date]范围内
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(due_date, "%Y-%m-%d")
                target = datetime.strptime(target_date, "%Y-%m-%d")
                if start <= target <= end:
                    is_match = True
            except:
                pass
        
        if is_match:
            matched_tasks.append({
                "id": task_id,
                "title": title.strip(),
                "startDate": start_date,
                "dueDate": due_date
            })
    
    return matched_tasks


def normalize_date(date_str: str) -> str:
    """
    标准化日期字符串，统一为 YYYY-MM-DD 格式
    处理时区信息，转换为北京时间 (UTC+8)
    
    输入可能是：
    - "2026-04-12"
    - "2026-04-12T00:00:00"
    - "2026-04-12T00:00:00+08:00"
    - "2026-04-12T08:00:00+08:00"
    
    输出：统一为 "2026-04-12"
    """
    if not date_str:
        return ""
    
    # 去掉时区信息（统一按北京时间处理）
    # 如果有时间部分，提取日期部分
    if "T" in date_str:
        date_str = date_str.split("T")[0]
    
    return date_str.strip()


def search_task_center_tasks(query: str, target_date: str = None) -> list:
    """
    在任务中心搜索匹配的任务
    先用精确标题匹配（equals），再验证时间范围
    
    Args:
        query: 任务标题（精确匹配）
        target_date: 目标日期 (YYYY-MM-DD)，如果提供则同时验证时间范围包含该日期
    
    Returns:
        匹配的任务列表
    """
    # ⚠️ 使用 equals 精确匹配，避免"广州"匹配到"曼谷飞广州"等历史记录
    payload = {
        "filter": {"property": "名称", "title": {"equals": query}},
        "page_size": 100
    }

    url = f"https://api.notion.com/v1/databases/{TASK_DB_ID}/query"
    response = requests.post(url, headers=NOTION_HEADERS, json=payload)

    if response.status_code != 200:
        print(f"搜索任务中心失败: {response.status_code} - {response.text[:200]}")
        return []

    all_matches = response.json().get("results", [])

    tasks = []
    for page in all_matches:
        props = page.get("properties", {})
        name_data = props.get("名称") or {}
        name_list = name_data.get("title") or []
        name = name_list[0].get("plain_text") if name_list else ""

        # 标题必须完全一致（去除首尾空格后比较）
        if name.strip() != query.strip():
            continue

        # 获取日期（可能是一个范围）
        date_data = props.get("日期") or {}
        date_obj = date_data.get("date") or {}
        date_start = normalize_date(date_obj.get("start", ""))
        date_end = normalize_date(date_obj.get("end", ""))

        # 如果没有提供目标日期，返回所有精确匹配标题的任务
        if not target_date:
            tasks.append({
                "id": page["id"],
                "title": name,
                "date_start": date_start,
                "date_end": date_end,
                "date": date_start
            })
            continue

        # 验证时间范围包含 target_date
        is_time_match = False

        if date_start == target_date:
            is_time_match = True
        elif date_start and date_end:
            try:
                s = datetime.strptime(date_start, "%Y-%m-%d")
                e = datetime.strptime(date_end, "%Y-%m-%d")
                t = datetime.strptime(target_date, "%Y-%m-%d")
                if s <= t <= e:
                    is_time_match = True
            except:
                pass

        if is_time_match:
            tasks.append({
                "id": page["id"],
                "title": name,
                "date_start": date_start,
                "date_end": date_end,
                "date": date_start
            })

    return tasks


def get_diary_entry(target_date: str) -> dict:
    """获取日记中心指定日期的条目"""
    url = f"https://api.notion.com/v1/databases/{DIARY_DB_ID}/query"
    payload = {
        "filter": {
            "property": "日期",
            "date": {"equals": target_date}
        },
        "page_size": 1
    }
    
    response = requests.post(url, headers=NOTION_HEADERS, json=payload)
    
    if response.status_code != 200:
        print(f"获取日记条目失败: {response.status_code}")
        return None
    
    data = response.json()
    results = data.get("results", [])
    
    if not results:
        print(f"未找到日期为 {target_date} 的日记条目")
        return None
    
    return results[0]


def get_existing_event_relations(diary_page_id: str) -> set:
    """获取日记当前关联的事件ID集合"""
    url = f"https://api.notion.com/v1/pages/{diary_page_id}"
    response = requests.get(url, headers=NOTION_HEADERS)
    
    if response.status_code != 200:
        return set()
    
    data = response.json()
    props = data.get("properties", {})
    events_data = props.get("事件与任务") or {}
    relations = events_data.get("relation") or []
    
    return {r.get("id") for r in relations}


def add_event_relation(diary_page_id: str, event_id: str) -> bool:
    """添加事件到日记的关联"""
    url = f"https://api.notion.com/v1/pages/{diary_page_id}"
    
    # 先获取当前关联
    existing = get_existing_event_relations(diary_page_id)
    
    if event_id in existing:
        return True  # 已经关联，跳过
    
    # 添加新关联
    new_relations = list(existing) + [event_id]
    
    payload = {
        "properties": {
            "事件与任务": {
                "relation": [{"id": rid} for rid in new_relations]
            }
        }
    }
    
    response = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    
    if response.status_code == 200:
        return True
    else:
        print(f"添加关联失败: {response.status_code} - {response.text[:200]}")
        return False


def link_dida_tasks_to_diary(target_date: str, dry_run: bool = True) -> dict:
    """
    主函数：将滴答任务关联到日记中心
    
    Args:
        target_date: 目标日期 (YYYY-MM-DD)
        dry_run: True=模拟运行，False=实际执行
    
    Returns:
        执行结果统计
    """
    results = {
        "date": target_date,
        "dida_tasks": [],
        "matched_tasks": [],
        "already_linked": [],
        "newly_linked": [],
        "failed": []
    }
    
    print(f"\n{'='*60}")
    print(f"📅 日期: {target_date}")
    print(f"{'='*60}")
    
    # 1. 获取滴答任务
    print(f"\n📋 获取滴答清单任务...")
    dida_tasks = get_dida_tasks_for_date(target_date)
    results["dida_tasks"] = dida_tasks
    print(f"   找到 {len(dida_tasks)} 个滴答任务:")
    for t in dida_tasks:
        print(f"   - {t['title']} (ID: {t['id']})")
    
    if not dida_tasks:
        print("   没有找到滴答任务，退出")
        return results
    
    # 2. 获取日记条目
    print(f"\n📓 获取日记条目...")
    diary = get_diary_entry(target_date)
    if not diary:
        print("   没有找到日记条目，退出")
        return results
    
    diary_id = diary["id"]
    print(f"   日记条目ID: {diary_id}")
    
    # 3. 获取已有关联
    existing_ids = get_existing_event_relations(diary_id)
    print(f"   已有 {len(existing_ids)} 个事件关联")
    
    # 4. 匹配并关联
    print(f"\n🔗 匹配任务中心记录 (标题 + 时间双重验证)...")
    for dida_task in dida_tasks:
        task_title = dida_task["title"]
        task_start = dida_task.get("startDate", "")
        task_due = dida_task.get("dueDate", "")
        
        # 在任务中心搜索（同时传递目标日期用于时间验证）
        matched = search_task_center_tasks(task_title, target_date)
        
        if not matched:
            # 尝试只看标题匹配（不过滤时间），用于诊断
            all_title_matches = search_task_center_tasks(task_title, target_date=None)
            if all_title_matches:
                task_dates = [f"{t['title'].strip()}({t.get('date_start', '无日期')})" for t in all_title_matches]
                print(f"   ⚠️  {task_title} [滴答:{task_due or task_start}]: 标题匹配但时间不一致")
                print(f"      任务中心记录: {', '.join(task_dates)}")
            else:
                print(f"   ⚠️  {task_title} [{task_due or task_start}]: 任务中心无此任务（精确匹配）")
            results["failed"].append(task_title)
            continue
        
        # 找到匹配的任务（可能多个，按时间匹配度排序）
        for task in matched:
            task_id = task["id"]
            task_date = task.get("date_start") or task.get("date")
            
            if task_id in existing_ids:
                print(f"   ✅ {task_title} [{task_date}]: 已关联")
                results["already_linked"].append(task["title"])
            else:
                if dry_run:
                    print(f"   🔄 {task_title} [{task_date}]: 将关联 (dry_run)")
                    results["newly_linked"].append(task["title"])
                else:
                    if add_event_relation(diary_id, task_id):
                        print(f"   ✅ {task_title} [{task_date}]: 关联成功")
                        results["newly_linked"].append(task["title"])
                    else:
                        print(f"   ❌ {task_title} [{task_date}]: 关联失败")
                        results["failed"].append(task["title"])
            
            results["matched_tasks"].append(task)
    
    # 5. 汇总
    print(f"\n{'='*60}")
    print(f"📊 执行结果汇总")
    print(f"{'='*60}")
    print(f"   滴答任务数: {len(dida_tasks)}")
    print(f"   任务中心匹配: {len(results['matched_tasks'])}")
    print(f"   已有关联: {len(results['already_linked'])}")
    print(f"   新增关联: {len(results['newly_linked'])}")
    print(f"   失败: {len(results['failed'])}")
    
    if dry_run:
        print(f"\n⚠️  当前是模拟运行模式，如需实际执行请设置 dry_run=False")
    
    return results


def main():
    """入口函数"""
    import sys
    
    # 默认处理昨天
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 解析命令行参数
    date = yesterday
    dry_run = True
    
    if len(sys.argv) > 1:
        date = sys.argv[1]
    if len(sys.argv) > 2:
        dry_run = sys.argv[2].lower() != "run"
    
    print(f"🤖 滴答任务 → 日记中心自动关联")
    print(f"   目标日期: {date}")
    print(f"   模式: {'模拟运行' if dry_run else '实际执行'}")
    
    link_dida_tasks_to_diary(date, dry_run=dry_run)


if __name__ == "__main__":
    main()
