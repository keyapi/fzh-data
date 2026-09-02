# SPS Selenium 自动化本地部署方案

## 概述

这是一个将原本运行在 Deepnote 上的 SPS Commerce Selenium 自动化脚本迁移到本地 Windows 11 环境的完整解决方案。使用 Docker 容器确保 Chrome 和 ChromeDriver 版本固定，避免兼容性问题。

## 功能特性

- ✅ **版本固定**: Chrome 114.0.5735.90 和匹配的 ChromeDriver
- ✅ **环境隔离**: Docker 容器不影响系统浏览器
- ✅ **自动化任务**: 每天自动发送 Inventory Advice
- ✅ **定时执行**: Windows 任务计划程序支持
- ✅ **错误处理**: 完善的日志记录和重试机制
- ✅ **截图保存**: 自动保存执行过程截图

## 系统要求

- Windows 11
- Docker Desktop
- 管理员权限（用于设置定时任务）

## 快速开始

### 1. 准备环境

确保 Docker Desktop 已安装并运行：

```bash
docker version
```

### 2. 构建镜像

双击运行 `build_image.bat` 或在命令行执行：

```cmd
build_image.bat
```

### 3. 配置凭据

创建 `.env` 文件并填真实凭据（config.py 只读 env，不内置默认值）：

```env
SPS_EMAIL=your_email@example.com
SPS_PASSWORD=your_password
```

### 4. 运行自动化

双击运行 `run_sps.bat` 或在命令行执行：

```cmd
run_sps.bat
```

### 5. 设置定时任务

以管理员身份运行 `setup_schedule.bat`：

```cmd
# 右键点击 setup_schedule.bat -> "以管理员身份运行"
```

## 文件结构

```
SPS_Selenium_Local/
├── Dockerfile                    # Docker 镜像配置
├── docker-compose.yml           # Docker Compose 配置
├── requirements.txt             # Python 依赖
├── sps_automation.py           # 主自动化脚本
├── config.py                   # 配置管理
├── .env                        # 环境变量（可选）
├── run_sps.bat                 # 执行脚本
├── build_image.bat             # 构建镜像脚本
├── setup_schedule.bat          # 设置定时任务
├── remove_schedule.bat         # 删除定时任务
├── screenshots/                # 截图保存目录
├── logs/                       # 日志保存目录
└── README.md                   # 使用说明
```

## 批处理脚本说明

### `build_image.bat`
- 构建 Docker 镜像
- 创建必要的目录
- 可选择清理旧镜像

### `run_sps.bat`
- 执行完整的自动化流程
- 自动构建镜像（如果需要）
- 显示执行结果和日志

### `setup_schedule.bat`
- 设置 Windows 定时任务
- 每天北京时间 12:35 自动执行
- 需要管理员权限

### `remove_schedule.bat`
- 删除已设置的定时任务
- 需要管理员权限

## 配置说明

### 环境变量配置

可以通过 `.env` 文件或环境变量配置以下参数：

```env
# 登录凭据
SPS_EMAIL=your_sps_email@example.com
SPS_PASSWORD=your_password

# 浏览器设置
HEADLESS=true
WINDOW_SIZE=1280,720

# 等待时间（秒）
LOGIN_WAIT=120
PAGE_LOAD_WAIT=60
ELEMENT_WAIT=30
ACTION_WAIT=10

# 日期偏移
DAY_OFFSET=7

# 模板设置
TEMPLATE_CUTOFF_DATE=2025-10-02
TEMPLATE_BEFORE_CUTOFF=IA Template 20250925 0xBlack138 till1009
TEMPLATE_AFTER_CUTOFF=IA Template 20250605 x100

# 重试设置
MAX_RETRIES=3
RETRY_DELAY=30
```

## 日志和截图

### 日志文件
- 位置: `logs/sps_automation.log`
- 包含详细的执行日志和错误信息
- 支持中文字符

### 截图文件
- 位置: `screenshots/` 目录
- 自动保存关键步骤截图
- 错误时自动保存错误截图

## 故障排除

### 常见问题

1. **Docker 未运行**
   ```
   解决方案: 启动 Docker Desktop
   ```

2. **权限不足**
   ```
   解决方案: 以管理员身份运行批处理脚本
   ```

3. **网络连接问题**
   ```
   解决方案: 检查网络连接和防火墙设置
   ```

4. **Chrome 版本问题**
   ```
   解决方案: Docker 容器使用固定版本，不受系统影响
   ```

### 调试模式

如需调试，可以修改 `docker-compose.yml` 中的环境变量：

```yaml
environment:
  - HEADLESS=false  # 显示浏览器窗口
```

## 定时任务管理

### 查看任务状态
```cmd
schtasks /query /tn "SPS_Selenium_Daily"
```

### 手动运行任务
```cmd
schtasks /run /tn "SPS_Selenium_Daily"
```

### 禁用任务
```cmd
schtasks /change /tn "SPS_Selenium_Daily" /disable
```

### 启用任务
```cmd
schtasks /change /tn "SPS_Selenium_Daily" /enable
```

## 版本信息

- Chrome: 114.0.5735.90 (固定版本)
- ChromeDriver: 114.0.5735.90 (匹配版本)
- Selenium: 4.34.2
- Python: 3.10 (Ubuntu 20.04)

## 技术支持

如遇问题，请检查：
1. `logs/sps_automation.log` 日志文件
2. `screenshots/` 目录中的截图
3. Docker 容器状态: `docker ps -a`
4. Windows 事件查看器中的任务计划程序日志

## 更新说明

如需更新脚本或配置：
1. 修改相应文件
2. 重新运行 `build_image.bat`
3. 测试运行 `run_sps.bat`
