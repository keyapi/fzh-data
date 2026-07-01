# 获取Temu跨境店的在线产品（子体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/temu/product/getChildInfo.json:
    post:
      summary: 获取Temu跨境店的在线产品（子体）
      deprecated: false
      description: 用户获取自身Temu跨境店铺的子体产品信息
      operationId: getChildInfoUsingPOST_3
      tags:
        - 多平台/销售
        - Temu跨境在线产品
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
              $ref: '#/components/schemas/ProductChildOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABTemuProductChildListOpenVo%C2%BB%C2%BB
          headers: {}
          x-apifox-name: ''
        '201':
          description: Created
          headers: {}
          x-apifox-name: ''
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: ''
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: ''
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: ''
      security: []
      x-order: '2147483647'
      x-apifox-folder: 多平台/销售
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782551-run
components:
  schemas:
    ProductChildOpenQo:
      type: object
      properties:
        parentId:
          type: string
      title: ProductChildOpenQo
      x-apifox-orders:
        - parentId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«TemuProductChildListOpenVo»»:
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
            $ref: '#/components/schemas/TemuProductChildListOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«TemuProductChildListOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TemuProductChildListOpenVo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体id
        skuId:
          type: string
          description: 商品的productSkuId
        extCode:
          type: string
          description: sku货号
        stockQuantity:
          type: string
          description: 库存
        createdAt:
          type: string
          description: 上架时间
        commodityMatchStatus:
          type: string
          description: 配对状态 0未配对 1已配对
        commoditySku:
          type: string
          description: 配对商品的sku
        salesmanNameList:
          type: array
          description: 业务员名称列表
          items:
            type: string
        specName:
          type: string
          description: 规格名称列表eg:[{"pSpecName":"颜色","specName":"红色"}]
        name:
          type: string
          description: 产品品名
        supplyPrice:
          type: string
          description: 产品供货价
        supplyCurrency:
          type: string
          description: 产品供货价的币种
        activityMinPrice:
          type: string
          description: 当前活动的最低价
        activityCurrency:
          type: string
          description: 币种
        createTime:
          type: string
          description: 创建时间
        updateTime:
          type: string
          description: 更新时间
      title: TemuProductChildListOpenVo
      x-apifox-orders:
        - parentId
        - skuId
        - extCode
        - stockQuantity
        - createdAt
        - commodityMatchStatus
        - commoditySku
        - salesmanNameList
        - specName
        - name
        - supplyPrice
        - supplyCurrency
        - activityMinPrice
        - activityCurrency
        - createTime
        - updateTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
