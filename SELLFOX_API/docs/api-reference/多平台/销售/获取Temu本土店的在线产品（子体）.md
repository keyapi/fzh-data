# 获取Temu本土店的在线产品（子体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/temu/local/product/getChildInfo.json:
    post:
      summary: 获取Temu本土店的在线产品（子体）
      deprecated: false
      description: 用户获取自身Temu本土店铺的子体产品信息
      operationId: getChildInfoUsingPOST_2
      tags:
        - 多平台/销售
        - Temu本土在线产品
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
                  #/components/schemas/OpenResult%C2%ABList%C2%ABTemuLocalProductChildListOpenVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782549-run
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
    OpenResult«List«TemuLocalProductChildListOpenVo»»:
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
            $ref: '#/components/schemas/TemuLocalProductChildListOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«TemuLocalProductChildListOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TemuLocalProductChildListOpenVo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体id
        shopType:
          type: string
          description: 店铺类型(美国本土:us)
        goodsId:
          type: string
          description: 商品的goodsId
        skuId:
          type: string
          description: 产品的skuId
        specName:
          type: string
          description: 规格
        thumbUrl:
          type: string
          description: 缩略图链接
        skuSn:
          type: string
          description: sku编码(sku的货号)
        quantity:
          type: string
          description: 库存量
        price:
          type: string
          description: 售价
        currency:
          type: string
          description: 币种信息,eg:USD
        status:
          type: string
          description: 商品状态
        goodsIsOnSale:
          type: string
          description: 商品是否在架
        trusteeship:
          type: string
          description: 托管类型:1全托管;0:半托管,本土店铺都是0
        commodityMatchStatus:
          type: string
          description: 配对状态
        commoditySku:
          type: string
          description: 配对的sku
        salesmanNameList:
          type: array
          description: 业务员名称列表
          items:
            type: string
        commodityName:
          type: string
          description: 配对的品名
        createTime:
          type: string
          description: 创建时间
        updateTime:
          type: string
          description: 更新时间
      title: TemuLocalProductChildListOpenVo
      x-apifox-orders:
        - parentId
        - shopType
        - goodsId
        - skuId
        - specName
        - thumbUrl
        - skuSn
        - quantity
        - price
        - currency
        - status
        - goodsIsOnSale
        - trusteeship
        - commodityMatchStatus
        - commoditySku
        - salesmanNameList
        - commodityName
        - createTime
        - updateTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
