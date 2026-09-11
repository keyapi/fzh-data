"""在 NAS 上杀旧进程 + 反复删除重建设计稿，验证 deny ACE 只有 1 条。"""
import paramiko

from nas_env import nas_ssh

def run(ssh, cmd, sudo=False):
    """执行命令，返回 stdout 行列表"""
    if sudo and not cmd.startswith("sudo "):
        cmd = "sudo " + cmd
    _, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return out + err

def main():
    cfg = nas_ssh()
    print(f"连接 {cfg.host}:{cfg.port} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    for user in [cfg.user, "root"]:
        try:
            ssh.connect(cfg.host, port=cfg.port, username=user,
                        password=cfg.password, timeout=15,
                        allow_agent=False, look_for_keys=False)
            print(f"已连接: {user}\n")
            break
        except Exception as e:
            print(f"  {user} 失败: {e}")
    else:
        print("连接失败")
        return

    # ── Step 1: 查找旧进程 ──
    print("=== 1. 查找旧进程 ===")
    print(run(ssh, "ps aux | grep -E 'fix_design|inotifywait' | grep -v grep"))

    # ── Step 2: 杀旧进程 ──
    print("=== 2. 杀旧进程 ===")
    run(ssh, "pkill -9 -f fix_design_permissions", sudo=True)
    run(ssh, "pkill -9 -f inotifywait", sudo=True)
    run(ssh, "rm -f /volume1/技术部/.fix_design.lock", sudo=True)

    # ── Step 3: 确认 ──
    print("=== 3. 确认已清干净 ===")
    print(run(ssh, "ps aux | grep -E 'fix_design|inotifywait' | grep -v grep"))

    # ── Step 4: flock 单实例启动 ──
    print("=== 4. flock 单实例启动 ===")
    # 先确保旧锁清理
    run(ssh, "rm -f /volume1/技术部/.fix_design.lock", sudo=True)
    print(run(ssh, "nohup flock -xn /volume1/技术部/.fix_design.lock -c '/bin/bash /volume1/技术部/fix_design_permissions.sh' > /dev/null 2>&1 &"))

    # ── Step 5: 反复删除重建测试 ──
    print("=== 5. 反复删除重建测试 (5轮) ===")
    TEST_DIR = "/volume1/技术部/KS0001_三角靠枕/图片/设计稿"

    for i in range(1, 6):
        print(f"\n--- 第 {i} 轮 ---")
        run(ssh, f"rm -rf '{TEST_DIR}'")
        print("  已删除")
        import time; time.sleep(3)
        run(ssh, f"mkdir -p '{TEST_DIR}'")
        print("  已重建")
        time.sleep(3)

        out = run(ssh, f"/usr/syno/bin/synoacltool -get '{TEST_DIR}' 2>/dev/null | grep -F '视觉需求' | grep -c 'deny' || echo 0", sudo=True)
        count = out.strip()
        print(f"  deny ACE 条数: {count}")
        if count != "1":
            print("  *** 异常! ***")
            print(run(ssh, f"/usr/syno/bin/synoacltool -get '{TEST_DIR}' 2>/dev/null | grep -F '视觉需求'", sudo=True))

    ssh.close()
    print("\n断开连接")

if __name__ == "__main__":
    main()
