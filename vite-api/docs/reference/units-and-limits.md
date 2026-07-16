# 单位与限制

## 通用约束

### 单位制

| 维度 | 接受单位 | 不接受单位 |
|------|----------|------------|
| 重量 | **lbs** (磅) | kg (千克) |
| 尺寸 | **inch** (英寸) | cm (厘米) |

### 包裹尺寸限制

| 字段 | 最大值 |
|------|--------|
| length | 999 inch |
| width | 999 inch |
| height | 999 inch |

### 地址字段长度限制

| 字段 | 最大长度 |
|------|----------|
| fullName | 35 |
| company | 35 |
| address1 | 50 |
| address2 | 50 |
| city | 28 |
| state | 2 (州缩写) |
| zipCode | 10 |
| phoneNumber | 15 |

### 其他限制

| 项目 | 限制 |
|------|------|
| memo (标签备注) | ≤ 30 字符 |
| shipDate 格式 | `yyyy-MM-dd` |
| requestId 唯一性 | 必须全局唯一 |

## 单位换算参考

| 换算 | 值 |
|------|-----|
| 1 lbs → kg | 0.4536 |
| 1 kg → lbs | 2.2046 |
| 1 inch → cm | 2.54 |
| 1 cm → inch | 0.3937 |

### 快速换算示例

```javascript
// kg → lbs
lbs = kg * 2.2046

// cm → inch
inch = cm / 2.54
```
