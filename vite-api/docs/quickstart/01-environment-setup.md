# 环境配置

## 1. API Key

测试环境 API Key 已提供:

```
H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd
```

所有请求需要在 Header 中携带:
```
x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd
```

## 2. Base URL

测试环境 API 地址:
```
https://test-api.vitedirect.com
```

## 3. 验证连通性

```bash
# 简单连通性测试
curl -X GET "https://test-api.vitedirect.com/user/account" \
  -H "x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd"
```

预期返回:
```json
{"balance": 2000}
```

## 4. 单位说明

> ⚠️ **API 只接受 lbs (磅) 和 inch (英寸)**

| 维度 | 单位 | 示例 |
|------|------|------|
| 重量 | lbs | `"weight": 2` ≈ 0.9 kg |
| 尺寸 | inch | `"length": 10` ≈ 25.4 cm |

## 5. 相关链接

| 资源 | 地址 |
|------|------|
| API 文档 | http://docs.vitedirect.com/ |
| 测试系统 | https://easygo-dev.vitedirect.com/labelHistory |
| API 规范源 | `/config/gofo.yaml` (GOFO Express) |

> 完整凭证参考: [测试凭证](../test-guide/test-credentials.md)
