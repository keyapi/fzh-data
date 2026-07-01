# 获取 Access Token

### 注意
```
为了安全考虑，开发者 请勿 将 access_token 返回给前端，需要开发者保存在后台，所有访问api的请求由必须由后台发起。
```

```
获取access_token是调用赛狐API接口的第一步，相当于创建了一个登录凭证，其它的业务API接口，都需要依赖于access_token来鉴权调用者身份。
```


### 请求方式： GET
### 请求地址
```
https://openapi.sellfox.com/api/oauth/v2/token.json
```
### 请求参数：
|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|client_id|query|string| 否 |应用的APPID ,如何获取请查看[申请API权限](doc-1748360)|
|client_secret|query|string| 否 |client_secret如何获取请查看[申请API权限](doc-1748360)|
|grant_type|query|string| 否 |固定为client_credentials|
### 请求示例：
```
https://openapi.sellfox.com/api/oauth/v2/token.json?client_id=aaaa&client_secret=bbb&grant_type=cccc
```
### 返回结果：
```
{
    "code": 0,
    "msg": "success",
    "data": {
        "access_token": "d20d9d20-5db0-429a-8390-3694265e297c",
        "expires_in": 86400000
    },
    "requestId": "b8d02feb-4892-4cc8-8cb7-890c1b333908"
}
```

### 返回参数说明：

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|code|integer(int32)|false|none||code(默认0代表成功)|
|data|[OpenapiTokenVo](#schemaopenapitokenvo)|false|none||none|
|data>>access_token|string|false|none||access_token|
|data>>expires_in|integer(int64)|false|none||有效期倒计时,为0时token失效(单位为毫秒)|
|msg|string|false|none||错误信息|
|requestId|string|false|none||none|
### Token使用注意事项：
```
1. 开发者需要缓存access_token，用于后续接口的调用，（注意：不能频繁调用api/oauth/v2/token.json 接口，否则会受到频率拦截），当access_token失效或过期时，需要重新获取。

2. access_token的有效期通过返回的expires_in来传达，正常情况下为（24小时），有效期内重复获取返回相同结果，过期后获取会返回新的access_token。

3. 赛狐可能会出于运营需要，提前使access_token失效，开发者应实现access_token失效时重新获取的逻辑。
```
