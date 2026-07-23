# 获取SHEIN在线产品（子体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/shein/product/getChildInfo.json:
    post:
      summary: 获取SHEIN在线产品（子体）
      deprecated: false
      description: 用户获取自身SHEIN店铺的子体产品信息
      operationId: getChildInfoUsingPOST_1
      tags:
        - 多平台/销售
        - SHEIN在线产品
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
              $ref: '#/components/schemas/SheinProductChildInfoOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABSheinProductChildInfoOpenVO%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782545-run
components:
  schemas:
    SheinProductChildInfoOpenQo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体ID
      title: SheinProductChildInfoOpenQo
      x-apifox-orders:
        - parentId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«SheinProductChildInfoOpenVO»»:
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
            $ref: '#/components/schemas/SheinProductChildInfoOpenVO'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«SheinProductChildInfoOpenVO»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SheinProductChildInfoOpenVO:
      type: object
      properties:
        parentId:
          type: string
          description: 父体id
        imageUrl:
          type: string
          description: 图片
        msku:
          type: string
          description: MSKU：卖家设置SKU货号
        itemId:
          type: string
          description: 产品ID：平台分配的SKU编码
        salesmanNameListStr:
          type: string
          description: 业务员
        state:
          type: string
          description: 状态
        commodityName:
          type: string
          description: 已配对商品品名
        commoditySku:
          type: string
          description: 已配对商品SKU
        attributeValues:
          type: string
          description: 属性
        productPriceList:
          type: array
          description: 产品价格
          items: &ref_0
            $ref: '#/components/schemas/SheinProductPriceOpenVO'
        supplyPriceList:
          type: array
          description: 供应商价格
          items: *ref_0
        totalInventoryQty:
          type: string
          description: 总库存
        totalLockedInventoryQty:
          type: string
          description: 锁定库存
        totalUsableInventoryQty:
          type: string
          description: 可用库存
        shelfDateTime:
          type: string
          description: 上架时间
        updateTime:
          type: string
          description: 更新时间
      title: SheinProductChildInfoOpenVO
      x-apifox-orders:
        - parentId
        - imageUrl
        - msku
        - itemId
        - salesmanNameListStr
        - state
        - commodityName
        - commoditySku
        - attributeValues
        - productPriceList
        - supplyPriceList
        - totalInventoryQty
        - totalLockedInventoryQty
        - totalUsableInventoryQty
        - shelfDateTime
        - updateTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SheinProductPriceOpenVO:
      type: object
      properties:
        priceType:
          type: integer
          format: int32
          description: 价格类型 0-售价，1-供货价
        currency:
          type: string
          description: 币种
        basePrice:
          type: string
          description: price_type 0-原价， 1-供货价
        specialPrice:
          type: string
          description: price_type 0-特价， 1-供货价
      title: SheinProductPriceOpenVO
      x-apifox-orders:
        - priceType
        - currency
        - basePrice
        - specialPrice
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
