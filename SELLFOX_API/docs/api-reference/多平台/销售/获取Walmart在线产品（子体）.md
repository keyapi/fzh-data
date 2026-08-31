# 获取Walmart在线产品（子体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/walmart/product/getChildInfo.json:
    post:
      summary: 获取Walmart在线产品（子体）
      deprecated: false
      description: 用户获取自身Walmart店铺的子体产品信息
      operationId: getChildInfoUsingPOST_7
      tags:
        - 多平台/销售
        - Walmart在线产品
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
              $ref: '#/components/schemas/WalmartProductChildInfoOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABWalmartProductChildInfoOpenVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782559-run
components:
  schemas:
    WalmartProductChildInfoOpenQo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体ID
        shopId:
          type: string
          description: 店铺Id
      title: WalmartProductChildInfoOpenQo
      x-apifox-orders:
        - parentId
        - shopId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«WalmartProductChildInfoOpenVo»»:
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
            $ref: '#/components/schemas/WalmartProductChildInfoOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«WalmartProductChildInfoOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WalmartProductChildInfoOpenVo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体
        shopId:
          type: string
          description: 店铺id
        shopName:
          type: string
          description: 店铺名称
        site:
          type: string
          description: 站点
        itemId:
          type: string
          description: 产品ID
        productName:
          type: string
          description: 标题
        mainImage:
          type: string
          description: 主图
        lifecycleStatus:
          type: string
          description: 产品状态
        sku:
          type: string
          description: MSKU
        commoditySku:
          type: string
          description: 已配对商品SKU
        commodityName:
          type: string
          description: 已配对商品品名
        variantAttributesValue:
          type: string
          description: 属性
        brand:
          type: string
          description: 沃尔玛品牌
        gtin:
          type: string
          description: GTIN
        upc:
          type: string
          description: UPC
        fulfillmentType:
          type: string
          description: 发货方式
        price:
          type: string
          description: 价格
        currency:
          type: string
          description: 币种
        promoPrice:
          type: string
          description: 促销价
        promoPriceCurrency:
          type: string
          description: 促销价币种
        inventory:
          type: string
          description: 库存
        publishedStatus:
          type: string
          description: 发布状态
        matchStatus:
          type: string
          description: 配对状态
        salesmanNameList:
          type: array
          description: 业务员
          items:
            type: string
        updateTime:
          type: string
          description: 更新时间
      title: WalmartProductChildInfoOpenVo
      x-apifox-orders:
        - parentId
        - shopId
        - shopName
        - site
        - itemId
        - productName
        - mainImage
        - lifecycleStatus
        - sku
        - commoditySku
        - commodityName
        - variantAttributesValue
        - brand
        - gtin
        - upc
        - fulfillmentType
        - price
        - currency
        - promoPrice
        - promoPriceCurrency
        - inventory
        - publishedStatus
        - matchStatus
        - salesmanNameList
        - updateTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
