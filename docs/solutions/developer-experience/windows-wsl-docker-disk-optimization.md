---
title: Windows WSL2 Docker VHDX disk space optimization and migration
date: 2026-07-27
category: developer-experience
module: development-workflow
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - C drive runs low on space and large ext4.vhdx files are found under AppData
  - Docker Desktop or WSL2 is used on Windows for development
  - Docker data needs to be moved from SSD C drive to a secondary HDD drive
tags: [wsl2, docker-desktop, vhdx, windows-11, disk-space, dev-environment]
---

# Windows WSL2 Docker VHDX disk space optimization and migration

## Context

This project uses Docker Desktop with WSL2 backend on Windows for local development. Docker and WSL store their virtual disks as `.vhdx` files that auto-expand with usage but never auto-shrink. Over time, these files consume tens of GB on the C drive. After migration to a secondary drive, misconfigured WSL resource limits can cause 100% disk IO and system sluggishness.

This documents a complete cleanup pipeline: diagnose, compact, migrate, and configure resource limits to prevent recurrence.

## Guidance

### 1. Diagnose the situation

```powershell
# List all WSL distros and their states
wsl -l -v

# Check VHDX file sizes
dir "$env:LOCALAPPDATA\Docker\wsl\data\ext4.vhdx"
dir "$env:LOCALAPPDATA\Docker\wsl\main\ext4.vhdx"
dir "$env:LOCALAPPDATA\Packages\CanonicalGroupLimited.Ubuntu22.04LTS_79rhkp1fndgsc\LocalState\ext4.vhdx"

# Check C drive free space
Get-PSDrive C
```

Key WSL distros to understand:
- `docker-desktop` — Docker engine runtime (~100-200 MB, stays on C)
- `docker-desktop-data` — Docker images, containers, volumes (10-100+ GB, the main target)
- `Ubuntu-22.04` (or similar) — standalone WSL Linux distro (if installed separately)

### 2. Compact VHDX files (immediate space recovery)

VHDX files store deleted space that diskpart can reclaim without data loss:

```powershell
# Shut down everything first
wsl --shutdown

# Compact each VHDX via diskpart (requires Administrator)
diskpart
select vdisk file="C:\Users\<user>\AppData\Local\Docker\wsl\data\ext4.vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
# ... repeat for each VHDX
exit
```

This typically recovers 30-40% of space immediately (e.g., 33 GB -> 20 GB).

### 3. Migrate WSL distros off C drive

**Ubuntu WSL distro** (via export/import):

```powershell
wsl --export Ubuntu-22.04 D:\WSL\Ubuntu-22.04.vhdx --vhd
wsl --unregister Ubuntu-22.04
wsl --import Ubuntu-22.04 D:\WSL\Ubuntu-22.04 D:\WSL\Ubuntu-22.04.vhdx --vhd

# Fix default user (import resets to root)
wsl -d Ubuntu-22.04 -u root
echo -e "[user]\ndefault=<your-username>" | tee /etc/wsl.conf
wsl --terminate Ubuntu-22.04
```

**Docker Desktop data** (prefer the GUI method):

1. Docker Desktop -> Settings -> Resources -> Advanced
2. Disk image location -> Browse to a folder on the target drive (e.g., `D:\DockerData`)
3. Apply & Restart

If the GUI method fails (known bugs in certain Docker Desktop versions), fall back to WSL export/import:

```powershell
wsl --shutdown
wsl --export docker-desktop-data D:\Docker\docker-desktop-data.tar
wsl --unregister docker-desktop-data
wsl --import docker-desktop-data D:\Docker\data D:\Docker\docker-desktop-data.tar --version 2
```

### 4. Configure WSL resource limits

Create or edit `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
memory=8GB        # 25-50% of physical RAM
processors=4      # 50% of logical cores
swap=4GB          # match or exceed memory value
vmIdleTimeout=60000

[experimental]
hostAddressLoopback=true
autoMemoryReclaim=gradual
```

Key parameters:
- `memory` — hard cap for WSL2 VM. Too low causes OOM kills; too high starves Windows
- `swap` — set to at least the `memory` value. Setting it to 0 disables swap and risks OOM
- `vmIdleTimeout` — milliseconds before idle VM releases resources (important for machines that stay on)
- `autoMemoryReclaim=gradual` — returns idle WSL memory to Windows over time

Apply with: `wsl --shutdown`

### 5. Regular maintenance

```powershell
# Prune unused Docker images, containers, volumes
docker system prune -a --volumes

# Clean old WSL swap files from Temp
Remove-Item "$env:LOCALAPPDATA\Temp\*\swap.vhdx" -Force -ErrorAction SilentlyContinue
```

## Why This Matters

**Disk space**: A 256 GB SSD C drive with Docker and WSL can lose 40-50 GB to VHDX bloat alone. Combined with Windows updates and application data, this can leave under 20 GB free — enough to cause system instability.

**Disk I/O**: WSL2 defaults to 50% of RAM and can swap aggressively to the VHDX file. When Docker containers bind-mount Windows paths (e.g., `D:\projects\...`), every file access goes through the 9P cross-filesystem protocol (NTFS -> 9P translation -> WSL2 -> Docker), multiplying I/O overhead. Without `.wslconfig` limits, this can saturate the disk at 100% utilization.

**SSD vs HDD**: If Docker data is moved from an SSD (C:) to an HDD (D:), container I/O will be slower due to the HDD's lower IOPS. The `.wslconfig` swap limit prevents swap thrashing from amplifying this further.

## When to Apply

- After setting up Docker Desktop on a new Windows machine
- When C drive free space drops below 30 GB
- After noticing system sluggishness when Docker is running
- When migrating to a new computer and setting up the dev environment

## Examples

**Before** (C drive nearly full, VHDX bloat):

| File | Size |
|------|------|
| Docker data VHDX | 33.2 GB |
| Ubuntu WSL VHDX | 13.2 GB |
| C drive free | ~22 GB |

**After** (compacted + Ubuntu migrated + Docker moved to D):

| File | Size | Location |
|------|------|----------|
| Docker data VHDX | 19.7 GB | D:\DockerData\ |
| Ubuntu WSL VHDX | 13.0 GB | D:\WSL\ |
| C drive free | ~47 GB | — |

## Related

- [Docker Desktop WSL2 disk image location docs](https://docs.docker.com/desktop/settings/windows/#advanced)
- [Microsoft WSL configure global options](https://learn.microsoft.com/en-us/windows/wsl/wsl-config#wslconfig)
- Zhihu article covering the same migration + IO issue: "Docker Desktop 迁移到 D 盘后越用越卡？WSL2 磁盘 IO 100% 排查与修复" (2026-06-30)
