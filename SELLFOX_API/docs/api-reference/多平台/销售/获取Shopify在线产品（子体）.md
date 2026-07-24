# 获取Shopify在线产品（子体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/shopify/product/getChildList.json:
    post:
      summary: 获取Shopify在线产品（子体）
      deprecated: false
      description: 用户获取自身Shopify店铺的子体产品信息
      operationId: getChildListUsingPOST
      tags:
        - 多平台/销售
        - Shopify在线产品
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
              $ref: '#/components/schemas/ProductChildListOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABShopifyProductChildListOpenVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782547-run
components:
  schemas:
    ProductChildListOpenQo:
      type: object
      properties:
        parentIdList:
          type: array
          description: 父体ID列表，最多100个
          items:
            type: string
      title: ProductChildListOpenQo
      x-apifox-orders:
        - parentIdList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«ShopifyProductChildListOpenVo»»:
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
            $ref: '#/components/schemas/ShopifyProductChildListOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«ShopifyProductChildListOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShopifyProductChildListOpenVo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体Id
        shopId:
          type: string
          description: 店铺Id
        shopName:
          type: string
          description: 店铺名称
        platformProductId:
          type: string
          description: 平台产品id（父体）
        itemId:
          type: string
          description: 产品id
        itemName:
          type: string
          description: 变体名称
        displayName:
          type: string
          description: 显示名称
        attributeValues:
          type: array
          description: 属性值
          items:
            type: string
        imageUrl:
          type: string
          description: 图片
        msku:
          type: string
          description: msku
        salesmanNameList:
          type: array
          description: 业务员名称列表
          items:
            type: string
        barcode:
          type: string
          description: 条码
        availableForSale:
          type: string
          description: 可销售
        currency:
          type: string
          description: 货币
        originalPrice:
          type: string
          description: 原价
        currentPrice:
          type: string
          description: 促销价
        inventory:
          type: string
          description: 库存
        matchStatus:
          type: string
          description: 是否配对 1:已配对 0:未配对
        commoditySku:
          type: string
          description: 配对商品sku
        commodityName:
          type: string
          description: 配对商品名称
      title: ShopifyProductChildListOpenVo
      x-apifox-orders:
        - parentId
        - shopId
        - shopName
        - platformProductId
        - itemId
        - itemName
        - displayName
        - attributeValues
        - imageUrl
        - msku
        - salesmanNameList
        - barcode
        - availableForSale
        - currency
        - originalPrice
        - currentPrice
        - inventory
        - matchStatus
        - commoditySku
        - commodityName
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
