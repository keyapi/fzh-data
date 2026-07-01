# 生成sign（签名）

### 验签参数
所有验签参数来自完整请求url中

| 参数 | 描述 | 可选值|
| --- | --- | --- |
| access_token | 通过接口获取的token信息 | 参考 [获取 Access Token](doc-1589130) | 
| client_id | 开发者id |申请到的client_id |
| method |  请求方式 | post | 
| nonce |  请求随机整数| 13251,每次请求都需要不同 | 
| timestamp |  请求时间戳 (ms)| 示例：1668153260508 |
| url |  接口请求路径|示例：/api/order/pageList.json |


### 验签过程
以上参数按照{参数名=参数值}格式拼接，
```
access_token =d20d9d20-5db0-429a-8390-3694265e297c
```
所有参数之间按照参数名**排序后**用&隔开（requestBody中的业务参数不参与签名，一定要按照示例中的参数顺序）
```
access_token=d20d9d20-5db0-429a-8390-3694265e297c&client_id=2323&method=post&nonce=13251&timestamp=1668153260508&url=/api/order/pageList.json
```
对于拼接后参数使用Hmac SHA256进行加密，应用的client_secret为加密密钥。
### JAVA开发示例

```
    /**
     * 生成签名主方法
     *
     * @return
     */
    public static String genarateSign() throws Exception {
        Map<String, Object> params = new HashMap<>();
        // 接口请求路径
        params.put("url", "/openapi/api/commodity/pageList.json");
        params.put("method", "post");
        // 通过接口获取的token信息
        params.put("access_token", "d20d9d20-5db0-429a-8390-3694265e297c");
        // 开发者id
        params.put("client_id", "1111111");
        //请求时间戳 (ms)
        params.put("timestamp", "1668153260508");
        // 请求随机整数
        params.put("nonce", "888");
        // 参数排序
        String data = params.entrySet().stream().map(e -> e.getKey() + "=" + e.getValue()).sorted().collect(Collectors.joining("&"));
        // HmacSHA256签名, 【密钥】(需要填写跟clientId配对的密钥)
        return hmacsha256("【密钥】", data);
    }

    /**
     * HmacSHA256签名
     *
     * @param key  密钥 (需要填写跟clientId配对的密钥)
     * @param data 被签名字符串
     */
    public static String hmacsha256(String key, String data) throws Exception {
        Mac hmac = Mac.getInstance("HmacSHA256");
        SecretKeySpec secret_key = new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
        hmac.init(secret_key);
        return new String(Hex.encodeHex(hmac.doFinal(data.getBytes(StandardCharsets.UTF_8))));
    }
    
```
### Python开发示例
```
import hashlib
import hmac
import random
import time

access_token = 'd20d9d20-5db0-429a-8390-3694265e297c'
client_id = '1111111'
url = '/api/sale/profit/shop/pageList.json'
client_secret = 'fde212ff-588a-11ef-b1d4-0c42a1eda3d9'


def get_sign():
    print(access_token,url,client_id)
    # 请求参数
    params = {
        "url": url,
        "method": "post",
        "access_token": access_token,
        "client_id": client_id,
        "timestamp": int(time.time() * 1000),  # 请求时间戳 (ms)
        "nonce": random.randint(1, 99999),  # 请求随机整数
    }

    # 将参数按字典顺序排序，并拼接成url参数的格式
    sorted_params = sorted(params.items())  # 排序
    param_str = '&'.join([f"{key}={value}" for key, value in sorted_params])
    print(param_str)
    # 使用 HMAC SHA256 加密
    signature = hmac.new(client_secret.encode(), param_str.encode(), hashlib.sha256).hexdigest()
    print(signature)
```

### 签名秘钥
```
fde212ff-588a-11ef-b1d4-0c42a1eda3d9
```
### 签名字符串
```
access_token=d20d9d20-5db0-429a-8390-3694265e297c&client_id=1111111&method=post&nonce=888&timestamp=1668153260508&url=/openapi/api/commodity/pageList.json
```

### 生成签名
```
57bcbd213461d47e99e9b781c11f3fb37937127824272a30b95ddb5cbfea881e
```

### 请求业务接口url示例
```
https://openapi.sellfox.com/api/shop/pageList.json?access_token=d20d9d20-5db0-429a-8390-3694265e297c&client_id=1111111&timestamp=1668153260508&nonce=888&sign=57bcbd213461d47e99e9b781c11f3fb37937127824272a30b95ddb5cbfea881e
```
