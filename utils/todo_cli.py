# import argparse
# import asyncio
# import json
#
#
# async def fetch_tasks(list_id: str, timeout: int) -> list[dict]:
#     result = await graph_request("GET", f"/me/todo/lists/{list_id}/tasks", timeout)
#     if not result:
#         return []
#     return result.get("value", [])
#
#
# def build_and_save_list_cache(items: list[dict]) -> None:
#     cache = {"by_index": {}, "by_name": {}}
#     for idx, item in enumerate(items, start=1):
#         list_id = item.get("id", "")
#         if not list_id:
#             continue
#         name = (item.get("displayName") or "").strip().lower()
#         cache["by_index"][str(idx)] = list_id
#         if name and name not in cache["by_name"]:
#             cache["by_name"][name] = list_id
#     LIST_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
#     LIST_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
#
#
# def build_and_save_task_cache(list_id: str, items: list[dict]) -> None:
#     cache = {"lists": {}}
#     if TASK_CACHE_FILE.exists():
#         try:
#             old = json.loads(TASK_CACHE_FILE.read_text(encoding="utf-8"))
#             if isinstance(old, dict) and isinstance(old.get("lists"), dict):
#                 cache = old
#         except Exception:
#             pass
#
#     mapping = {"by_index": {}, "by_short": {}, "by_title": {}}
#     for idx, item in enumerate(items, start=1):
#         task_id = item.get("id", "")
#         if not task_id:
#             continue
#         short = f"t{idx}"
#         title = (item.get("title") or "").strip().lower()
#
#         mapping["by_index"][str(idx)] = task_id
#         mapping["by_short"][short] = task_id
#         if title and title not in mapping["by_title"]:
#             mapping["by_title"][title] = task_id
#
#     cache["lists"][list_id] = mapping
#     TASK_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
#     TASK_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
#
#
# async def resolve_list_ref(list_ref: str, timeout: int) -> str:
#     ref = list_ref.strip()
#     if not ref:
#         raise SystemExit("Missing list reference")
#
#     if len(ref) > 20:
#         return ref
#
#     if LIST_CACHE_FILE.exists():
#         try:
#             cache = json.loads(LIST_CACHE_FILE.read_text(encoding="utf-8"))
#         except Exception as exc:
#             raise SystemExit(f"List cache file is corrupted: {LIST_CACHE_FILE} ({exc})") from exc
#         by_index = cache.get("by_index", {})
#         by_name = cache.get("by_name", {})
#         if ref in by_index:
#             return by_index[ref]
#         name_key = ref.lower()
#         if name_key in by_name:
#             return by_name[name_key]
#
#     items = await fetch_lists(timeout)
#     build_and_save_list_cache(items)
#     ref_lower = ref.lower()
#     for idx, item in enumerate(items, start=1):
#         list_id = item.get("id", "")
#         name = (item.get("displayName") or "").strip()
#         if ref == str(idx) or ref == list_id or ref_lower == name.lower():
#             return list_id
#
#     raise SystemExit(f"Unable to resolve list ref: {list_ref}. Run `python todo_cli.py lists` first.")
#
#
# async def resolve_task_ref(list_id: str, task_ref: str, timeout: int) -> str:
#     ref = task_ref.strip()
#     if not ref:
#         raise SystemExit("Missing task reference")
#
#     if len(ref) > 20:
#         return ref
#
#     if TASK_CACHE_FILE.exists():
#         try:
#             cache = json.loads(TASK_CACHE_FILE.read_text(encoding="utf-8"))
#         except Exception as exc:
#             raise SystemExit(f"Task cache file is corrupted: {TASK_CACHE_FILE} ({exc})") from exc
#         list_map = cache.get("lists", {}).get(list_id, {})
#         by_index = list_map.get("by_index", {})
#         by_short = list_map.get("by_short", {})
#         by_title = list_map.get("by_title", {})
#
#         if ref in by_index:
#             return by_index[ref]
#         if ref in by_short:
#             return by_short[ref]
#         ref_lower = ref.lower()
#         if ref_lower in by_title:
#             return by_title[ref_lower]
#
#     items = await fetch_tasks(list_id, timeout)
#     build_and_save_task_cache(list_id, items)
#     ref_lower = ref.lower()
#     for idx, item in enumerate(items, start=1):
#         task_id = item.get("id", "")
#         title = (item.get("title") or "").strip()
#         if ref == str(idx) or ref == f"t{idx}" or ref == task_id or ref_lower == title.lower():
#             return task_id
#
#     raise SystemExit(f"Unable to resolve task ref: {task_ref}. Run `python todo_cli.py tasks --list <...>` first.")
#
#
# async def cmd_lists(timeout: int) -> None:
#     items = await fetch_lists(timeout)
#     if not items:
#         print("No todo lists found.")
#         return
#
#     build_and_save_list_cache(items)
#     for idx, item in enumerate(items, start=1):
#         print(f"{idx:>2}  {item.get('displayName')}")
#     print(f"Full list-id mapping saved to: {LIST_CACHE_FILE.resolve()}")
#
#
# async def cmd_tasks(list_ref: str, timeout: int) -> None:
#     list_id = await resolve_list_ref(list_ref, timeout)
#     items = await fetch_tasks(list_id, timeout)
#     if not items:
#         print("No tasks found.")
#         return
#
#     build_and_save_task_cache(list_id, items)
#
#     for idx, item in enumerate(items, start=1):
#         status = item.get("status", "unknown")
#         short = f"t{idx}"
#         print(f"{idx:>2}  {short:>4}  [{status}]  {item.get('title')}")
#
#     print(f"Task-id mapping saved to: {TASK_CACHE_FILE.resolve()} (list: {list_id})")
#
#
# async def cmd_create(list_ref: str, title: str, timeout: int, content: str | None = None) -> None:
#     list_id = await resolve_list_ref(list_ref, timeout)
#     payload = {"title": title}
#     if content:
#         payload["body"] = {"content": content, "contentType": "text"}
#     item = await graph_request("POST", f"/me/todo/lists/{list_id}/tasks", timeout, payload=payload) or {}
#     print("Created task:")
#     print(f"id: {item.get('id')}")
#     print(f"title: {item.get('title')}")
#     print(f"status: {item.get('status')}")
#
#
# async def cmd_update(
#     list_ref: str, task_ref: str, timeout: int, title: str | None, content: str | None
# ) -> None:
#     if not title and not content:
#         raise SystemExit("Update requires at least one field: --title or --content")
#
#     list_id = await resolve_list_ref(list_ref, timeout)
#     task_id = await resolve_task_ref(list_id, task_ref, timeout)
#
#     payload = {}
#     if title:
#         payload["title"] = title
#     if content:
#         payload["body"] = {"content": content, "contentType": "text"}
#
#     item = (
#         await graph_request(
#             "PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", timeout, payload=payload
#         )
#         or {}
#     )
#     print("Updated task:")
#     print(f"id: {item.get('id')}")
#     print(f"title: {item.get('title')}")
#     print(f"status: {item.get('status')}")
#
#
# async def cmd_complete(list_ref: str, task_ref: str, timeout: int) -> None:
#     list_id = await resolve_list_ref(list_ref, timeout)
#     task_id = await resolve_task_ref(list_id, task_ref, timeout)
#     payload = {"status": "completed"}
#     item = (
#         await graph_request(
#             "PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", timeout, payload=payload
#         )
#         or {}
#     )
#     print("Completed task:")
#     print(f"id: {item.get('id')}")
#     print(f"title: {item.get('title')}")
#     print(f"status: {item.get('status')}")
#
#
# async def cmd_delete(list_ref: str, task_ref: str, timeout: int) -> None:
#     list_id = await resolve_list_ref(list_ref, timeout)
#     task_id = await resolve_task_ref(list_id, task_ref, timeout)
#     await graph_request("DELETE", f"/me/todo/lists/{list_id}/tasks/{task_id}", timeout)
#     print(f"Deleted task: {task_id}")
#
#
# def main():
#     parser = argparse.ArgumentParser(description="Microsoft To-Do CLI")
#     parser.add_argument("--timeout", type=int, default=30, help="Network timeout in seconds")
#     subparsers = parser.add_subparsers(dest="command", required=True)
#
#     # lists
#     subparsers.add_parser("lists", help="List all todo lists")
#
#     # tasks
#     tasks_p = subparsers.add_parser("tasks", help="List tasks in a list")
#     tasks_p.add_argument("--list", required=True, help="List index, name, or ID")
#
#     # create
#     create_p = subparsers.add_parser("create", help="Create a new task")
#     create_p.add_argument("--list", required=True, help="List index, name, or ID")
#     create_p.add_argument("--title", required=True, help="Task title")
#     create_p.add_argument("--content", help="Task body content")
#
#     # update
#     update_p = subparsers.add_parser("update", help="Update an existing task")
#     update_p.add_argument("--list", required=True, help="List index, name, or ID")
#     update_p.add_argument("--task", required=True, help="Task index (e.g. 1), short-id (e.g. t1), or ID")
#     update_p.add_argument("--title", help="New task title")
#     update_p.add_argument("--content", help="New task body content")
#
#     # complete
#     complete_p = subparsers.add_parser("complete", help="Mark a task as completed")
#     complete_p.add_argument("--list", required=True, help="List index, name, or ID")
#     complete_p.add_argument("--task", required=True, help="Task index, short-id, or ID")
#
#     # delete
#     delete_p = subparsers.add_parser("delete", help="Delete a task")
#     delete_p.add_argument("--list", required=True, help="List index, name, or ID")
#     delete_p.add_argument("--task", required=True, help="Task index, short-id, or ID")
#
#     args = parser.parse_args()
#
#     loop = asyncio.get_event_loop()
#     if args.command == "lists":
#         loop.run_until_complete(cmd_lists(args.timeout))
#     elif args.command == "tasks":
#         loop.run_until_complete(cmd_tasks(args.list, args.timeout))
#     elif args.command == "create":
#         loop.run_until_complete(cmd_create(args.list, args.title, args.timeout, args.content))
#     elif args.command == "update":
#         loop.run_until_complete(cmd_update(args.list, args.task, args.timeout, args.title, args.content))
#     elif args.command == "complete":
#         loop.run_until_complete(cmd_complete(args.list, args.task, args.timeout))
#     elif args.command == "delete":
#         loop.run_until_complete(cmd_delete(args.list, args.task, args.timeout))
#
#
# if __name__ == "__main__":
#     main()
