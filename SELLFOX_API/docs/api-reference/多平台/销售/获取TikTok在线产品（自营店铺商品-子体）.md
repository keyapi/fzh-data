# 获取TikTok在线产品（自营店铺商品-子体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/tiktok/shop/product/getChildInfo.json:
    post:
      summary: 获取TikTok在线产品（自营店铺商品-子体）
      deprecated: false
      description: 用户获取自身TikTok店铺（自营店铺商品）的子体产品信息
      operationId: getChildInfoUsingPOST_6
      tags:
        - 多平台/销售
        - TiKTok自营店铺商品
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
              $ref: '#/components/schemas/TiktokShopProductChildInfoOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABTiktokShopProductChildInfoOpenVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782557-run
components:
  schemas:
    TiktokShopProductChildInfoOpenQo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体ID
      title: TiktokShopProductChildInfoOpenQo
      x-apifox-orders:
        - parentId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«TiktokShopProductChildInfoOpenVo»»:
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
            $ref: '#/components/schemas/TiktokShopProductChildInfoOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«TiktokShopProductChildInfoOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TiktokShopProductChildInfoOpenVo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体Id
        shopId:
          type: string
          description: 店铺id
        shopName:
          type: string
          description: 店铺名称
        productId:
          type: string
          description: 平台产品id
        skuId:
          type: string
          description: skuId-唯一标识
        msku:
          type: string
          description: 平台seller_sku
        mainImage:
          type: string
          description: 主图
        matchStatus:
          type: string
          description: 配对状态
        quantity:
          type: string
          description: 可用库存总数
        commoditySku:
          type: string
          description: 已配对商品SKU
        commodityName:
          type: string
          description: 已配对商品品名
        originalPrice:
          type: string
          description: 不含税价格
        priceIncludeVat:
          type: string
          description: 含税价格
        currency:
          type: string
          description: 币种
        publishSiteList:
          type: array
          description: 已发布站点
          items:
            type: string
        attributeStr:
          type: string
          description: 商品属性
        warehouseVoList:
          type: array
          description: 库存信息
          items:
            $ref: '#/components/schemas/WarehouseOpenVo'
        salesmanNameList:
          type: array
          description: 业务员名称列表
          items:
            type: string
      title: TiktokShopProductChildInfoOpenVo
      x-apifox-orders:
        - parentId
        - shopId
        - shopName
        - productId
        - skuId
        - msku
        - mainImage
        - matchStatus
        - quantity
        - commoditySku
        - commodityName
        - originalPrice
        - priceIncludeVat
        - currency
        - publishSiteList
        - attributeStr
        - warehouseVoList
        - salesmanNameList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WarehouseOpenVo:
      type: object
      properties:
        id:
          type: string
          description: ID
        shopId:
          type: string
          description: 店铺ID,针对FBA仓库
        type:
          type: string
          description: 仓库类型：-1虚拟仓，0默认仓，1国内仓库，2FBA仓，3海外仓
        mode:
          type: string
          description: '仓库运营模式，0:FBA&FBM，1:FBM(拣货仓)，2:FBA(中转仓)   '
        replenishSite:
          type: string
          description: 海外仓可补货站点（国家）
        name:
          type: string
          description: 名称
        manager:
          type: string
          description: 负责人
        skuKind:
          type: string
          description: SKU种类总数
        stockAvailable:
          type: string
          description: 可用库存总数
        stockDefective:
          type: string
          description: 次品总数
        stockOccupy:
          type: string
          description: 占用数
        stockWait:
          type: string
          description: 在途数量
        stockAllNum:
          type: string
          description: 总量
        totalPurchase:
          type: string
          description: 货值
        inventoryCost:
          type: string
          description: 库存成本
      title: WarehouseOpenVo
      x-apifox-orders:
        - id
        - shopId
        - type
        - mode
        - replenishSite
        - name
        - manager
        - skuKind
        - stockAvailable
        - stockDefective
        - stockOccupy
        - stockWait
        - stockAllNum
        - totalPurchase
        - inventoryCost
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
