# 获取TikTok在线产品（全托子体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/tiktok/fullyManaged/product/getChildInfo.json:
    post:
      summary: 获取TikTok在线产品（全托子体）
      deprecated: false
      description: 用户获取自身TikTok店铺（全托）的子体产品信息
      operationId: getChildInfoUsingPOST_4
      tags:
        - 多平台/销售
        - TiKTok全托在线产品
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
              $ref: '#/components/schemas/TiktokFullyManagedProductChildInfoOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABTiktokFullyManagedProductChildInfoOpenVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782553-run
components:
  schemas:
    TiktokFullyManagedProductChildInfoOpenQo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体ID
      title: TiktokFullyManagedProductChildInfoOpenQo
      x-apifox-orders:
        - parentId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«TiktokFullyManagedProductChildInfoOpenVo»»:
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
            $ref: '#/components/schemas/TiktokFullyManagedProductChildInfoOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«TiktokFullyManagedProductChildInfoOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TiktokFullyManagedProductChildInfoOpenVo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体Id
        shopId:
          type: string
          description: 店铺id
        platformProductId:
          type: string
          description: 平台产品id（父体）,对应 platform_spu_code
        itemId:
          type: string
          description: 平台产品id,对应 sku_code
        msku:
          type: string
          description: 平台msku,对应 external_sku_code
        status:
          type: string
          description: 产品状态
        productSkuInventoryVoList:
          type: array
          description: 库存信息
          items:
            $ref: '#/components/schemas/TiktokFmProductSkuInventoryOpenVo'
        devIdAndNameVoList:
          type: array
          description: 业务员信息
          items:
            $ref: '#/components/schemas/DevIdAndNameOpenVo'
        salesmanIdList:
          type: array
          description: 业务员id列表
          items:
            type: string
        matchStatus:
          type: string
          description: 配对状态
        commoditySku:
          type: string
          description: 已配对商品SKU
        commodityName:
          type: string
          description: 已配对商品品名
      title: TiktokFullyManagedProductChildInfoOpenVo
      x-apifox-orders:
        - parentId
        - shopId
        - platformProductId
        - itemId
        - msku
        - status
        - productSkuInventoryVoList
        - devIdAndNameVoList
        - salesmanIdList
        - matchStatus
        - commoditySku
        - commodityName
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    DevIdAndNameOpenVo:
      type: object
      properties:
        devName:
          type: string
          description: 业务员名称
      title: DevIdAndNameOpenVo
      x-apifox-orders:
        - devName
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TiktokFmProductSkuInventoryOpenVo:
      type: object
      properties:
        inventory:
          type: string
          description: 可售库存
        occupyInventory:
          type: string
          description: 占用库存
      title: TiktokFmProductSkuInventoryOpenVo
      x-apifox-orders:
        - inventory
        - occupyInventory
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
