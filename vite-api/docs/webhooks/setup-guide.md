# Webhook 配置指南

## 概述

Webhook 允许您在标签处理完成时接收异步通知，无需手动轮询 API。

## 配置步骤

### Step 1: 准备 Webhook 接收端

您需要提供一个公网可访问的 HTTP/HTTPS 端点来接收通知。可以是：

- 自建服务器
- 云函数 (AWS Lambda, Google Cloud Function)
- 第三方 Webhook 聚合服务

### Step 2: 在 EEVEE 系统配置 Webhook URL

1. 登录 [EEVEE 系统](https://easygo-dev.vitedirect.com/labelHistory)
2. 进入 **组织管理页面**（需管理员权限）
3. 找到 API Hook URL 输入框
4. 填入您的 Webhook 接收地址
5. 点击确认

### Step 3: 验证订阅

配置完成后，Vite 系统会向您的 Webhook URL 发送一条订阅确认消息。您的接收端需要：

1. 接收消息
2. 解析消息中的 `SubscribeURL` 字段
3. 访问该 URL 完成订阅确认

### Step 4: 接收通知

订阅确认后，每次标签处理完成，Vite 系统会自动向您的 Webhook URL 推送通知。

## 通知格式

```json
{
  "orderId": "string",
  "status": "string",
  "url": "string",
  "trackingNumber": "string"
}
```

## 推荐实践

- 设置合理的超时处理（建议 5 秒内响应）
- 对通知返回 200 状态码确认接收
- 实现幂等处理，避免重复通知导致重复操作
- 记录通知日志用于排查问题

## 当前状态

> ⏳ API Hook URL 尚未填写，请联系管理员配置。
