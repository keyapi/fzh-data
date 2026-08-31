# FBA发货单创建

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fba/shippingOrder/create.json:
    post:
      summary: FBA发货单创建
      deprecated: false
      description: ''
      operationId: createShippingOrderUsingPOST
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
              $ref: '#/components/schemas/ShippingOrderOpenParam'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFbaShippingOrderOpenVo%C2%BB
          headers: {}
          x-apifox-name: 成功
        '201':
          description: Created
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 成功
        '401':
          description: Unauthorized
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 没有权限
        '403':
          description: Forbidden
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 禁止访问
        '404':
          description: Not Found
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 记录不存在
      security: []
      x-apifox-folder: FBA/发货单
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516612-run
components:
  schemas:
    ShippingOrderOpenParam:
      type: object
      required:
        - headFeeType
        - taxFeeShareType
        - warehouseId
        - items
      properties:
        headFeeType:
          type: string
          description: 头程分摊方式（0：按计费重，1：按实重，2：按体积重，3：按SKU数量，4：自定义，5：按总体积，6：按申报价）
          examples:
            - 1
        taxFeeShareType:
          type: string
          description: 税费分摊方式（0：按计费重，1：按实重，2：按体积重，3：按SKU数量，4：自定义，5：按总体积，6：按申报价）
          examples:
            - 1
        auxFeeShareType:
          type: string
          description: 辅料分摊方式（0：按计费重，1：按实重，2：按体积重，3：按SKU数量，5按总体积, 6 按申报价 ）
        realShipTime:
          type: string
          description: 实际发货时间，yyyy-MM-dd
          examples:
            - '2024-01-01'
        expectArrivalDate:
          type: string
          description: 预计到货时间，yyyy-MM-dd
          examples:
            - '2024-01-01'
        remark:
          type: string
          description: 发货单备注
          examples:
            - 发货单备注
        volumeParam:
          type: string
          description: 体积参数
          examples:
            - 1
        logisticId:
          type: string
          description: 头程物流ID（已废弃，请使用fbaLogisticId字段）
          examples:
            - 1
        fbaLogisticId:
          type: string
          description: 头程物流ID
          examples:
            - 1
        logisticProviderId:
          type: string
          description: 物流商ID
          examples:
            - 1
        warehouseId:
          type: string
          description: 调出仓ID
          examples:
            - 1
        logistics:
          type: array
          description: 单据物流信息
          items:
            $ref: '#/components/schemas/ShippingLogisticsOpenParam'
        items:
          type: array
          description: 单据明细信息
          items:
            $ref: '#/components/schemas/ShippingItemOpenParam'
        exclusiveInventory:
          type: string
          description: 使用专属库存 0否 1是
          examples:
            - 0
        paid:
          type: string
          description: 付款标记 0未标记 1未付款 2已付款
          examples:
            - 0
        match:
          type: string
          description: 是否将配对同步到在线产品 true,false
          examples:
            - false
        isSelectShelf:
          type: string
          description: 是否勾选了手动选择货架位, true, false
          examples:
            - false
        commodityPartsList:
          type: array
          description: 商品辅料
          items: &ref_0
            $ref: '#/components/schemas/CommodityAuxListOpenVo'
        billPartsList:
          type: array
          description: 整体辅料
          items: *ref_0
      title: ShippingOrderOpenParam
      x-apifox-orders:
        - headFeeType
        - taxFeeShareType
        - auxFeeShareType
        - realShipTime
        - expectArrivalDate
        - remark
        - volumeParam
        - logisticId
        - fbaLogisticId
        - logisticProviderId
        - warehouseId
        - logistics
        - items
        - exclusiveInventory
        - paid
        - match
        - isSelectShelf
        - commodityPartsList
        - billPartsList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityAuxListOpenVo:
      type: object
      properties:
        auxId:
          type: string
          description: 辅料商品ID
          examples:
            - 1
        createTime:
          type: string
          format: date-time
          description: 创建时间
        auxNum:
          type: string
          description: 辅料比例
          examples:
            - 1
        updateTime:
          type: string
          format: date-time
          description: 修改时间
        commodityNum:
          type: string
          description: 主商品比例
          examples:
            - 1
        commodityId:
          type: string
          description: 主商品id
          examples:
            - 1
        auxSku:
          type: string
          description: 辅料商品sku
          examples:
            - sku
        deliveryQuantity:
          type: string
          description: 出库数量
          examples:
            - 10
        selectedShelfOut:
          type: array
          description: 辅料货架位
          items:
            type: string
      title: CommodityAuxListOpenVo
      x-apifox-orders:
        - auxId
        - createTime
        - auxNum
        - updateTime
        - commodityNum
        - commodityId
        - auxSku
        - deliveryQuantity
        - selectedShelfOut
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingItemOpenParam:
      type: object
      required:
        - shopId
        - amazonShipmentId
        - sellerSku
        - fnSku
        - commodityId
        - shipCount
      properties:
        shopId:
          type: string
          description: 店铺ID
        amazonShipmentId:
          type: string
          description: fba货件ID
          examples:
            - 1
        planSn:
          type: string
          description: 发货计划编号
        sellerSku:
          type: string
          description: 卖家SKU
          examples:
            - sellfox-sku
        fnSku:
          type: string
          description: FNSKU
          examples:
            - sellfox-fnsku
        customsUnitPrice:
          type: string
          description: 报关单价
          examples:
            - 1
        commodityId:
          type: string
          description: 商品ID
          examples:
            - 1
        commoditySku:
          type: string
          description: 商品SKU
          examples:
            - sku
        customsTax:
          type: string
          description: 商品报关税费
          examples:
            - 1
        customsTaxCurrency:
          type: string
          description: 商品税费单位
          examples:
            - CNY
        length:
          type: string
          description: 长
          examples:
            - 1
        width:
          type: string
          description: 宽
          examples:
            - 1
        height:
          type: string
          description: 高
          examples:
            - 1
        weight:
          type: string
          description: 重量g
          examples:
            - 1
        cartonLength:
          type: string
          description: 箱规——长
          examples:
            - 1
        cartonWidth:
          type: string
          description: 箱规——宽
          examples:
            - 1
        cartonHeight:
          type: string
          description: 箱规——高
          examples:
            - 1
        cartonQty:
          type: string
          description: 单箱数量
          examples:
            - 1
        quantity:
          type: string
          description: 申报量
          examples:
            - 1
        shipCount:
          type: string
          description: 发货数
          examples:
            - 1
        available:
          type: string
          description: 可用量
          examples:
            - 1
        headFee:
          type: string
          description: 自定义头程费用
          examples:
            - 1
        shippingOrderRemark:
          type: string
          description: 商品备注
          examples:
            - 发货单明细备注
        unitPurchaseCost:
          type: string
          description: 单位采购成本（导入的单位采购成本）
          examples:
            - 1
        manualPurchaseCost:
          type: string
          description: 指定单位采购成本
          examples:
            - 1
        purchaseCostCurrency:
          type: string
          description: 采购成本币种
          examples:
            - CNY
        selectedShelfOut:
          type: array
          description: 用户选择出库的良品货架位(出库可以有多个)
          items:
            type: string
      title: ShippingItemOpenParam
      x-apifox-orders:
        - shopId
        - amazonShipmentId
        - planSn
        - sellerSku
        - fnSku
        - customsUnitPrice
        - commodityId
        - commoditySku
        - customsTax
        - customsTaxCurrency
        - length
        - width
        - height
        - weight
        - cartonLength
        - cartonWidth
        - cartonHeight
        - cartonQty
        - quantity
        - shipCount
        - available
        - headFee
        - shippingOrderRemark
        - unitPurchaseCost
        - manualPurchaseCost
        - purchaseCostCurrency
        - selectedShelfOut
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingLogisticsOpenParam:
      type: object
      properties:
        logisticsNo:
          type: string
          description: 物流商单号
          examples:
            - 1
        trackingNo:
          type: string
          description: 追踪号
          examples:
            - 1
        estimateLogisticsCost:
          type: string
          description: 预估物流费用
          examples:
            - 1
        estimateLogisticsCostCurrency:
          type: string
          description: 预估物流费用币种
          examples:
            - CNY
        estimateOtherCost:
          type: string
          description: 预估其他费用
          examples:
            - 1
        estimateOtherCostCurrency:
          type: string
          description: 预估其他费用币种
          examples:
            - CNY
        estimateTaxCost:
          type: string
          description: 预估税费
          examples:
            - 1
        estimateTaxCostCurrency:
          type: string
          description: 预估税费币种
          examples:
            - CNY
        logisticsCost:
          type: string
          description: 实际物流费用
          examples:
            - 1
        logisticsCostCurrency:
          type: string
          description: 实际物流费用币种
          examples:
            - CNY
        otherCost:
          type: string
          description: 实际其他费用
          examples:
            - 1
        otherCostCurrency:
          type: string
          description: 实际其他费用币种
          examples:
            - CNY
        taxCost:
          type: string
          description: 实际税费
          examples:
            - 1
        taxCostCurrency:
          type: string
          description: 实际税费币种
          examples:
            - CNY
        rate:
          type: string
          description: 汇率
          examples:
            - 1
      title: ShippingLogisticsOpenParam
      x-apifox-orders:
        - logisticsNo
        - trackingNo
        - estimateLogisticsCost
        - estimateLogisticsCostCurrency
        - estimateOtherCost
        - estimateOtherCostCurrency
        - estimateTaxCost
        - estimateTaxCostCurrency
        - logisticsCost
        - logisticsCostCurrency
        - otherCost
        - otherCostCurrency
        - taxCost
        - taxCostCurrency
        - rate
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FbaShippingOrderOpenVo»:
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
          $ref: '#/components/schemas/FbaShippingOrderOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FbaShippingOrderOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaShippingOrderOpenVo:
      type: object
      title: FbaShippingOrderOpenVo
      x-apifox-orders: []
      properties: {}
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
