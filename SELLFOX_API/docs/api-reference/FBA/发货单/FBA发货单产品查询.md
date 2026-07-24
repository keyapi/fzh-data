# FBA发货单产品查询

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fba/shippingOrder/items.json:
    post:
      summary: FBA发货单产品查询
      deprecated: false
      description: ''
      operationId: itemsUsingPOST
      tags:
        - FBA/发货单
        - FBA
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
              $ref: '#/components/schemas/ShippingOrderItemsOpenQo'
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABShippingOrderItemOpenVo%C2%BB%C2%BB
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
      x-apifox-folder: FBA/发货单
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516613-run
components:
  schemas:
    ShippingOrderItemsOpenQo:
      type: object
      properties:
        shipSn:
          type: string
          description: 发货单号
      title: ShippingOrderItemsOpenQo
      x-apifox-orders:
        - shipSn
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«ShippingOrderItemOpenVo»»:
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
            $ref: '#/components/schemas/ShippingOrderItemOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«ShippingOrderItemOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingOrderItemOpenVo:
      type: object
      properties:
        shopId:
          type: string
          description: 店铺ID
        marketplaceId:
          type: string
          description: 站点ID
        marketplace:
          type: string
          description: 站点
        amazonShipmentId:
          type: string
          description: 亚马逊FBA货件ID
        shipSn:
          type: string
          description: 发货单号
        planSn:
          type: string
          description: 发货计划编号
        auxFee:
          type: string
          description: 辅料的费用
        sellerSku:
          type: string
          description: 卖家SKU
        fnSku:
          type: string
          description: Fulfilment Network SKU
        asin:
          type: string
          description: ASIN
        commodityId:
          type: string
          description: 商品ID
        customsTax:
          type: string
          description: 报关税费
        customsTaxCurrency:
          type: string
          description: 报关税费币种
        length:
          type: string
          description: 长
        width:
          type: string
          description: 宽
        height:
          type: string
          description: 高
        lengthUnit:
          type: string
          description: 长度单位，默认cm
        weight:
          type: string
          description: 重量
        weightUnit:
          type: string
          description: 重量单位，默认g
        cartonLength:
          type: string
          description: 箱规——长
        cartonWidth:
          type: string
          description: 箱规——宽
        cartonHeight:
          type: string
          description: 箱规——高
        cartonQty:
          type: string
          description: 单箱数量
        customsUnitPrice:
          type: number
          format: double
          description: 报关单价
        quantity:
          type: string
          description: 申报量
        shipCount:
          type: string
          description: 发货数
        availableCount:
          type: string
          description: 可用量
        localInventoryVos:
          type: array
          description: 本地可用明细
          items:
            $ref: '#/components/schemas/LocalInventoryOpenVo'
        headFee:
          type: string
          description: 自定义头程费用 / 分摊头程费用
        purchaseCost:
          type: string
          description: 采购成本
        manualPurchaseCost:
          type: string
          description: 指定采购成本
        firstHeadLogistics:
          type: string
          description: 首段头程物流
        areCasesRequired:
          type: string
          description: 包装类型 0混发 1原厂
        shipmentType:
          type: string
          description: 货件类型：SP,TLT
        caseNum:
          type: string
          description: 箱数（原厂包装）
        quantityInCase:
          type: string
          description: 单箱数量（原厂包装）
        adjustStatus:
          type: string
          description: 补录状态
        diffCount:
          type: string
          description: 差异量
        shipmentStatus:
          type: string
          description: shipmentStatus
        shippingOrderRemark:
          type: string
          description: 发货单明细备注
        quantityReceived:
          type: string
          description: 到货量
        childItems:
          type: array
          description: 子商品的信息
          items:
            $ref: '#/components/schemas/FbaShippingOrderItemGroupOpenVo'
      title: ShippingOrderItemOpenVo
      x-apifox-orders:
        - shopId
        - marketplaceId
        - marketplace
        - amazonShipmentId
        - shipSn
        - planSn
        - auxFee
        - sellerSku
        - fnSku
        - asin
        - commodityId
        - customsTax
        - customsTaxCurrency
        - length
        - width
        - height
        - lengthUnit
        - weight
        - weightUnit
        - cartonLength
        - cartonWidth
        - cartonHeight
        - cartonQty
        - customsUnitPrice
        - quantity
        - shipCount
        - availableCount
        - localInventoryVos
        - headFee
        - purchaseCost
        - manualPurchaseCost
        - firstHeadLogistics
        - areCasesRequired
        - shipmentType
        - caseNum
        - quantityInCase
        - adjustStatus
        - diffCount
        - shipmentStatus
        - shippingOrderRemark
        - quantityReceived
        - childItems
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaShippingOrderItemGroupOpenVo:
      type: object
      properties:
        shippingOrderId:
          type: string
          description: 发货单ID
        shipSn:
          type: string
          description: 发货单号
        commodityId:
          type: string
          description: 商品ID
        commoditySku:
          type: string
          description: 配对商品SKU
        commodityName:
          type: string
          description: 配对商品名称（单品级别）
        commodityImage:
          type: string
          description: 配对商品主图（单品级别）
        customsUnitPrice:
          type: string
          description: 报关单价
        quantity:
          type: string
          description: 单品发货数量
        warehouseItemId:
          type: string
          description: 仓库itemId
        warehouseFnSku:
          type: string
          description: 仓库FNSKU
        availableCount:
          type: string
          description: 可用量
        purchaseCost:
          type: string
          description: 采购成本
        headFee:
          type: string
          description: 头程费用
        selectedShelfOut:
          type: array
          description: 用户选择的出库货架位
          items:
            type: string
      title: FbaShippingOrderItemGroupOpenVo
      x-apifox-orders:
        - shippingOrderId
        - shipSn
        - commodityId
        - commoditySku
        - commodityName
        - commodityImage
        - customsUnitPrice
        - quantity
        - warehouseItemId
        - warehouseFnSku
        - availableCount
        - purchaseCost
        - headFee
        - selectedShelfOut
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    LocalInventoryOpenVo:
      type: object
      properties:
        warehouseItemId:
          type: string
          description: 仓库明细ID
        warehouseId:
          type: string
          description: 仓库ID
        warehouseName:
          type: string
          description: 仓库名称
        commoditySku:
          type: string
          description: 商品SKU
        fnSku:
          type: string
          description: fnSku
        quantity:
          type: string
          description: 可用数量
        stockWait:
          type: string
          description: 待到货数
      title: LocalInventoryOpenVo
      x-apifox-orders:
        - warehouseItemId
        - warehouseId
        - warehouseName
        - commoditySku
        - fnSku
        - quantity
        - stockWait
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
