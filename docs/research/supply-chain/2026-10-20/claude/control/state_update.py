import json
import os
import pathlib
import sys
import time

STATE = pathlib.Path(__file__).with_name("state.json")
LOCK = pathlib.Path(__file__).with_name("state.lock")
TASK_LOCKS = pathlib.Path(r"C:/Users/zhang/.agent-ops/fzh-data/locks")


def release_task_lock(task_id: str):
    # precheck holds locks/<task>.lock; clear it when the worker leaves in_progress
    try:
        (TASK_LOCKS / f"{task_id}.lock").unlink()
    except OSError:
        pass


def acquire():
    for _ in range(20):
        try:
            fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - LOCK.stat().st_mtime > 30:
                    LOCK.unlink()
                    continue
            except OSError:
                pass
            time.sleep(0.05)
    return False


def release():
    try:
        LOCK.unlink()
    except OSError:
        pass


def save(data):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE)


def main():
    if len(sys.argv) < 3:
        print("usage: state_update.py status <task-id> <status> [--note TEXT] | flag <key> <json-value>")
        return 2
    if not acquire():
        print("state busy")
        return 1
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        cmd = sys.argv[1]
        if cmd == "status":
            task_id, status = sys.argv[2], sys.argv[3]
            note = None
            if "--note" in sys.argv:
                note = sys.argv[sys.argv.index("--note") + 1]
            task = next((t for t in data.get("tasks", []) if t.get("id") == task_id), None)
            if not task:
                print(f"unknown task {task_id}")
                return 1
            task["status"] = status
            task["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            if note:
                task["note"] = note
            if status in ("completed", "blocked"):
                task.pop("claimed_at", None)
                task.pop("claimed_by", None)
            if status != "in_progress":
                release_task_lock(task_id)
            print(json.dumps(task, ensure_ascii=False))
        elif cmd == "flag":
            key, raw = sys.argv[2], sys.argv[3]
            try:
                value = json.loads(raw)
            except Exception:
                value = raw
            data.setdefault("quota", {})[key] = value
            data["quota"]["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            print(json.dumps({key: value}, ensure_ascii=False))
        else:
            print(f"unknown command {cmd}")
            return 2
        save(data)
        return 0
    finally:
        release()


if __name__ == "__main__":
    raise SystemExit(main())
