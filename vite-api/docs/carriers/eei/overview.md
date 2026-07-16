# EEI API 概述

## 基本信息

| 项目 | 说明 |
|------|------|
| API 文档源 | `/config/eei.yaml` |
| 基础 URL | `https://test-api.vitedirect.com` |
| 认证 | `x-api-key` |

## 用途

EEI（Electronic Export Information）用于美国出口货物的电子申报信息提交。当通过 FedEx/UPS 国际运输时，可能需要同时提交 EEI 信息。

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/eei` | 提交 EEI 申报 |

> 详细信息请参考 API 文档源文件 `/config/eei.yaml`
