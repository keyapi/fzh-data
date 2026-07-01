# 在线产品按ASIN匹配商品

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/order/api/product/matchByAsin.json:
    post:
      summary: 在线产品按ASIN匹配商品
      deprecated: false
      description: 支持批量匹配，会出现部分成功或部分失败的情况，只会返回匹配商品失败的错误提示信息，匹配成功的商品不会返回错误提示。
      operationId: matchByAsinUsingPOST
      tags:
        - 销售/在线产品配对
        - 销售
      parameters:
        - name: access_token
          in: query
          description: 通过获取token接口获得的token，详见 [获取 Access Token](doc-1589130)
          required: true
          example: '{{access_token}}'
          schema:
            type: string
        - name: client_id
          in: query
          description: client_id, 获取方式详见 [申请API权限](1748360)
          required: true
          example: '{{client_id}}'
          schema:
            type: string
        - name: timestamp
          in: query
          description: 13位毫秒时间戳，与当前时间差异不超过正负15分钟，示例：1668153260508
          required: true
          example: '121212'
          schema:
            type: string
        - name: nonce
          in: query
          description: '随机整数值，保证每个请求唯一，示例：11251 '
          required: true
          example: '121212'
          schema:
            type: string
        - name: sign
          in: query
          description: 请求签名，详见  [生成sign（签名）](doc-1749562)
          required: true
          example: '121212121'
          schema:
            type: string
        - name: Content-Type
          in: header
          description: 固定再header位置加入Content-Type:application/json
          example: application/json
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ProductMatchAsinOpenQo'
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABProductMatchAsinErrorQo%C2%BB%C2%BB
          headers: {}
          x-apifox-name: OK
        '201':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Created
        '401':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Unauthorized
        '403':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Forbidden
        '404':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Not Found
      security: []
      x-apifox-folder: 销售/在线产品配对
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-119077677-run
components:
  schemas:
    ProductMatchAsinOpenQo:
      type: object
      required:
        - matchList
      properties:
        matchList:
          type: array
          description: 按ASIN匹配的参数列表，数量不能超过1000个
          items:
            $ref: '#/components/schemas/ProductMatchAsinItemOpenQo'
      title: ProductMatchAsinOpenQo
      x-apifox-orders:
        - matchList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ProductMatchAsinItemOpenQo:
      type: object
      required:
        - asin
        - sku
      properties:
        asin:
          type: string
          description: ASIN
        sku:
          type: string
          description: 商品SKU
        shopId:
          type: integer
          format: int32
          description: 店铺ID，选填；填写后仅对该shopId下对应的ASIN生效
      title: ProductMatchAsinItemOpenQo
      x-apifox-orders:
        - asin
        - sku
        - shopId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«ProductMatchAsinErrorQo»»:
      type: object
      properties:
        requestId:
          type: string
        code:
          type: integer
          format: int32
          description: code(默认0代表成功)
        msg:
          type: string
          description: 错误信息
        data:
          type: array
          description: 数据
          items:
            $ref: '#/components/schemas/ProductMatchAsinErrorQo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«ProductMatchAsinErrorQo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ProductMatchAsinErrorQo:
      type: object
      required:
        - asin
        - sku
        - errorMsg
      properties:
        asin:
          type: string
          description: ASIN
        sku:
          type: string
          description: 商品SKU
        errorMsg:
          type: string
          description: 错误提示
      title: ProductMatchAsinErrorQo
      x-apifox-orders:
        - asin
        - sku
        - errorMsg
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
